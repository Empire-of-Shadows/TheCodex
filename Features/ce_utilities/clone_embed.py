"""Clone Embed — admin message context-menu command.

Right-click any message that has an embed -> Apps -> "Clone Embed" to re-post
its embed(s) in the same channel as a clean bot message. Replaces the old prefix
`.embed clone / preview / batch` commands.

Why a context menu instead of a slash command:
  - It only shows on right-click for members with Manage Messages, so it stays
    out of the way of regular users (the reason the old commands were prefix-based
    and hidden from the slash picker).
  - The clone is posted with ``channel.send()`` rather than as the interaction
    response, so there is no "Username used <command>" attribution line above it -
    a clean copy of just the embed.
"""

import discord
from discord import app_commands

from storage.logging import get_logger

logger = get_logger("CloneEmbed")


@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def clone_embed(interaction: discord.Interaction, message: discord.Message):
    """Re-post the target message's embed(s) cleanly in the current channel."""
    # Answer privately first so the public clone carries no command attribution.
    await interaction.response.defer(ephemeral=True)

    if not message.embeds:
        await interaction.followup.send(
            "That message has no embed to clone.", ephemeral=True
        )
        return

    channel = interaction.channel
    posted = 0
    for embed in message.embeds:
        try:
            await channel.send(embed=embed)
            posted += 1
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to send messages in this channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            logger.error(
                f"Failed to clone an embed for {interaction.user}: {e}", exc_info=True
            )

    if posted == 0:
        await interaction.followup.send(
            "Couldn't clone that embed. Please try again.", ephemeral=True
        )
        return

    logger.info(
        f"{interaction.user} ({interaction.user.id}) cloned {posted} embed(s) from "
        f"message {message.id} into channel {channel.id} (guild {interaction.guild_id})"
    )
    await interaction.followup.send(
        f"Cloned {posted} embed{'s' if posted != 1 else ''} into this channel.",
        ephemeral=True,
    )


async def setup(bot):
    """Register the message context-menu command on the command tree."""
    bot.tree.add_command(
        app_commands.ContextMenu(name="Clone Embed", callback=clone_embed)
    )
    logger.info("Clone Embed context menu registered")
