# Python
import logging
import re
from typing import Optional, Set

import discord
from Features.ce_utilities.helpers.embed_modal import (
	MAX_FOOTER_LENGTH,
	get_allowed_colors,
	get_max_description_length,
	resolve_features,
)
from storage.log import get_logger, log_context

logger = get_logger("EmbedEditModal")


def _is_valid_image_url(url: str) -> bool:
	"""
    Basic validation for thumbnail URLs. Accepts http(s) URLs with common image extensions.
    """
	if not url:
		return False
	if not url.startswith("https://"):
		return False
	return bool(re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)(?:\?.*)?$", url, flags=re.IGNORECASE))


def _parse_color(color_str: str) -> Optional[int]:
	"""
    Parse a color string into an integer RGB value.
    Accepts:
    - Hex with or without '#', case-insensitive
    - 0x-prefixed hex
    Returns int or None if invalid.
    """
	s = color_str.strip().lower()
	if not s:
		return None

	if s.startswith("#"):
		s = s[1:]
	elif s.startswith("0x"):
		s = s[2:]

	if not re.fullmatch(r"[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8}", s):
		return None

	if len(s) == 3:
		s = "".join(ch * 2 for ch in s)

	if len(s) == 8:
		s = s[2:]

	try:
		return int(s, 16)
	except ValueError:
		return None


class EditTimestampView(discord.ui.View):
	"""The timestamp control for /embed edit, on the ephemeral reply to the modal.

	It cannot live in the modal. Discord allows five components in one, and a fully
	entitled member already fills all five with title, description, thumbnail, footer
	and colour. The create flow has the same constraint and solves it the same way -
	its toggle sits on the confirm view, not in ``EmbedModal``.

	Why the native property rather than telling members to type ``<t:...>``: the
	markdown form renders in a description but is NOT parsed inside a footer, so the
	small localized time Discord draws beside the footer is only reachable through
	``Embed.timestamp``. Same reasoning as ``embed_confirm.py``.

	Turning it ON restores the timestamp the embed already had, and falls back to the
	MESSAGE's own creation time when it had none - never ``utcnow()``. The feature
	describes itself as "the time your embed was created", so stamping an edit made a
	week later with the current time would print a creation time that is not one.
	"""

	def __init__(
		self,
		*,
		message: discord.Message,
		embed: discord.Embed,
		author_id: int,
		timeout: float = 300,
	):
		super().__init__(timeout=timeout)
		self.message = message
		# The embed the modal last wrote. Held rather than re-read from
		# ``message.embeds`` because ``Message.edit`` does not refresh the object we
		# are holding, so a re-read could hand back the pre-edit version.
		self.embed = embed
		self.author_id = author_id
		self.source_interaction: Optional[discord.Interaction] = None

		# What ON restores. Captured before any toggle so switching off and back on
		# returns the embed to the time it actually had, not to whenever that happened.
		self.original_timestamp = embed.timestamp
		self.timestamp_on = embed.timestamp is not None

		self.toggle_button = discord.ui.Button(
			label="Timestamp: On" if self.timestamp_on else "Timestamp: Off",
			style=discord.ButtonStyle.primary if self.timestamp_on else discord.ButtonStyle.secondary,
		)
		self.toggle_button.callback = self._on_toggled
		self.add_item(self.toggle_button)

		self.done_button = discord.ui.Button(label="Done", style=discord.ButtonStyle.success)
		self.done_button.callback = self._on_done
		self.add_item(self.done_button)

	def bind_source(self, interaction: discord.Interaction) -> None:
		"""Remember the interaction whose original response carries these controls."""
		self.source_interaction = interaction

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.author_id:
			await interaction.response.send_message(
				"These controls belong to someone else.", ephemeral=True
			)
			return False
		return True

	def _disable_all(self) -> None:
		for child in self.children:
			child.disabled = True

	async def on_timeout(self) -> None:
		"""Leave no live controls on a stale ephemeral message."""
		self._disable_all()
		if self.source_interaction is None:
			return
		try:
			await self.source_interaction.edit_original_response(
				content="Timestamp controls expired. Run `/embed edit` again to change it.",
				view=None,
			)
		except discord.HTTPException as e:
			logger.debug(f"Could not clear the timed-out timestamp controls: {e}")

	async def _on_toggled(self, interaction: discord.Interaction) -> None:
		"""Flip the timestamp on the live message, not just on the preview."""
		self.timestamp_on = not self.timestamp_on
		if self.timestamp_on:
			self.embed.timestamp = self.original_timestamp or self.message.created_at
		else:
			self.embed.timestamp = None

		try:
			await self.message.edit(embed=self.embed)
		except (discord.HTTPException, discord.Forbidden) as e:
			# Put the flag back so the button keeps matching what the message shows.
			self.timestamp_on = not self.timestamp_on
			self.embed.timestamp = self.original_timestamp if self.timestamp_on else None
			logger.error(f"Failed to toggle embed timestamp: {e}", exc_info=True)
			await interaction.response.send_message(
				"❌ Could not update the embed just now. Please try again.", ephemeral=True
			)
			return

		self.toggle_button.label = "Timestamp: On" if self.timestamp_on else "Timestamp: Off"
		self.toggle_button.style = (
			discord.ButtonStyle.primary if self.timestamp_on else discord.ButtonStyle.secondary
		)
		await interaction.response.edit_message(view=self)

	async def _on_done(self, interaction: discord.Interaction) -> None:
		self._disable_all()
		await interaction.response.edit_message(content="✅ Done.", view=None)
		self.stop()


