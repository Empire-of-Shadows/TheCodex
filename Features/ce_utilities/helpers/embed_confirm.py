"""The confirm step of /embed create.

The modal collects the text; everything that needs a live preview is decided
here. This is deliberately a classic ``discord.ui.View`` on a regular ephemeral
message rather than a Components v2 ``LayoutView``: a message flagged as
Components v2 cannot carry an embed, and the whole point of this step is to show
the member the REAL embed before it goes public.

What lives here:
  - two dependent selects (color set -> color) when the member's roles restrict
    them to specific color sets; a member with no sets assigned types a hex in
    the modal instead and never sees these
  - a Timestamp On/Off toggle, only for members entitled to the timestamp
    feature; it drives the embed's native timestamp property, which is the only
    way to get the localized time Discord renders next to the footer (``<t:...>``
    markdown works in a description but is NOT parsed inside a footer)
  - Post / Cancel

The view is author-locked, disables itself on timeout, and stops as soon as it
has posted or been cancelled.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

import discord

from storage.log import get_logger

logger = get_logger("EmbedConfirm", level=logging.INFO)

# Discord's hard ceiling on select options.
MAX_SELECT_OPTIONS = 25

CONFIRM_TIMEOUT = 300

PREVIEW_TEXT = "Here is your embed. Adjust it below, then press Post."
_PLACEHOLDER_OPTION_VALUE = "__pick_a_set__"


class EmbedConfirmView(discord.ui.View):
    """Live preview plus the final controls for a member-built embed."""

    def __init__(
        self,
        *,
        embed: discord.Embed,
        author_id: int,
        color_sets: Optional[list[dict]] = None,
        allow_timestamp: bool = False,
        cache_update_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
        timeout: float = CONFIRM_TIMEOUT,
    ):
        super().__init__(timeout=timeout)

        self.embed = embed
        self.author_id = author_id
        self.color_sets = [cs for cs in (color_sets or []) if cs.get("colors")]
        self.allow_timestamp = allow_timestamp
        self.cache_update_callback = cache_update_callback

        # The interaction whose original response IS this ephemeral message. Set
        # by bind_source() right after the message is sent; used to post the
        # finished embed publicly and to blank the preview on timeout.
        self.source_interaction: Optional[discord.Interaction] = None

        self.timestamp_on = False
        self.posted = False

        self.set_select: Optional[discord.ui.Select] = None
        self.color_select: Optional[discord.ui.Select] = None
        self.timestamp_button: Optional[discord.ui.Button] = None

        if self.color_sets:
            self._build_color_selects()
        if self.allow_timestamp:
            self._build_timestamp_button()
        self._build_action_buttons()

        logger.debug(
            f"EmbedConfirmView built: {len(self.color_sets)} color set(s), "
            f"timestamp={'on offer' if self.allow_timestamp else 'not entitled'}"
        )

    # -- construction -----------------------------------------------------

    def bind_source(self, interaction: discord.Interaction) -> None:
        """Remember the interaction that owns this ephemeral message."""
        self.source_interaction = interaction

    def _build_color_selects(self) -> None:
        self.set_select = discord.ui.Select(
            placeholder="Choose a color set",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=(cs.get("name") or "Unnamed set")[:100],
                    value=str(index),
                    description=f"{len(cs.get('colors', []))} colors"[:100],
                )
                for index, cs in enumerate(self.color_sets[:MAX_SELECT_OPTIONS])
            ],
        )
        self.set_select.callback = self._on_set_selected
        self.add_item(self.set_select)

        # A Select must ship at least one option, so the dependent one starts
        # disabled behind a placeholder entry until a set has been chosen.
        self.color_select = discord.ui.Select(
            placeholder="Pick a color set first",
            min_values=1,
            max_values=1,
            disabled=True,
            options=[
                discord.SelectOption(label="Pick a color set first", value=_PLACEHOLDER_OPTION_VALUE)
            ],
        )
        self.color_select.callback = self._on_color_selected
        self.add_item(self.color_select)

    def _build_timestamp_button(self) -> None:
        self.timestamp_button = discord.ui.Button(
            label="Timestamp: Off",
            style=discord.ButtonStyle.secondary,
        )
        self.timestamp_button.callback = self._on_timestamp_toggled
        self.add_item(self.timestamp_button)

    def _build_action_buttons(self) -> None:
        self.post_button = discord.ui.Button(label="Post", style=discord.ButtonStyle.success)
        self.post_button.callback = self._on_post
        self.add_item(self.post_button)

        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)

    # -- lifecycle --------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the member who opened the builder may drive it."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This embed builder belongs to someone else.", ephemeral=True
            )
            return False
        return True

    def _disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def on_timeout(self) -> None:
        """Expire cleanly: no live controls left behind on a stale preview."""
        self._disable_all()
        if self.posted or self.source_interaction is None:
            return
        try:
            await self.source_interaction.edit_original_response(
                content="This embed builder timed out. Run `/embed create` again to start over.",
                embed=None,
                view=None,
            )
        except discord.HTTPException as e:
            logger.debug(f"Could not clear the timed-out embed preview: {e}")

    async def _finish(self, interaction: discord.Interaction, message: str) -> None:
        """Consume the button interaction, clear the preview, and stop."""
        self._disable_all()
        await interaction.response.edit_message(content=message, embed=None, view=None)
        self.stop()

    # -- component callbacks ----------------------------------------------

    async def _on_set_selected(self, interaction: discord.Interaction) -> None:
        """Rebuild the color options from the chosen set."""
        raw = interaction.data.get("values", []) if interaction.data else []
        try:
            index = int(raw[0])
            color_set = self.color_sets[index]
        except (IndexError, ValueError):
            await interaction.response.send_message(
                "That color set could not be resolved. Please pick another.", ephemeral=True
            )
            return

        for option in self.set_select.options:
            option.default = option.value == str(index)

        colors = [c for c in color_set.get("colors", []) if c.get("name")]
        self.color_select.options = [
            discord.SelectOption(
                label=str(color["name"])[:100],
                value=str(color["value"]),
                description=f"#{int(color['value']):06X}",
            )
            for color in colors[:MAX_SELECT_OPTIONS]
        ] or [discord.SelectOption(label="This set has no colors", value=_PLACEHOLDER_OPTION_VALUE)]
        self.color_select.disabled = not colors
        self.color_select.placeholder = (
            f"Choose a color from {color_set.get('name', 'this set')}"[:150]
            if colors else "This set has no colors"
        )

        await interaction.response.edit_message(embed=self.embed, view=self)

    async def _on_color_selected(self, interaction: discord.Interaction) -> None:
        """Apply the chosen color to the live preview."""
        raw = interaction.data.get("values", []) if interaction.data else []
        value = raw[0] if raw else _PLACEHOLDER_OPTION_VALUE
        if value == _PLACEHOLDER_OPTION_VALUE:
            await interaction.response.edit_message(embed=self.embed, view=self)
            return

        try:
            color_value = int(value)
        except ValueError:
            await interaction.response.send_message(
                "That color could not be read. Please pick another.", ephemeral=True
            )
            return

        self.embed.color = discord.Color(color_value)
        for option in self.color_select.options:
            option.default = option.value == value

        await interaction.response.edit_message(embed=self.embed, view=self)

    async def _on_timestamp_toggled(self, interaction: discord.Interaction) -> None:
        """Flip the embed's native timestamp on or off."""
        self.timestamp_on = not self.timestamp_on
        if self.timestamp_on:
            self.embed.timestamp = discord.utils.utcnow()
            self.timestamp_button.label = "Timestamp: On"
            self.timestamp_button.style = discord.ButtonStyle.primary
        else:
            self.embed.timestamp = None
            self.timestamp_button.label = "Timestamp: Off"
            self.timestamp_button.style = discord.ButtonStyle.secondary

        await interaction.response.edit_message(embed=self.embed, view=self)

    async def _on_post(self, interaction: discord.Interaction) -> None:
        """Post the embed publicly, exactly as the pre-confirm flow did."""
        if self.source_interaction is None:
            await self._finish(
                interaction, "Something went wrong posting this embed. Please try again."
            )
            return

        try:
            message = await self.source_interaction.followup.send(embed=self.embed)
        except discord.Forbidden:
            logger.error("Missing permission to post a member-built embed", exc_info=True)
            await self._finish(
                interaction, "I don't have permission to send embeds in this channel."
            )
            return
        except discord.HTTPException as e:
            logger.error(f"Discord API error posting a member-built embed: {e}", exc_info=True)
            await self._finish(interaction, "Failed to post the embed. Please try again.")
            return

        self.posted = True
        logger.info(
            f"Embed posted by {interaction.user} ({interaction.user.id}) - message {message.id}"
        )

        if self.cache_update_callback:
            await self.cache_update_callback(self.author_id, message.id)

        await self._finish(interaction, "Embed posted.")

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        await self._finish(interaction, "Cancelled - nothing was posted.")


__all__ = ["EmbedConfirmView", "CONFIRM_TIMEOUT", "MAX_SELECT_OPTIONS", "PREVIEW_TEXT"]
