# Python
import logging
import re
from typing import Optional, Set

import discord
from Features.ce_utilities.helpers.embed_modal import get_allowed_colors, get_max_description_length
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


class EditEmbedModal(discord.ui.Modal, title="Edit Embed"):
	def __init__(self, message: discord.Message, guild_id: int, max_length: int, user_roles: Set[int],
	             user_features: Optional[Set[str]] = None, default_color: Optional[int] = None):
		super().__init__()
		self.message = message
		self.guild_id = guild_id
		self.user_roles = user_roles
		self.max_length = max_length
		self.default_color = default_color
		self.has_image_field = user_features is None or "image_field" in user_features
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

		self.color_input = discord.ui.TextInput(
			label="New color",
			placeholder="Choose a new color by hex (#RRGGBB) or allowed name",
			default=(f"#{embed.color.value:06x}" if embed.color else ""),
			required=False,
			max_length=32,
		)

		self.add_item(self.title_input)
		self.add_item(self.description_input)
		if self.thumbnail_input:
			self.add_item(self.thumbnail_input)
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

			# Handle Color (per-guild)
			allowed_colors = await get_allowed_colors(self.guild_id, self.user_roles)

			if self.color_input.value:
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

					if allowed_colors and new_color_val not in allowed_colors.values():
						await interaction.response.send_message(
							f"❌ Color '{color_str}' is not authorized for your roles.",
							ephemeral=True,
						)
						return

				if not embed.color or embed.color.value != new_color_val:
					embed.color = discord.Color(new_color_val)
					changed = True
					changes_made.append("color")

			if not changed:
				await interaction.response.send_message(
					"ℹ️ Nothing to update. No changes were detected.",
					ephemeral=True,
				)
				return

			logger.info(f"Applying embed changes: {', '.join(changes_made)} for message {self.message.id}")

			try:
				await self.message.edit(embed=embed)
				logger.info(f"Embed successfully updated by user {interaction.user.id} for message {self.message.id}")
				await interaction.response.send_message("✅ Embed updated successfully.", ephemeral=True)
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
