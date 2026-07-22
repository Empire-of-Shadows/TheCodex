"""
Startup sync seam for TheCodex (bot-owned, NOT vendored).

The generic cog-loading machinery (discovery, priority/parallel loading, attribute
attachment, command-table logging) lives in the vendored runtime engine at
``startup/loader.py``. This file supplies only what is Codex-specific: the cog
discovery roots, the owner-only ``load_cogs`` reload command, and
``attach_databases()`` (which managers exist and how they wire onto the bot).
``Codex.py`` keeps importing ``load_cogs`` / ``attach_databases`` /
``log_all_commands`` from here.
"""

from discord.ext import commands

from startup.bot import bot, s
from startup.loader import (  # noqa: F401 - log_all_commands is re-exported for Codex.py
    attach_attribute,
    load_cogs as _engine_load_cogs,
    log_all_commands,
)
from storage.log import get_logger

logger = get_logger("Sync")


# Cog discovery roots. Priority cogs load first (sequential) for DB-dependent setup;
# the rest load in parallel for a faster boot.
COG_DIRECTORIES = ["./commands", "./admin", "./Features"]
PRIORITY_COG_DIRECTORIES: list[str] = []


async def load_cogs():
    """Load all cogs from the configured directories (engine loader)."""
    await _engine_load_cogs(bot, COG_DIRECTORIES, PRIORITY_COG_DIRECTORIES)


@bot.command(name="load_cogs", help="Loads all cogs in the COG_DIRECTORIES list.")
@commands.is_owner()
async def load_cogs_command(ctx):
    """Owner-only runtime cog (re)load."""
    await ctx.send("Loading cogs...")
    await load_cogs()
    await ctx.send("Cogs loaded successfully.")


async def attach_databases():
    """
    Initialize and attach the DB-dependent managers onto the bot instance.
    Groups successfully attached (`✅`) and failed (`❌`) attributes in one log.
    """
    success_logs = [f"{s}🔄 Starting database attachment process...\n"]
    failed_logs = []

    try:
        # Initialize DatabaseManager first (all other managers depend on it)
        from storage.settings.collections import db_manager
        try:
            await db_manager.initialize()
            result, is_success = await attach_attribute(bot, "db_manager", db_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as db_error:
            failed_logs.append(f"{s}❌ db_manager → Error: {db_error}\n")
            raise  # Can't continue without db_manager

        # Guild snapshot service (snapshots discord objects into the ServerData collections)
        try:
            from storage.discord import create_guild_snapshot_service, GuildSnapshotConfig
            guild_snapshots = create_guild_snapshot_service(
                db_manager, config=GuildSnapshotConfig(timezone="America/Chicago"))
            result, is_success = await attach_attribute(bot, "guild_snapshots", guild_snapshots)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as snapshot_error:
            failed_logs.append(f"{s}❌ guild_snapshots → Error: {snapshot_error}\n")

        # Unified GuildConfigManager (structured config + flat settings)
        try:
            from storage.settings.config_manager import get_guild_config_manager
            guild_config_manager = await get_guild_config_manager(db_manager)
            result, is_success = await attach_attribute(bot, "guild_config_manager", guild_config_manager)
            (success_logs if is_success else failed_logs).append(result)

            result, is_success = await attach_attribute(bot, "storage_config_manager", guild_config_manager)
            (success_logs if is_success else failed_logs).append(result)
        except Exception as config_error:
            failed_logs.append(f"{s}❌ guild_config_manager / storage_config_manager → Error: {config_error}\n")
    except Exception as e:
        failed_logs.append(f"{s}❌ Encountered a critical error during database attachment → {e}\n")

    if failed_logs:
        failed_logs.insert(0, f"{s}❌ Failed to attach the following attributes:\n")
    if success_logs:
        success_logs.insert(1 if failed_logs else 0, f"{s}✅ Successfully attached the following attributes:\n")

    final_log = failed_logs + success_logs
    logger.info("\n" + "".join(final_log) + f"{s}✅ Database attachment process completed.\n")
