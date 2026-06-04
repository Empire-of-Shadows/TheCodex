import logging
import re
import time
from typing import Dict, Tuple, Set, Optional
import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks

from Features.ce_utilities.helpers.embed_config_loader import EmbedConfigLoader
from Features.ce_utilities.helpers.embed import EditEmbedModal
from Features.ce_utilities.helpers.embed_modal import EmbedModal, get_max_description_length, get_allowed_colors, get_default_color
from utils.logger import get_logger, log_context, log_performance
from storage.config_manager import get_config

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

        if user_role_ids & set(guild_config.roles["mod_role_ids"]):
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


async def _build_features_embed(guild_id: int, user_roles: Set[int]) -> discord.Embed:
    """
    Build an embed showing available features for the user (per-guild).
    """
    feature_access = await embed_config.get_feature_access(guild_id)
    user_features = {
        feature_name
        for feature_name, allowed_roles in feature_access.items()
        if not user_roles.isdisjoint(allowed_roles)
    }

    embed = discord.Embed(
        title="Available Features",
        description="Here are the embed features you can access based on your roles:",
        color=discord.Color.green(),
    )

    feature_descriptions = {
        "basic_embed": "Create basic embeds with title, description, and color",
        "image_field": "Add images and thumbnails to embeds",
        "author_field": "Add author field with name and icon",
        "footer_field": "Add footer text to embeds",
        "timestamp": "Add timestamps to embeds"
    }

    features_text = []
    for feature in sorted(user_features):
        if feature in feature_descriptions:
            features_text.append(feature_descriptions[feature])

    if features_text:
        embed.description += "\n\n" + "\n".join(features_text)
    else:
        embed.description = "No features available for your role."

    embed.set_footer(text="Upgrade your role to unlock more features!")
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
                    await interaction.response.send_message(
                        "Embed creation is not enabled on this server.", ephemeral=True
                    )
                    return

                # Check basic_embed feature access
                user_features = await embed_config.get_user_features(guild_id, user_roles)
                if user_features and "basic_embed" not in user_features:
                    await interaction.response.send_message(
                        "Your role does not have access to embed creation.", ephemeral=True
                    )
                    return

                # Pre-compute max_length and default color before constructing modal
                max_length = await get_max_description_length(guild_id, user_roles)
                default_color = await get_default_color(guild_id)
                await self._open_create_modal(interaction, guild_id, max_length, user_roles, user_features, default_color)
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

            allowed_colors = await get_allowed_colors(guild_id, user_roles)
            if not allowed_colors:
                await interaction.response.send_message("❌ You do not have access to any colors.", ephemeral=True)
                return

            embed = await _build_colors_embed(guild_id, user_roles)
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

            embed = await _build_features_embed(guild_id, user_roles)
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

            # Pre-compute max_length, features, and default color before constructing modal
            max_length = await get_max_description_length(guild_id, user_roles)
            user_features = await embed_config.get_user_features(guild_id, user_roles)
            default_color = await get_default_color(guild_id)

            try:
                await interaction.response.send_modal(
                    EditEmbedModal(message, guild_id, max_length, user_roles, user_features, default_color)
                )
            except Exception as e:
                logger.error(f"Failed to send edit modal: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Failed to process the edit modal.", ephemeral=True)

    async def _open_create_modal(self, interaction: discord.Interaction, guild_id: int, max_length: int,
                                user_roles: Set[int], user_features: Optional[Set[str]] = None,
                                default_color: Optional[int] = None):
        """Present the embed creation modal and attach a callback to update the authorization cache."""
        try:
            modal = EmbedModal(
                guild_id=guild_id,
                max_length=max_length,
                user_roles=user_roles,
                user_features=user_features,
                default_color=default_color,
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
