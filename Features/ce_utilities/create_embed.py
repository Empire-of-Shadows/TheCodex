import logging
import re
import time
from typing import Dict, Tuple, Set, Optional
import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks

from Features.ce_utilities.helpers.embed_config_loader import EmbedConfigLoader
from Features.ce_utilities.helpers.embed import EditEmbedModal
from Features.ce_utilities.helpers.embed_config_loader import EMBED_FEATURES
from Features.ce_utilities.helpers.embed_modal import (
    EmbedModal,
    get_allowed_colors,
    get_allowed_features,
    get_default_color,
    get_free_color_access,
    get_max_description_length,
    get_user_color_sets,
)
from storage.log import get_logger, log_context, log_performance
from storage.settings.config_manager import get_config
from admin.setup_notice import send_setup_notice, setup_notice_embed

logger = get_logger("CreateEmbed")

# Global embed config loader - initialized on cog load (no db_manager needed)
embed_config: Optional[EmbedConfigLoader] = None

# Authorization cache (message_id -> {"user_id": int, "expires": float})
authorization_cache: Dict[int, Dict[str, int | float]] = {}

# Hardcoded cache constants
MAX_CACHE_ENTRIES = 2000
CACHE_DURATION = 3600


async def is_admin_check(interaction: Interaction) -> bool:
    """
    Return True if the user is an admin or has a configured admin role.
    """
    if interaction.user.guild_permissions.administrator:
        return True

    guild_config = await get_config(interaction.guild.id)
    user_role_ids = {role.id for role in interaction.user.roles}
    admin_set = set(guild_config.roles["admin_role_ids"])

    return bool(user_role_ids & admin_set)


def has_embed_permissions():
    """
    App command check for embed creation permissions.
    Uses dynamic role configuration from guild config.
    """
    async def predicate(interaction: Interaction) -> bool:
        if not interaction.guild:
            return False

        if interaction.user.guild_permissions.administrator:
            return True

        guild_config = await get_config(interaction.guild.id)
        user_role_ids = {role.id for role in interaction.user.roles}

        if user_role_ids & set(guild_config.roles["admin_role_ids"]):
            return True

        tier_role_ids = set(guild_config.get_all_tier_role_ids())
        if user_role_ids & tier_role_ids:
            return True

        return False

    return app_commands.check(predicate)


def _parse_message_ref(message_link_or_channel_id: str, message_id: Optional[str]) -> Tuple[int, int]:
    """
    Robustly parse a Discord message link or a pair of channel_id/message_id strings.
    Returns (channel_id, message_id) as integers or raises ValueError.
    """
    if message_id is None:
        link = message_link_or_channel_id.strip()
        pattern = r"(?:https?://)?(?:\w+\.)?discord(?:app)?\.com/channels/(?:@me|\d+)/(\d+)/(\d+)$"
        m = re.search(pattern, link)
        if m:
            return int(m.group(1)), int(m.group(2))
        parts = link.split("/")
        if len(parts) >= 2 and parts[-2].isdigit() and parts[-1].isdigit():
            return int(parts[-2]), int(parts[-1])
        raise ValueError("Invalid message link format.")
    if not message_link_or_channel_id.isdigit() or not message_id.isdigit():
        raise ValueError("Channel ID and Message ID must be numeric.")
    return int(message_link_or_channel_id), int(message_id)


async def _build_colors_embed(guild_id: int, user_roles: Set[int]) -> discord.Embed:
    """
    Build an embed listing allowed colors grouped by color set name (per-guild).
    """
    grouped = await embed_config.get_colors_grouped_by_set(guild_id, user_roles)

    embed = discord.Embed(
        title="Available Colors",
        description="Here are the embed colors you can use based on your roles.",
        color=discord.Color.blurple(),
    )
    for set_name, colors in grouped.items():
        lines = [f"`{name}`: #{code:06X}" for name, code in colors.items()]
        embed.add_field(name=set_name, value="\n".join(lines), inline=False)
    embed.set_footer(text="Note: Color usage is restricted by your roles.")

    return embed


