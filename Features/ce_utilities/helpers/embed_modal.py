# Python
import logging
import re
from typing import Optional, Set, Callable, Awaitable, TYPE_CHECKING
import discord

from storage.logging import get_logger, log_context, log_performance

if TYPE_CHECKING:
    from Features.ce_utilities.helpers.embed_config_loader import EmbedConfigLoader

logger = get_logger("EmbedModal", level=logging.INFO, colored_console=True)

# Will be set by create_embed.py when the cog loads
_embed_config: Optional['EmbedConfigLoader'] = None

def set_embed_config(config: 'EmbedConfigLoader') -> None:
    """Set the global embed config loader instance."""
    global _embed_config
    _embed_config = config


async def get_max_description_length(guild_id: int, user_roles: Set[int]) -> int:
    """
    Return the maximum embed description length allowed for the given roles.
    Roles do not stack; we choose the highest limit among the user's roles.
    The absolute ceiling is aligned to Discord's 4000 TextInput limit.
    """
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")

    with log_context(logger, f"Calculating max description length for {len(user_roles)} roles", level=logging.DEBUG):
        allowed = await _embed_config.get_description_limit_for_user(guild_id, user_roles)
        final_limit = min(allowed, 4000)

        logger.debug(f"Max allowed: {allowed}, final limit: {final_limit}")
        return final_limit


async def get_allowed_colors(guild_id: int, user_roles: Set[int]) -> dict[str, int]:
    """Get allowed colors for user based on their roles in a guild.

    Resolves tier assignments and direct role assignments from the Color Set DB.
    """
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")

    with log_context(logger, f"Determining allowed colors for {len(user_roles)} roles", level=logging.DEBUG):
        allowed_colors = await _embed_config.get_available_colors(guild_id, user_roles)
        logger.info(f"User has access to {len(allowed_colors)} colors in guild {guild_id}")
        return allowed_colors


async def get_default_color(guild_id: int) -> Optional[int]:
    """Get the server default embed color, or None if not set."""
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")
    return await _embed_config.get_default_color(guild_id)

def _is_valid_image_url(url: str) -> bool:
    """Validate if URL is a valid image URL."""
    logger.debug(f"Validating image URL: {url[:50]}{'...' if len(url) > 50 else ''}")

    if not url or not url.startswith("https://"):
        logger.debug(f"URL validation failed: Invalid protocol or empty URL")
        return False

    is_valid = bool(re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)(?:\?.*)?$", url, flags=re.IGNORECASE))
    logger.debug(f"URL validation result: {is_valid}")
    return is_valid


def _parse_color_to_int(color_str: str) -> Optional[int]:
    """
    Parse color string to integer.
    Accepts:
    - #RRGGBB, #RGB
    - 0xRRGGBB
    - RRGGBB
    Returns int or None if invalid.
    """
    logger.debug(f"Parsing color string: '{color_str}'")

    s = color_str.strip().lower()
    if not s:
        logger.debug("Empty color string provided")
        return None

    original_format = "unknown"
    if s.startswith("#"):
        s = s[1:]
        original_format = "hex with #"
    elif s.startswith("0x"):
        s = s[2:]
        original_format = "hex with 0x"
    else:
        original_format = "raw hex"

    if not re.fullmatch(r"[0-9a-f]{3}|[0-9a-f]{6}", s):
        logger.debug(f"Color validation failed: Invalid hex format for '{s}' (original format: {original_format})")
        return None

    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
        logger.debug(f"Expanded 3-digit hex to 6-digit: {s}")

    try:
        color_int = int(s, 16)
        logger.debug(
            f"Successfully parsed color '{color_str}' ({original_format}) to integer: {color_int} (0x{color_int:06X})")
        return color_int
    except ValueError as e:
        logger.warning(f"Failed to parse color '{color_str}' to integer: {e}")
        return None


