"""
TheCodex Discord bot — main orchestrator.

Unified startup sequence (mirrors Ecom / TheHost / ImperialReminder):
    1. Load env from docker/.env
    2. setup_application_logging  → "Application logging initialized for: discord-bot-codex"
    3. main(): banner + Python/discord.py versions
    4. _async_main(): install signal handlers → init DatabaseManager → start health endpoint (50002)
    5. start_services(): bot.start raced against shutdown_event
    6. on_ready (idempotent via _init_done): Database Attachment → Cog Loading → Command Sync → Status Setup
    7. shutdown_handler(): health → DB → bot
"""

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Load env from docker/.env before any other imports read env vars
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "docker" / ".env")

import discord

from startup.bot import bot, TOKEN, s  # noqa: E402,F401
from utils.logger import get_logger, setup_application_logging  # noqa: E402
from startup.sync import load_cogs, attach_databases, log_all_commands  # noqa: E402
from startup.phases import (  # noqa: E402
    log_startup_summary,
    startup_phase,
)
from health_endpoint import initialize_health_server, stop_health_server  # noqa: E402
from storage.database_manager import db_manager  # noqa: E402

# Guild that owns the guild-scoped admin slash commands (e.g. /status).
# Environment-specific, so it is opt-in via env; guild sync is skipped if unset.
STATUS_ADMIN_GUILD_ID = int(os.getenv("STATUS_ADMIN_GUILD_ID", "0"))

# Initialize application-wide logging
APPLICATION_NAME = "discord-bot-codex"
HEALTH_PORT = 50002

app_logger = setup_application_logging(
    app_name=APPLICATION_NAME,
    log_level=logging.INFO,  # Change to DEBUG for development
    log_dir="logs",
    enable_performance_logging=True,
    max_file_size=20 * 1024 * 1024,  # 20 MB
    backup_count=10,
)

# Main logger for this module
logger = get_logger("main")


async def on_ready():
    """
    Handle bot readiness. Idempotent across gateway reconnects via _init_done.

    On first ready: attach databases, load cogs, sync commands, set status,
    log startup summary. On reconnect: just refresh presence and return.
    """
    if getattr(bot, "_init_done", False):
        try:
            await bot.change_presence(status=discord.Status.online)
            logger.info("🔁 Reconnect detected — presence refreshed, init skipped.")
        except Exception as e:
            logger.error(f"❌ Error refreshing presence on reconnect: {e}")
        return

    logger.info(f"🚀 Bot logged in as {bot.user}")
    logger.info(
        f"📊 Connected to {len(bot.guilds)} guilds with "
        f"{sum(g.member_count or 0 for g in bot.guilds)} total members"
    )

    try:
        async with startup_phase("Database Attachment"):
            await attach_databases()
    except Exception:
        logger.error("❌ Error during database attachment", exc_info=True)
        return  # Can't operate without attached managers

    try:
        async with startup_phase("Cog Loading"):
            await load_cogs()
    except Exception as cog_error:
        logger.error(f"❌ Error during cog loading: {cog_error}", exc_info=True)

    try:
        async with startup_phase("Command Sync"):
            synced_global = await bot.tree.sync()
            if STATUS_ADMIN_GUILD_ID:
                admin_guild = discord.Object(id=STATUS_ADMIN_GUILD_ID)
                synced_admin = await bot.tree.sync(guild=admin_guild)
                logger.info(
                    f"🔄 Resynced commands: {len(synced_global)} global + "
                    f"{len(synced_admin)} guild-scoped registered."
                )
            else:
                logger.info(
                    f"🔄 Resynced global commands: {len(synced_global)} registered "
                    f"(STATUS_ADMIN_GUILD_ID unset, skipped guild sync)."
                )
    except Exception as sync_error:
        logger.error(f"❌ Error during command sync: {sync_error}", exc_info=True)

    try:
        async with startup_phase("Status Setup"):
            await bot.change_presence(status=discord.Status.online)
    except Exception as status_error:
        logger.error(f"❌ Error during status setup: {status_error}", exc_info=True)

    log_startup_summary()
    logger.info("🎉 Bot is fully online and operational!")

    try:
        await log_all_commands(bot)
    except Exception as cmd_log_error:
        logger.error(f"❌ Error logging commands: {cmd_log_error}")

    bot._init_done = True


