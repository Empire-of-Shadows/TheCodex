"""
Drop Cog - /drop slash command with Components v2 panel.

Provides a role-aware panel for browsing sent drops and (for managers)
testing drops and viewing unsent drops.
"""

import math

import discord
from discord import app_commands
from discord.ext import commands

from admin.actions.drops_actions import DropsActions
from storage.settings.config_manager import get_config
from storage.settings.collections import db_manager
from storage.log import get_logger
from utils.setup_notice import send_setup_notice, setup_notice_text

from .drop_views import (
    build_drops_browse_view,
    build_unsent_drops_view,
    attach_timeout_expiry_msg,
    DROPS_PER_PAGE,
)

logger = get_logger("DropCog")


class DropCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="drop", description="Browse Prime Gaming drops")
    @app_commands.guild_only()
    async def drop_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        is_manager = await DropsActions.has_drops_management(interaction.user)
        collection = db_manager.get_collection_manager("prime_drops")
        guild_id = interaction.guild.id
        sent_field = f"sent_by_guild.{guild_id}"

        # State tracked via mutable list for closure access
        browse_page = [0]
        unsent_page = [0]

        async def _fetch_sent():
            return await collection.find_many(
                {sent_field: {"$exists": True}},
                sort=[(sent_field, -1)],
            )

        async def _fetch_unsent():
            return await collection.find_many(
                {sent_field: {"$exists": False}},
                sort=[("expires", 1)],
            )

        async def _show_browse(target_interaction: discord.Interaction | None = None):
            """Build and show the browse view. If target_interaction is None, use followup."""
            sent = await _fetch_sent()
            total_pages = max(1, math.ceil(len(sent) / DROPS_PER_PAGE))
            browse_page[0] = min(browse_page[0], total_pages - 1)
            start = browse_page[0] * DROPS_PER_PAGE
            page_drops = sent[start : start + DROPS_PER_PAGE]

            # An empty list on a server with no drops channel means drops were
            # never turned on, not that none were released. Explain which.
            setup_hint = ""
            if not page_drops:
                guild_config = await get_config(guild_id)
                if not guild_config.drops.get("channel_id"):
                    setup_hint = await setup_notice_text(
                        interaction.guild,
                        what="Prime Gaming drops",
                        path="Updates & Drops -> Drops Channel",
                        viewer=interaction.user if isinstance(interaction.user, discord.Member) else None,
                    )

            layout = build_drops_browse_view(
                drops=page_drops,
                page=browse_page[0],
                total_pages=total_pages,
                is_manager=is_manager,
                on_prev=on_browse_prev,
                on_next=on_browse_next,
                on_test=on_test if is_manager else None,
                on_unsent=on_show_unsent if is_manager else None,
                setup_hint=setup_hint,
            )

            if target_interaction:
                await target_interaction.response.edit_message(view=layout)
                attach_timeout_expiry_msg(layout, await interaction.original_response())
            else:
                msg = await interaction.followup.send(view=layout, ephemeral=True)
                attach_timeout_expiry_msg(layout, msg)

        async def on_browse_prev(btn_interaction: discord.Interaction):
            browse_page[0] = max(0, browse_page[0] - 1)
            await _show_browse(btn_interaction)

        async def on_browse_next(btn_interaction: discord.Interaction):
            browse_page[0] += 1
            await _show_browse(btn_interaction)

        async def on_test(btn_interaction: discord.Interaction):
            await btn_interaction.response.defer(ephemeral=True)
            prime_cog = self.bot.get_cog("PrimeDrops")
            if not prime_cog:
                await btn_interaction.followup.send(
                    "PrimeDrops cog is not loaded.", ephemeral=True
                )
                return

            guild_config = await get_config(guild_id)
            if not guild_config.drops.get("channel_id"):
                await send_setup_notice(
                    btn_interaction,
                    what="a drops channel",
                    path="Updates & Drops -> Drops Channel",
                    detail="There is nowhere to post drops yet.",
                )
                return

            sent_count = await prime_cog.send_drops_for_guild(guild_id, guild_config)
            if sent_count:
                await btn_interaction.followup.send(
                    f"Posted {sent_count} drop(s) to the drops channel.",
                    ephemeral=True,
                )
            else:
                await btn_interaction.followup.send(
                    "No unsent drops for this server.", ephemeral=True
                )

        async def on_show_unsent(btn_interaction: discord.Interaction):
            unsent_page[0] = 0
            await _show_unsent(btn_interaction)

        async def _show_unsent(target_interaction: discord.Interaction):
            unsent = await _fetch_unsent()
            total_pages = max(1, math.ceil(len(unsent) / DROPS_PER_PAGE))
            unsent_page[0] = min(unsent_page[0], total_pages - 1)
            start = unsent_page[0] * DROPS_PER_PAGE
            page_drops = unsent[start : start + DROPS_PER_PAGE]

            layout = build_unsent_drops_view(
                drops=page_drops,
                page=unsent_page[0],
                total_pages=total_pages,
                on_prev=on_unsent_prev,
                on_next=on_unsent_next,
                on_back=on_back_to_browse,
            )
            await target_interaction.response.edit_message(view=layout)
            attach_timeout_expiry_msg(layout, await interaction.original_response())

        async def on_unsent_prev(btn_interaction: discord.Interaction):
            unsent_page[0] = max(0, unsent_page[0] - 1)
            await _show_unsent(btn_interaction)

        async def on_unsent_next(btn_interaction: discord.Interaction):
            unsent_page[0] += 1
            await _show_unsent(btn_interaction)

        async def on_back_to_browse(btn_interaction: discord.Interaction):
            browse_page[0] = 0
            await _show_browse(btn_interaction)

        await _show_browse()


async def setup(bot: commands.Bot):
    await bot.add_cog(DropCog(bot))