class EmbedModal(discord.ui.Modal):
    def __init__(self, guild_id: int, max_length: int, user_roles: Set[int],
                 user_features: Optional[Set[str]] = None,
                 default_color: Optional[int] = None,
                 cache_update_callback: Optional[Callable[[int, int], Awaitable[None]]] = None):
        """
        Modal for creating an embed.

        :param guild_id: The guild ID for per-guild config lookups.
        :param max_length: Pre-computed max description length.
        :param user_roles: The roles of the user invoking the modal.
        :param user_features: Pre-computed set of feature names the user can access.
        :param default_color: Server default embed color (int), or None.
        :param cache_update_callback: A callback function to update the authorization cache.
        """
        with log_context(logger, "Initializing EmbedModal", level=logging.DEBUG):
            super().__init__(title="Create Embed")

            logger.info(f"EmbedModal initialized with {len(user_roles)} user roles, max_length={max_length}")

            self.guild_id = guild_id
            self.default_color = default_color
            self.has_image_field = user_features is None or "image_field" in user_features

            # Title input
            self.title_input = discord.ui.TextInput(
                label="Title",
                placeholder="Enter embed title (optional)",
                required=False,
                max_length=256,
            )
            self.add_item(self.title_input)

            # Description input
            self.description_input = discord.ui.TextInput(
                label="Description",
                placeholder=f"Enter embed description (up to {max_length} characters)",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=max_length,
            )
            self.add_item(self.description_input)

            # Thumbnail input (gated by image_field feature)
            self.thumbnail_input = None
            if self.has_image_field:
                self.thumbnail_input = discord.ui.TextInput(
                    label="Thumbnail URL",
                    placeholder="Image URL, 'pp' for profile picture, or leave empty for none",
                    required=False,
                )
                self.add_item(self.thumbnail_input)

            # Color input
            self.color_input = discord.ui.TextInput(
                label="Color",
                placeholder="Enter hex (e.g., #FF0000) or allowed name",
                required=False,
                max_length=32,
            )
            self.add_item(self.color_input)

            self.user_roles = user_roles
            self.cache_update_callback = cache_update_callback

            logger.info("EmbedModal initialization completed successfully")

    @log_performance("embed_modal_submission")
    async def on_submit(self, interaction: discord.Interaction):
        """
        Handle embed creation on modal submission.
        """
        operation_id = f"embed_{interaction.user.id}_{hash(str(interaction.created_at)) % 10000}"

        with log_context(logger, f"Processing embed modal submission [{operation_id}]"):
            logger.info(
                f"Modal submitted by {interaction.user} ({interaction.user.id}) in guild {interaction.guild} ({interaction.guild.id if interaction.guild else 'DM'})")

            try:
                # Get allowed colors for validation (per-guild)
                with log_context(logger, "Retrieving user permissions and colors", level=logging.DEBUG):
                    allowed_colors = await get_allowed_colors(self.guild_id, self.user_roles)
                    logger.debug(f"User has access to {len(allowed_colors)} allowed colors")

                # Retrieve and log field values
                with log_context(logger, "Processing input field values", level=logging.DEBUG):
                    title = self.title_input.value or None
                    description = self.description_input.value
                    color_input_raw = (self.color_input.value or "").strip()

                    logger.debug(f"Input values - Title: {'Set' if title else 'None'}, "
                                 f"Description: {len(description)} chars, "
                                 f"Color: '{color_input_raw}' {'Set' if color_input_raw else 'None'}")

                # Validate and process color
                with log_context(logger, "Processing color validation"):
                    embed_color_val: int
                    if not color_input_raw:
                        embed_color_val = self.default_color if self.default_color is not None else 0x000000
                        logger.debug(f"Using {'server default' if self.default_color is not None else 'black'} color: 0x{embed_color_val:06X}")
                    else:
                        lower_key = color_input_raw.lower()
                        if lower_key in allowed_colors:
                            embed_color_val = allowed_colors[lower_key]
                            logger.info(f"Using named color '{color_input_raw}' -> 0x{embed_color_val:06X}")
                        else:
                            parsed = _parse_color_to_int(color_input_raw)
                            if parsed is None:
                                error_msg = f"Invalid color '{color_input_raw}'. Please use a valid hex code or allowed name."
                                logger.warning(f"Color validation failed for user {interaction.user}: {error_msg}")
                                await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                                return
                            if allowed_colors and parsed not in allowed_colors.values():
                                error_msg = f"You are not authorized to use the color '{color_input_raw}'."
                                logger.warning(
                                    f"Color authorization failed for user {interaction.user}: {error_msg} - Color: 0x{parsed:06X}")
                                await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                                return
                            embed_color_val = parsed
                            logger.info(f"Using parsed color '{color_input_raw}' -> 0x{embed_color_val:06X}")

                # Create embed
                with log_context(logger, "Creating Discord embed"):
                    embed = discord.Embed(title=title, description=description, color=embed_color_val)

                # Set thumbnail logic (only if image_field feature is enabled)
                with log_context(logger, "Processing thumbnail configuration"):
                    if self.has_image_field:
                        thumbnail_url_raw = (self.thumbnail_input.value or "").strip() if self.thumbnail_input else ""
                        if thumbnail_url_raw.lower() in ("none", ""):
                            logger.debug("No thumbnail - field empty or set to 'none'")
                        elif thumbnail_url_raw.lower() == "pp":
                            avatar = interaction.user.avatar
                            avatar_url = avatar.url if avatar else interaction.user.default_avatar.url
                            embed.set_thumbnail(url=avatar_url)
                            logger.debug("Thumbnail set to user's profile picture")
                        elif thumbnail_url_raw:
                            if not _is_valid_image_url(thumbnail_url_raw):
                                error_msg = "Invalid thumbnail URL. Provide a valid https image URL, 'pp' for profile picture, or leave empty."
                                logger.warning(
                                    f"Thumbnail validation failed for user {interaction.user}: {error_msg}")
                                await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                                return
                            embed.set_thumbnail(url=thumbnail_url_raw)

                # Send embed
                with log_context(logger, "Sending embed message"):
                    await interaction.response.defer()
                    message = await interaction.followup.send(embed=embed)
                    logger.info(
                        f"Embed message sent successfully - Message ID: {message.id}")

                # Update cache if callback provided
                if self.cache_update_callback:
                    await self.cache_update_callback(interaction.user.id, message.id)

            except discord.Forbidden as e:
                logger.error(f"Permission error during embed submission by {interaction.user}: {e}", exc_info=True)
                await self._send_error_response(interaction,
                                                "❌ I don't have permission to send embeds in this channel.")
            except discord.HTTPException as e:
                logger.error(f"Discord API error during embed submission by {interaction.user}: HTTP {e.status} - {e.text}", exc_info=True)
                await self._send_error_response(interaction, "❌ Failed to send embed due to Discord API error.")

            except Exception as e:
                logger.exception(f"Unexpected error during embed submission by {interaction.user}: {e}")
                await self._send_error_response(interaction,
                                                "❌ An unexpected error occurred while processing your request.")

    async def _send_error_response(self, interaction: discord.Interaction, message: str):
        """Helper method to send error responses, handling both cases where response is done or not."""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error response to user {interaction.user}: {e}")