bot.event(on_ready)  # Register the event


async def shutdown_handler():
    """Graceful shutdown: health server → database → bot."""
    shutdown_start = time.perf_counter()
    logger.info("🛑 Initiating graceful shutdown...")

    try:
        stop_health_server()
    except Exception as e:
        logger.error(f"❌ Error stopping health server: {e}")

    try:
        logger.info("🔄 Closing database connections...")
        await db_manager.close()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error during database cleanup: {e}")

    try:
        if not bot.is_closed():
            await bot.close()
            logger.info("✅ Bot connection closed")
    except Exception as shutdown_error:
        logger.error(f"❌ Error during bot shutdown: {shutdown_error}")

    duration = time.perf_counter() - shutdown_start
    logger.info(f"🏁 Graceful shutdown completed in {duration:.2f}s")


async def start_services(shutdown_event: asyncio.Event):
    """Start the bot and await either its exit or a shutdown signal."""
    bot_task = asyncio.create_task(bot.start(TOKEN), name="bot_task")
    shutdown_wait = asyncio.create_task(shutdown_event.wait(), name="shutdown_wait")

    try:
        done, pending = await asyncio.wait(
            [bot_task, shutdown_wait], return_when=asyncio.FIRST_COMPLETED
        )

        if shutdown_wait in done:
            logger.info("🛑 Shutdown signal received, stopping services...")
        elif bot_task in done:
            try:
                bot_task.result()
            except Exception as e:
                logger.error(f"💥 Bot stopped unexpectedly: {e}")

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except asyncio.CancelledError:
        logger.info("🔄 Services cancelled during shutdown")
    finally:
        if bot_task and not bot_task.done():
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass
        await shutdown_handler()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown_event: asyncio.Event):
    """Install SIGINT/SIGTERM handlers (graceful no-op on Windows)."""
    def _signal_handler(sig_name: str):
        logger.info(f"📡 Received {sig_name} signal, initiating shutdown...")
        shutdown_event.set()

    signals_to_handle = []
    if hasattr(signal, "SIGINT"):
        signals_to_handle.append(signal.SIGINT)
    if hasattr(signal, "SIGTERM"):
        signals_to_handle.append(signal.SIGTERM)

    for sig in signals_to_handle:
        try:
            loop.add_signal_handler(sig, _signal_handler, sig.name)
        except NotImplementedError:
            pass
        except Exception as e:
            logger.warning(f"⚠️ Failed to register signal handler for {sig.name}: {e}")


async def _async_main(shutdown_event: asyncio.Event):
    """Async entry: install signals, init DB, start health, start services."""
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, shutdown_event)

    try:
        logger.info("🔄 Initializing database manager...")
        await db_manager.initialize()
        logger.info("✅ Database manager initialized successfully")
    except Exception as e:
        logger.critical(f"💥 Failed to initialize database manager: {e}")
        raise

    try:
        initialize_health_server(port=HEALTH_PORT, bot=bot, db_manager=db_manager)
        logger.info("✅ Health check endpoint initialized")
    except Exception as e:
        logger.error(f"❌ Failed to start health endpoint: {e}")

    await start_services(shutdown_event)


def main():
    """Process entry point."""
    logger.info(f"=== Starting {APPLICATION_NAME} ===")
    logger.info(f"🐍 Python version: {sys.version}")
    logger.info(f"🤖 Discord.py version: {discord.__version__}")

    shutdown_event = asyncio.Event()

    try:
        asyncio.run(_async_main(shutdown_event))
    except KeyboardInterrupt:
        logger.info("⌨️ Keyboard interrupt received.")
    except Exception:
        logger.critical("💥 Fatal error occurred in main execution", exc_info=True)
        raise
    finally:
        logger.info(f"=== {APPLICATION_NAME} shutdown complete ===")


if __name__ == "__main__":
    main()
