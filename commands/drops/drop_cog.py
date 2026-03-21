"""
Drop Cog - /drop slash command with Components v2 panel.

Provides a role-aware panel for browsing sent drops and (for managers)
testing drops and viewing unsent drops.
"""

import math

import discord
from discord import app_commands
from discord.ext import commands

from commands.admin.actions.drops_actions import DropsActions
from commands.admin.views.panel_views import attach_timeout_expiry_msg
from storage.database_manager import db_manager
from utils.logger import get_logger

from .drop_views import (
    build_drops_browse_view,
    build_unsent_drops_view,
    DROPS_PER_PAGE,
)

logger = get_logger("DropCog")


class DropCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="drop", description="Browse Prime Gaming drops")
    async def drop_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        is_manager = await DropsActions.has_drops_management(interaction.user)
        collection = db_manager.get_collection_manager("prime_drops")

        # State tracked via mutable list for closure access
        browse_page = [0]
        unsent_page = [0]

        async def _fetch_sent():
            return await collection.find_many(
                {"sent": True}, sort=[("sent_at", -1)]
            )

        async def _fetch_unsent():
            return await collection.find_many(
                {"sent": {"$ne": True}}, sort=[("expires", 1)]
            )

        async def _show_browse(target_interaction: discord.Interaction | None = None):
            """Build and show the browse view. If target_interaction is None, use followup."""
            sent = await _fetch_sent()
            total_pages = max(1, math.ceil(len(sent) / DROPS_PER_PAGE))
            browse_page[0] = min(browse_page[0], total_pages - 1)
            start = browse_page[0] * DROPS_PER_PAGE
            page_drops = sent[start : start + DROPS_PER_PAGE]

            layout = build_drops_browse_view(
                drops=page_drops,
                page=browse_page[0],
                total_pages=total_pages,
                is_manager=is_manager,
                on_prev=on_browse_prev,
                on_next=on_browse_next,
                on_test=on_test if is_manager else None,
                on_unsent=on_show_unsent if is_manager else None,
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
            if prime_cog:
                await prime_cog.daily_drops_check()
                await btn_interaction.followup.send(
                    "Drops check completed. Check the drops channel for results.",
                    ephemeral=True,
                )
            else:
                await btn_interaction.followup.send(
                    "PrimeDrops cog is not loaded.", ephemeral=True
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
