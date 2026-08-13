# Python
import logging
import re
from typing import Optional, Set, Callable, Awaitable, TYPE_CHECKING
import discord

from Features.ce_utilities.helpers.embed_confirm import EmbedConfirmView, PREVIEW_TEXT
from Features.ce_utilities.helpers.embed_config_loader import EMBED_FEATURES
from storage.log import get_logger, log_context, log_performance

if TYPE_CHECKING:
    from Features.ce_utilities.helpers.embed_config_loader import EmbedConfigLoader

logger = get_logger("EmbedModal", level=logging.INFO)

# Discord's ceiling for an embed footer.
MAX_FOOTER_LENGTH = 2048

# Will be set by create_embed.py when the cog loads
_embed_config: Optional['EmbedConfigLoader'] = None

def set_embed_config(config: 'EmbedConfigLoader') -> None:
    """Set the global embed config loader instance."""
    global _embed_config
    _embed_config = config


def resolve_features(allowed_features: Optional[Set[str]]) -> Set[str]:
    """Normalize a caller-supplied entitlement set.

    Entitlements are decided per FEATURE against the guild's config (see
    ``EmbedConfigLoader.describe_feature_access``), so membership here is
    literal: a feature absent from the set is denied. ``None`` means the caller
    did not resolve anything and is only used by direct constructions in tests
    and by defaults - it opens every feature, and the submit path re-resolves
    from the guild config regardless, so it can never widen real access.
    """
    if allowed_features is None:
        return set(EMBED_FEATURES)
    return set(allowed_features)


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


async def get_user_color_sets(guild_id: int, user_roles: Set[int]) -> list[dict]:
    """Get the color sets a user's roles/tiers grant, dropping empty ones.

    An empty result means no set restricts the member, which is what puts the
    free-rein hex field in the modal instead of the color pickers on the
    confirm step.
    """
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")

    sets = await _embed_config.get_user_color_sets(guild_id, user_roles)
    return [cs for cs in sets if cs.get("colors")]


async def get_allowed_features(guild_id: int, user_roles: Set[int]) -> Set[str]:
    """Get the embed features this member may use in this guild."""
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")
    return await _embed_config.get_allowed_features(guild_id, user_roles)