def _build_unrestricted_colors_embed() -> discord.Embed:
    """The listing shown when this server has turned on free color access.

    Every member may type any hex in that state, so the listing has to say so.
    """
    embed = discord.Embed(
        title="Available Colors",
        description=(
            "This server lets everyone pick their own embed color, so you can use "
            "**any** color you like.\n\n"
            "Type a hex code in the Color field, for example `#FF0000` or `#5865F2`."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="If your roles also come with color palettes, you can pick from those too.")
    return embed


def _build_no_palette_colors_embed() -> discord.Embed:
    """The listing shown when colors are role-restricted and the member has none.

    Strict is the default: with no palette assigned to any of their roles, the
    member gets no color choice at all and their embeds use the server's default
    color. Saying that plainly beats showing an empty list.
    """
    embed = discord.Embed(
        title="Available Colors",
        description=(
            "Embed colors on this server come with your roles, and none of yours "
            "has a color palette yet.\n\n"
            "Your embeds will use the server's default color. If you think you "
            "should have a palette, ask a server admin."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Color palettes are handed out per role by the server admins.")
    return embed


# Only the flags the builder actually honours are listed. Anything not here does
# nothing, so advertising it would be a promise the builder cannot keep.
FEATURE_DESCRIPTIONS = {
    "basic_embed": "Create embeds with a title, description, and color",
    "image_field": "Add a thumbnail image to your embed",
    "footer_field": "Add footer text to your embed",
    "timestamp": "Show the time your embed was created, next to the footer",
}


async def _build_features_embed(
    guild_id: int,
    user_roles: Set[int],
    *,
    guild: Optional[discord.Guild] = None,
    viewer: Optional[discord.Member] = None,
) -> discord.Embed:
    """
    Build an embed showing which embed features the member can use.

    Access is decided per feature, not per member: a feature no role was given
    is open to everyone, and a feature that was given to roles belongs only to
    the members holding one. The listing shows all three outcomes so a member
    can tell "everyone gets this" from "you earned this" from "not yours yet".

    guild/viewer are kept on the signature for the caller; they are no longer
    read now that every state has a plain-language line of its own.
    """
    states = await embed_config.describe_feature_access(guild_id, user_roles)

    available_lines = []
    locked_lines = []
    for name in EMBED_FEATURES:
        description = FEATURE_DESCRIPTIONS[name]
        state = states.get(name, "open")
        if state == "open":
            available_lines.append(f"{description} - open to everyone")
        elif state == "granted":
            available_lines.append(f"{description} - unlocked by your roles")
        else:
            locked_lines.append(f"{description} - needs a role you do not have yet")

    embed = discord.Embed(title="Available Features", color=discord.Color.green())

    if available_lines:
        embed.description = "Embed features you can use right now:\n\n" + "\n".join(available_lines)
    else:
        embed.description = "None of the embed features are available to your roles yet."

    if locked_lines:
        embed.add_field(
            name="Not available to you yet",
            value="\n".join(locked_lines),
            inline=False,
        )
        embed.set_footer(text="Upgrade your role to unlock more features!")
    else:
        embed.set_footer(text="You have every embed feature this server offers.")

    return embed


class EmbedGroup(commands.GroupCog, name="embed", description="Create and edit embeds with role-based limits"):
    """
    Group cog providing:
    - /embed create
    - /embed edit
    - /embed colors (lists allowed colors)
    - /embed features (lists available features)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Initializing EmbedGroup cog")
        self.cleanup_cache.start()
        logger.info("EmbedGroup cog initialized successfully")

    def cog_unload(self) -> None:
        logger.info("Unloading EmbedGroup cog")
        self.cleanup_cache.cancel()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Turn a failed embed-permission check into a message that explains the fix.

        Without this the global handler answers a bare "Command Unavailable", which
        on a fresh server is misleading - nothing is wrong, embed access simply has
        not been handed to any role yet.
        """
        if not isinstance(error, app_commands.CheckFailure):
            raise error

        embed = await setup_notice_embed(
            interaction.guild,
            what="embed access for your roles",
            path="Embed Settings -> Role Tier Mapping",
            viewer=interaction.user if isinstance(interaction.user, discord.Member) else None,
            detail=(
                "Embed commands are opened up per role. Yours has not been given "
                "access yet."
            ),
            title="Embed Access Required",
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.debug(f"Could not deliver embed permission notice: {e}")

    @tasks.loop(minutes=10)
    async def cleanup_cache(self):
        """Periodically remove expired entries from the authorization cache."""
        now = time.time()
        expired_keys = [key for key, data in authorization_cache.items() if data["expires"] <= now]

        for key in expired_keys:
            del authorization_cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired entries in the authorization cache")

    @cleanup_cache.before_loop
    async def _before_cleanup_cache(self):
        await self.bot.wait_until_ready()

    async def update_cache(self, user_id: int, message_id: int):
        """
        Add message ownership to the cache and enforce a soft cap to avoid unbounded growth.
        """
        if len(authorization_cache) >= MAX_CACHE_ENTRIES:
            oldest = sorted(authorization_cache.items(), key=lambda kv: kv[1]["expires"])[:50]
            for mid, _ in oldest:
                authorization_cache.pop(mid, None)

        authorization_cache[message_id] = {
            "user_id": user_id,
            "expires": time.time() + CACHE_DURATION,
        }

    # /embed create
    @app_commands.command(
        name="create",
        description="Create an embed via modal. Role-based description length and color access."
    )
    @has_embed_permissions()
    async def create(self, interaction: discord.Interaction):
        """
        Open a modal to create an embed. On success, the created message is cached
        to allow the author to edit it for a limited time.
        """
        with log_context(logger, f"embed_create_command", logging.INFO):
            logger.info(f"Command /embed create invoked by {interaction.user} in guild {interaction.guild_id}")
            user_roles = {role.id for role in interaction.user.roles}
            guild_id = interaction.guild.id

            try:
                _embed_config = await get_config(guild_id)
                if not _embed_config.embed.get("enabled", False):
                    await send_setup_notice(
                        interaction,
                        what="embed creation",
                        path="Embed Settings -> Role Tier Mapping",
                        detail=(
                            "Embeds unlock once at least one role is mapped to a tier, "
                            "which is what decides who can build embeds and how long "
                            "their descriptions can be."
                        ),
                    )
                    return

                # Check basic_embed feature access. Guild-keyed: a feature nobody
                # was granted is open to everyone, but once it names roles only
                # those role holders have it.
                allowed_features = await get_allowed_features(guild_id, user_roles)
                if "basic_embed" not in allowed_features:
                    await interaction.response.send_message(
                        "Your role does not have access to embed creation.", ephemeral=True
                    )
                    return

                # Pre-compute everything the modal cannot await for itself
                max_length = await get_max_description_length(guild_id, user_roles)
                default_color = await get_default_color(guild_id)
                color_sets = await get_user_color_sets(guild_id, user_roles)
                free_colors = await get_free_color_access(guild_id)
                await self._open_create_modal(
                    interaction, guild_id, max_length, user_roles, allowed_features,
                    default_color, color_sets, free_colors,
                )
            except Exception as e:
                logger.error(f"Error presenting create modal to {interaction.user}: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An internal error occurred while opening the modal.", ephemeral=True
                    )

    # /embed colors
    @app_commands.command(
        name="colors",
        description="List the embed colors you are allowed to use."
    )
    @has_embed_permissions()
    async def colors(self, interaction: discord.Interaction):
        """Display a list of accessible colors based on user roles."""
        with log_context(logger, f"embed_colors_command", logging.INFO):
            user_roles = {role.id for role in interaction.user.roles}
            guild_id = interaction.guild.id

            # Three states, and the listing must match what the builder does:
            # free access on -> any color; off with a palette -> that palette;
            # off without one -> no color choice at all.
            if await get_free_color_access(guild_id):
                embed = _build_unrestricted_colors_embed()
            elif await get_allowed_colors(guild_id, user_roles):
                embed = await _build_colors_embed(guild_id, user_roles)
            else:
                embed = _build_no_palette_colors_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # /embed features
    @app_commands.command(
        name="features",
        description="List the embed features you can access based on your roles."
    )
    @has_embed_permissions()
    async def features(self, interaction: discord.Interaction):
        """Display available features based on user roles."""
        with log_context(logger, f"embed_features_command", logging.INFO):
            user_roles = {role.id for role in interaction.user.roles}
            guild_id = interaction.guild.id

            embed = await _build_features_embed(
                guild_id, user_roles, guild=interaction.guild, viewer=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # /embed edit
    @app_commands.command(
        name="edit",
        description="Edit an existing bot embed by link or by channel/message IDs."
    )
    @app_commands.describe(
        message_link_or_channel_id="A full message link, or a channel ID if message_id is provided",
        message_id="Message ID (optional if a full message link is provided)"
    )
    async def edit(
            self,
            interaction: discord.Interaction,
            message_link_or_channel_id: str,
            message_id: Optional[str] = None,
    ):
        """
        Edit a bot-authored embed if authorized. Non-admins must be the creator of the embed
        and within the authorization window.
        """
        with log_context(logger, f"embed_edit_command", logging.INFO):
            logger.info(f"Command /embed edit invoked by {interaction.user}")

            try:
                channel_id, parsed_message_id = _parse_message_ref(message_link_or_channel_id, message_id)
            except ValueError:
                await interaction.response.send_message("❌ Invalid message link or ID format.", ephemeral=True)
                return

            if await is_admin_check(interaction):
                pass
            else:
                now = time.time()
                if parsed_message_id not in authorization_cache:
                    await interaction.response.send_message(
                        "❌ You cannot edit this embed because the session has expired. Please recreate it using `/embed create`.",
                        ephemeral=True,
                    )
                    return

                data = authorization_cache[parsed_message_id]
                if data["user_id"] != interaction.user.id:
                    await interaction.response.send_message("❌ You are not authorized to edit this embed.",
                                                            ephemeral=True)
                    return
                if data["expires"] <= now:
                    del authorization_cache[parsed_message_id]
                    await interaction.response.send_message("❌ Your authorization session has expired.", ephemeral=True)
                    return

            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                message = await channel.fetch_message(parsed_message_id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Message or channel not found.", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.response.send_message("❌ Access to this channel or message is forbidden.",
                                                        ephemeral=True)
                return
            except Exception as e:
                logger.error(f"Fetch error for channel {channel_id} / message {parsed_message_id}: {e}", exc_info=True)
                await interaction.response.send_message("❌ Failed to fetch the message.", ephemeral=True)
                return

            if not message.author.bot or not message.embeds:
                await interaction.response.send_message("❌ This is not a valid bot embed.", ephemeral=True)
                return

            user_roles = {role.id for role in interaction.user.roles}
            guild_id = interaction.guild.id

            # Pre-compute max_length, features, colors and default color before
            # constructing the modal - the same gates the create flow applies.
            max_length = await get_max_description_length(guild_id, user_roles)
            allowed_features = await get_allowed_features(guild_id, user_roles)
            default_color = await get_default_color(guild_id)
            color_sets = await get_user_color_sets(guild_id, user_roles)
            free_colors = await get_free_color_access(guild_id)

            try:
                await interaction.response.send_modal(
                    EditEmbedModal(
                        message, guild_id, max_length, user_roles, allowed_features,
                        default_color, has_color_sets=bool(color_sets),
                        free_color_access=free_colors,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to send edit modal: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Failed to process the edit modal.", ephemeral=True)

    async def _open_create_modal(self, interaction: discord.Interaction, guild_id: int, max_length: int,
                                user_roles: Set[int], allowed_features: Optional[Set[str]] = None,
                                default_color: Optional[int] = None,
                                color_sets: Optional[list] = None,
                                free_color_access: bool = False):
        """Present the embed creation modal and attach a callback to update the authorization cache."""
        try:
            modal = EmbedModal(
                guild_id=guild_id,
                max_length=max_length,
                user_roles=user_roles,
                allowed_features=allowed_features,
                default_color=default_color,
                color_sets=color_sets,
                free_color_access=free_color_access,
                cache_update_callback=self.update_cache,
            )
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Error opening create modal for {interaction.user}: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An internal error occurred. Please contact the admin.", ephemeral=True
                )

    # Unified error handlers for subcommands
    @create.error
    async def _create_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            if isinstance(error, app_commands.CheckFailure):
                await interaction.response.send_message("❌ You don't have permission to use this command.",
                                                        ephemeral=True)
            else:
                logger.error(f"Unhandled error in /embed create: {error}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Something went wrong. Please try again later.",
                                                            ephemeral=True)
        except discord.errors.NotFound:
            pass
        except Exception as inner_e:
            logger.error(f"Error in create error handler: {inner_e}", exc_info=True)

    @edit.error
    async def _edit_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            if isinstance(error, app_commands.CheckFailure):
                await interaction.response.send_message("❌ You're on cooldown or lack permission to use this command.",
                                                        ephemeral=True)
            else:
                logger.error(f"Unhandled error in /embed edit: {error}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Something went wrong. Please try again later.",
                                                            ephemeral=True)
        except discord.errors.NotFound:
            pass
        except Exception as inner_e:
            logger.error(f"Error in edit error handler: {inner_e}", exc_info=True)

    @colors.error
    async def _colors_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            if isinstance(error, app_commands.CheckFailure):
                await interaction.response.send_message("❌ You don't have permission to view colors.", ephemeral=True)
            else:
                logger.error(f"Unhandled error in /embed colors: {error}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Something went wrong. Please try again later.",
                                                            ephemeral=True)
        except discord.errors.NotFound:
            pass
        except Exception as inner_e:
            logger.error(f"Error in colors error handler: {inner_e}", exc_info=True)

    @features.error
    async def _features_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            if isinstance(error, app_commands.CheckFailure):
                await interaction.response.send_message("❌ You don't have permission to view features.", ephemeral=True)
            else:
                logger.error(f"Unhandled error in /embed features: {error}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Something went wrong. Please try again later.",
                                                            ephemeral=True)
        except discord.errors.NotFound:
            pass
        except Exception as inner_e:
            logger.error(f"Error in features error handler: {inner_e}", exc_info=True)


async def setup(bot: commands.Bot):
    global embed_config

    logger.info("Setting up EmbedGroup cog")

    # Initialize embed config loader (no db_manager needed, uses storage.config_manager)
    embed_config = EmbedConfigLoader()
    logger.info("Embed configuration loader initialized (storage-backed)")

    # Set the config in the modal module
    from Features.ce_utilities.helpers import embed_modal
    embed_modal.set_embed_config(embed_config)
    logger.info("Embed configuration set in modal module")

    await bot.add_cog(EmbedGroup(bot))
    logger.info("EmbedGroup cog setup completed")