class EditEmbedModal(discord.ui.Modal, title="Edit Embed"):
	def __init__(self, message: discord.Message, guild_id: int, max_length: int, user_roles: Set[int],
	             allowed_features: Optional[Set[str]] = None, default_color: Optional[int] = None,
	             has_color_sets: bool = False, free_color_access: bool = False):
		super().__init__()
		self.message = message
		self.guild_id = guild_id
		self.user_roles = user_roles
		self.max_length = max_length
		self.default_color = default_color
		self.free_color_access = bool(free_color_access)
		_features = resolve_features(allowed_features)
		self.has_image_field = "image_field" in _features
		# Footer is offered on edit for exactly the members the create flow offers it
		# to. Without this a member could set a footer when creating an embed and then
		# never change or remove it, which is the asymmetry this closes.
		self.has_footer_field = "footer_field" in _features
		# Timestamp does NOT become a modal field - five components is Discord's hard
		# limit and title/description/thumbnail/footer/colour already fills it. It is
		# offered on the reply instead, via EditTimestampView, which is the same shape
		# the create flow uses. Gated on the same entitlement create gates it on.
		self.has_timestamp_field = "timestamp" in _features
		# Colors follow the same rule as the create flow: the guild-wide opt-out,
		# or a palette assigned to one of this member's roles. With neither, there
		# is nothing to choose from, so the field is not offered at all.
		self.has_color_field = self.free_color_access or bool(has_color_sets)
		embed = message.embeds[0] if message.embeds else discord.Embed()

		logger.info(f"Initializing embed edit modal for message {message.id}, guild {guild_id}, max_length={max_length}")

		self.title_input = discord.ui.TextInput(
			label="New Embed Title",
			placeholder="Leave empty to keep current title",
			default=embed.title or "",
			required=False,
			max_length=256,
		)
		self.description_input = discord.ui.TextInput(
			label="New Embed Description",
			placeholder=f"Leave empty to keep current description (Max {self.max_length} characters)",
			style=discord.TextStyle.paragraph,
			default=embed.description or "",
			required=False,
			max_length=self.max_length,
		)

		# Thumbnail input (gated by image_field feature)
		self.thumbnail_input = None
		if self.has_image_field:
			self.thumbnail_input = discord.ui.TextInput(
				label="New Embed Thumbnail URL",
				placeholder="URL, 'pp' for profile picture, 'none' to remove, empty to keep",
				default=(embed.thumbnail.url if getattr(embed, "thumbnail", None) else ""),
				required=False,
			)

		# Footer input (gated by the footer_field feature)
		self.footer_input = None
		if self.has_footer_field:
			self.footer_input = discord.ui.TextInput(
				label="New Embed Footer",
				placeholder="Footer text, 'none' to remove, empty to keep",
				style=discord.TextStyle.paragraph,
				default=(embed.footer.text if getattr(embed, "footer", None) else "") or "",
				required=False,
				max_length=MAX_FOOTER_LENGTH,
			)

		# Color input (gated by free color access or an assigned palette)
		self.color_input = None
		if self.has_color_field:
			self.color_input = discord.ui.TextInput(
				label="New color",
				placeholder="Choose a new color by hex (#RRGGBB) or allowed name",
				default=(f"#{embed.color.value:06x}" if embed.color else ""),
				required=False,
				max_length=32,
			)

		# Five components is Discord's hard limit for a modal, and title, description,
		# thumbnail, footer and color is exactly five. Anything further has to go on a
		# view after submit, which is how the create flow handles the timestamp toggle.
		self.add_item(self.title_input)
		self.add_item(self.description_input)
		if self.thumbnail_input:
			self.add_item(self.thumbnail_input)
		if self.footer_input:
			self.add_item(self.footer_input)
		if self.color_input:
			self.add_item(self.color_input)

	async def on_submit(self, interaction: discord.Interaction):
		with log_context(logger, f"embed edit submission for message {self.message.id}", logging.INFO):
			logger.info(f"Embed edit submitted by user {interaction.user.id} for message {self.message.id}")

			original_embed = self.message.embeds[0] if self.message.embeds else discord.Embed()
			embed = original_embed.copy()

			changed = False
			changes_made = []

			# Update Title
			if self.title_input.value and self.title_input.value != (original_embed.title or ""):
				embed.title = self.title_input.value
				changed = True
				changes_made.append("title")

			# Update Description
			if self.description_input.value and self.description_input.value != (original_embed.description or ""):
				if len(self.description_input.value) > self.max_length:
					await interaction.response.send_message(
						f"❌ Description exceeds maximum length of {self.max_length} characters.",
						ephemeral=True,
					)
					return

				embed.description = self.description_input.value
				changed = True
				changes_made.append("description")

			# Handle Thumbnail (only if image_field feature is enabled)
			if self.has_image_field and self.thumbnail_input:
				thumb_val = (self.thumbnail_input.value or "").strip()
				if thumb_val:
					if thumb_val.lower() == "none":
						embed.set_thumbnail(url=None)
						changed = True
						changes_made.append("thumbnail_removed")
					elif thumb_val.lower() == "pp":
						avatar = interaction.user.avatar
						avatar_url = avatar.url if avatar else interaction.user.default_avatar.url
						embed.set_thumbnail(url=avatar_url)
						changed = True
						changes_made.append("thumbnail_set")
					elif _is_valid_image_url(thumb_val):
						embed.set_thumbnail(url=thumb_val)
						changed = True
						changes_made.append("thumbnail_set")
					else:
						await interaction.response.send_message(
							"❌ Invalid thumbnail URL. Provide a valid https image URL, 'pp' for profile picture, or 'none' to remove.",
							ephemeral=True,
						)
						return

			# Handle Footer (only if the footer_field feature is enabled). Same
			# convention as the thumbnail above: 'none' removes it, empty keeps what
			# is already there, anything else replaces it. Without an explicit remove
			# word a footer could be set but never cleared.
			if self.has_footer_field and self.footer_input:
				footer_val = (self.footer_input.value or "").strip()
				current_footer = (
					original_embed.footer.text
					if getattr(original_embed, "footer", None) and original_embed.footer.text
					else ""
				)
				if footer_val.lower() == "none":
					if current_footer:
						# remove_footer(), NOT set_footer(text=None). Unlike set_thumbnail,
						# set_footer does not treat None as "remove" - it resets the footer
						# to an EMPTY object, which serializes as "footer": {} and Discord
						# rejects for a missing footer.text. Do not make this match the
						# thumbnail line above; the two APIs genuinely differ.
						embed.remove_footer()
						changed = True
						changes_made.append("footer_removed")
				elif footer_val and footer_val != current_footer:
					if len(footer_val) > MAX_FOOTER_LENGTH:
						await interaction.response.send_message(
							f"❌ Footer text is limited to {MAX_FOOTER_LENGTH} characters.",
							ephemeral=True,
						)
						return
					# Preserve the icon: set_footer replaces the whole footer object, so
					# passing only text would silently drop an icon the embed already had.
					embed.set_footer(
						text=footer_val,
						icon_url=(
							original_embed.footer.icon_url
							if getattr(original_embed, "footer", None)
							else None
						),
					)
					changed = True
					changes_made.append("footer")

			# Handle Color (per-guild)
			allowed_colors = await get_allowed_colors(self.guild_id, self.user_roles)

			if self.color_input is not None and self.color_input.value:
				color_str = self.color_input.value.strip()
				color_key = color_str.lower()

				if color_key in allowed_colors:
					new_color_val = allowed_colors[color_key]
				else:
					parsed = _parse_color(color_str)
					if parsed is None:
						await interaction.response.send_message(
							f"❌ Invalid color '{color_str}'. Use a valid hex color or an allowed name.",
							ephemeral=True,
						)
						return
					new_color_val = parsed

					# Any hex is fine when the guild has opened colors up; with
					# that off, it has to be one of the member's palette colors.
					if not self.free_color_access and new_color_val not in allowed_colors.values():
						await interaction.response.send_message(
							f"❌ Color '{color_str}' is not authorized for your roles.",
							ephemeral=True,
						)
						return

				if not embed.color or embed.color.value != new_color_val:
					embed.color = discord.Color(new_color_val)
					changed = True
					changes_made.append("color")

			# The timestamp control rides the REPLY, because the modal has no room for
			# it. It is built even when nothing else changed: toggling the timestamp is
			# a legitimate reason to open /embed edit on its own, and requiring some
			# other edit first to reach the button would be a worse flow than no button.
			timestamp_view = (
				EditTimestampView(
					message=self.message,
					embed=embed,
					author_id=interaction.user.id,
				)
				if self.has_timestamp_field
				else None
			)

			if not changed:
				if timestamp_view is None:
					await interaction.response.send_message(
						"ℹ️ Nothing to update. No changes were detected.",
						ephemeral=True,
					)
					return
				await interaction.response.send_message(
					"ℹ️ No changes were detected in the form. You can still switch the "
					"timestamp on or off below.",
					view=timestamp_view,
					ephemeral=True,
				)
				timestamp_view.bind_source(interaction)
				return

			logger.info(f"Applying embed changes: {', '.join(changes_made)} for message {self.message.id}")

			try:
				await self.message.edit(embed=embed)
				logger.info(f"Embed successfully updated by user {interaction.user.id} for message {self.message.id}")
				if timestamp_view is None:
					await interaction.response.send_message("✅ Embed updated successfully.", ephemeral=True)
				else:
					await interaction.response.send_message(
						"✅ Embed updated successfully.",
						view=timestamp_view,
						ephemeral=True,
					)
					timestamp_view.bind_source(interaction)
			except discord.HTTPException as e:
				logger.error(f"Discord HTTP error editing embed: {e.status} {e.text}", exc_info=True)
				error_msg = "❌ Failed to edit the embed. Please try again later."
				if interaction.response.is_done():
					await interaction.followup.send(error_msg, ephemeral=True)
				else:
					await interaction.response.send_message(error_msg, ephemeral=True)
			except discord.Forbidden:
				logger.error(f"Forbidden error editing embed for message {self.message.id}", exc_info=True)
				error_msg = "❌ I don't have permission to edit this message."
				if interaction.response.is_done():
					await interaction.followup.send(error_msg, ephemeral=True)
				else:
					await interaction.response.send_message(error_msg, ephemeral=True)
			except Exception as e:
				logger.error(f"Unexpected error editing embed: {e}", exc_info=True)
				error_msg = "❌ An unexpected error occurred. Please try again later."
				if interaction.response.is_done():
					await interaction.followup.send(error_msg, ephemeral=True)
				else:
					await interaction.response.send_message(error_msg, ephemeral=True)
