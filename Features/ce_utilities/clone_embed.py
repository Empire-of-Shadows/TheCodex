"""Clone Embed - admin message context-menu command.

Right-click any message that has an embed -> Apps -> "Clone Embed", then pick a
destination (this channel, or another one) to re-post its embed(s) as a clean
bot message. Replaces the old prefix `.embed clone / preview / batch` commands.

Why a context menu instead of a slash command:
  - It only shows on right-click for members with Manage Messages, so it stays
    out of the way of regular users (the reason the old commands were prefix-based
    and hidden from the slash picker).
  - The clone is posted with ``channel.send()`` rather than as the interaction
    response, so there is no "Username used <command>" attribution line above it -
    a clean copy of just the embed(s).

Context menus take no parameters, so the destination is collected through an
ephemeral picker (a channel select + a "Clone here" button) shown after the
right-click.
"""

from __future__ import annotations

import discord
from discord import app_commands

from storage.log import get_logger

logger = get_logger("CloneEmbed")


class _CloneDestinationView(discord.ui.View):
    """Ephemeral picker: choose where the cloned embed(s) should be posted."""

    def __init__(self, embeds: list[discord.Embed], source_message_id: int):
        super().__init__(timeout=120)
        self._embeds = embeds
        self._source_id = source_message_id
        self._interaction: discord.Interaction | None = None

    async def on_timeout(self) -> None:
        if self._interaction is not None:
            try:
                await self._interaction.edit_original_response(
                    content="Clone timed out - run it again if you still want to copy the embed.",
                    view=None,
                )
            except discord.HTTPException:
                pass

    async def _clone_to(self, interaction: discord.Interaction, channel) -> None:
        # The bot must be able to post embeds in the destination...
        bot_perms = channel.permissions_for(interaction.guild.me)
        if not (bot_perms.send_messages and bot_perms.embed_links):
            await interaction.response.edit_message(
                content=f"I don't have permission to post embeds in {channel.mention}.",
                view=None,
            )
            self.stop()
            return
        # ...and the person cloning must be able to see the destination.
        if not channel.permissions_for(interaction.user).view_channel:
            await interaction.response.edit_message(
                content="You don't have access to that channel.", view=None,
            )
            self.stop()
            return

        try:
            # All embeds in one message, exactly as they appeared on the source.
            await channel.send(embeds=self._embeds)
        except discord.HTTPException as e:
            logger.error(f"Failed to clone embed(s) for {interaction.user}: {e}", exc_info=True)
            await interaction.response.edit_message(
                content="Couldn't clone the embed(s). Please try again.", view=None,
            )
            self.stop()
            return

        n = len(self._embeds)
        logger.info(
            f"{interaction.user} ({interaction.user.id}) cloned {n} embed(s) from "
            f"message {self._source_id} to channel {channel.id} (guild {interaction.guild_id})"
        )
        await interaction.response.edit_message(
            content=f"Cloned {n} embed{'s' if n != 1 else ''} to {channel.mention}.",
            view=None,
        )
        self.stop()

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Clone to another channel...",
        min_values=1,
        max_values=1,
    )
    async def pick_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel(select.values[0].id)
        if channel is None:
            await interaction.response.edit_message(
                content="That channel could not be resolved.", view=None,
            )
            self.stop()
            return
        await self._clone_to(interaction, channel)

    @discord.ui.button(label="Clone here", style=discord.ButtonStyle.primary, emoji="📋")
    async def clone_here(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._clone_to(interaction, interaction.channel)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def clone_embed(interaction: discord.Interaction, message: discord.Message):
    """Ask where to clone, then re-post the target message's embed(s) cleanly."""
    if not message.embeds:
        await interaction.response.send_message(
            "That message has no embed to clone.", ephemeral=True
        )
        return

    n = len(message.embeds)
    view = _CloneDestinationView(list(message.embeds), message.id)
    await interaction.response.send_message(
        f"Clone {n} embed{'s' if n != 1 else ''} - post it in this channel, or pick another below.",
        view=view,
        ephemeral=True,
    )
    # Stored so the view can clear itself on timeout.
    view._interaction = interaction


async def setup(bot):
    """Register the message context-menu command on the command tree."""
    bot.tree.add_command(
        app_commands.ContextMenu(name="Clone Embed", callback=clone_embed)
    )
    logger.info("Clone Embed context menu registered")