async def get_free_color_access(guild_id: int) -> bool:
    """Whether this guild lets every member use any hex color."""
    if _embed_config is None:
        raise RuntimeError("Embed config not initialized. Call set_embed_config() first.")
    return await _embed_config.get_free_color_access(guild_id)


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
                 allowed_features: Optional[Set[str]] = None,
                 default_color: Optional[int] = None,
                 color_sets: Optional[list[dict]] = None,
                 free_color_access: bool = False,
                 cache_update_callback: Optional[Callable[[int, int], Awaitable[None]]] = None):
        """
        Modal for creating an embed. Text only - color pickers and the timestamp
        toggle live on the confirm step that this modal's submit opens, because a
        modal's own components are static until submit.

        :param guild_id: The guild ID for per-guild config lookups.
        :param max_length: Pre-computed max description length.
        :param user_roles: The roles of the user invoking the modal.
        :param allowed_features: Features this member may use, resolved against
                                 the guild's per-feature config.
        :param default_color: Server default embed color (int), or None.
        :param color_sets: Color sets assigned to this member's roles/tiers.
        :param free_color_access: Guild-wide opt-out that lets every member type
                                  any hex. Off by default, in which case colors
                                  follow the assigned sets strictly.
        :param cache_update_callback: A callback function to update the authorization cache.
        """
        with log_context(logger, "Initializing EmbedModal", level=logging.DEBUG):
            super().__init__(title="Create Embed")

            logger.info(f"EmbedModal initialized with {len(user_roles)} user roles, max_length={max_length}")

            features = resolve_features(allowed_features)

            self.guild_id = guild_id
            self.default_color = default_color
            self.color_sets = [cs for cs in (color_sets or []) if cs.get("colors")]
            self.free_color_access = bool(free_color_access)
            self.has_image_field = "image_field" in features
            self.has_footer_field = "footer_field" in features
            self.has_timestamp = "timestamp" in features
            # The hex field is the guild-wide opt-out only. With it off, colors
            # come from the member's assigned sets on the confirm step - and a
            # member with no sets gets no color control at all.
            self.has_hex_input = self.free_color_access

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

            # Footer input (gated by footer_field feature)
            self.footer_input = None
            if self.has_footer_field:
                self.footer_input = discord.ui.TextInput(
                    label="Footer",
                    placeholder="Footer text (optional)",
                    style=discord.TextStyle.paragraph,
                    required=False,
                    max_length=MAX_FOOTER_LENGTH,
                )
                self.add_item(self.footer_input)

            # Color input - only when the guild has opened colors up to everyone.
            self.color_input = None
            if self.has_hex_input:
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

                # Entitlements are re-resolved here rather than trusted from the
                # modal's construction: roles can change between opening the
                # modal and submitting it, and the gated fields must be enforced
                # on the way in, not only hidden on the way out.
                with log_context(logger, "Re-checking feature entitlements", level=logging.DEBUG):
                    current_features = await get_allowed_features(self.guild_id, self.user_roles)
                    may_use_image = "image_field" in current_features
                    may_use_footer = "footer_field" in current_features
                    may_use_timestamp = "timestamp" in current_features
                    free_colors = await get_free_color_access(self.guild_id)

                # Retrieve and log field values
                with log_context(logger, "Processing input field values", level=logging.DEBUG):
                    title = self.title_input.value or None
                    description = self.description_input.value
                    color_input_raw = (self.color_input.value or "").strip() if self.color_input else ""
                    footer_raw = (self.footer_input.value or "").strip() if self.footer_input else ""

                    logger.debug(f"Input values - Title: {'Set' if title else 'None'}, "
                                 f"Description: {len(description)} chars, "
                                 f"Footer: {len(footer_raw)} chars, "
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
                            # With free color access on, any hex is legitimate.
                            # With it off, a typed color must be one the member's
                            # assigned sets actually contain.
                            if not free_colors and parsed not in allowed_colors.values():
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
                    thumbnail_url_raw = (self.thumbnail_input.value or "").strip() if self.thumbnail_input else ""
                    if thumbnail_url_raw and not may_use_image:
                        error_msg = "Your role does not have access to embed images."
                        logger.warning(f"Thumbnail rejected for user {interaction.user}: not entitled")
                        await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                        return
                    if may_use_image:
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

                # Footer (gated by footer_field, enforced here as well as hidden)
                with log_context(logger, "Processing footer configuration"):
                    if footer_raw:
                        if not may_use_footer:
                            error_msg = "Your role does not have access to embed footers."
                            logger.warning(f"Footer rejected for user {interaction.user}: not entitled")
                            await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                            return
                        if len(footer_raw) > MAX_FOOTER_LENGTH:
                            error_msg = f"Footer text is limited to {MAX_FOOTER_LENGTH} characters."
                            logger.warning(f"Footer too long for user {interaction.user}")
                            await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
                            return
                        embed.set_footer(text=footer_raw)

                # Confirm step: the real embed as a live preview, plus the
                # controls that a modal cannot carry (dependent color selects,
                # the timestamp toggle, Post/Cancel).
                with log_context(logger, "Presenting embed confirm step"):
                    view = EmbedConfirmView(
                        embed=embed,
                        author_id=interaction.user.id,
                        color_sets=self.color_sets,
                        allow_timestamp=may_use_timestamp,
                        cache_update_callback=self.cache_update_callback,
                    )
                    await interaction.response.send_message(
                        content=PREVIEW_TEXT, embed=embed, view=view, ephemeral=True
                    )
                    view.bind_source(interaction)
                    logger.info(f"Embed confirm step shown to {interaction.user} ({interaction.user.id})")

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
