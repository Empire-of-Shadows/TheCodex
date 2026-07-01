import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from collections import defaultdict
import aiohttp
import discord
from startup.bot import bot, TOKEN, s
from storage.discord import GuildSnapshotService
from storage.config_manager import get_config, GuildConfig
from storage.manager import db_manager
from storage.config_manager import get_guild_config_manager
from storage.logging import get_logger


class GuildEventHandler:
    """Handles all guild-related events with enhanced caching and rate limiting"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = get_logger("GuildEventHandler")

        # Enhanced guild-specific rate limiting storage
        self.dm_rate_limits: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            'count': 0,
            'last_reset': datetime.now(timezone.utc),
            'blocked_until': None,
            'total_attempts': 0,
            'first_attempt': None
        })

        # Caps concurrent gatekeep flows so a raid (many simultaneous joins)
        # can't fan out into an unbounded burst of DMs/kicks that trips
        # Discord's global rate limits.
        self._join_sem = asyncio.Semaphore(5)

        # Enhanced guild cache with more comprehensive data
        self.guild_cache: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            '_initialized': False,  # set True after the one-time baseline scan
            'member_count': 0,
            'bot_count': 0,
            'human_count': 0,  # NEW: Track human members separately
            'new_member_joins_today': 0,
            'kicks_today': 0,
            'last_activity': None,
            'voice_channels_active': 0,
            'recent_messages': 0,
            'moderation_actions': [],
            'member_retention_rate': 0.0,
            'popular_channels': {},
            'role_distribution': {},
            'timezone_distribution': {},
            'join_patterns': {
                'hourly': defaultdict(int),
                'daily': defaultdict(int),
                'weekly': defaultdict(int)
            },
            'security_metrics': {
                'suspicious_joins': 0,
                'account_age_violations': 0,
                'rapid_joins': 0
            }
        })

        # Rate limit configuration - can be guild-specific
        self.rate_limits = {
            'new_account_days': 30,
            'max_dms_per_hour': 2,
            'max_dms_per_day': 5,
            'block_duration_hours': 24,
        }

    @property
    def cache_manager(self) -> 'GuildSnapshotService':
        """Lazily resolve the guild snapshot service from bot (set by sync.py after init)."""
        return self.bot.guild_snapshots

    async def _count_human_members(self, guild: discord.Guild) -> int:
        """Count only human (non-bot) members in the guild"""
        return sum(1 for member in guild.members if not member.bot)

    async def initialize_guild_cache(self, guild: discord.Guild):
        """Initialize comprehensive guild cache data with human member tracking"""
        try:
            self.logger.info(f"Initializing comprehensive guild cache for {guild.name} ({guild.id})")

            cache_data = self.guild_cache[guild.id]

            # Basic guild metrics with human member tracking
            cache_data['member_count'] = guild.member_count
            cache_data['bot_count'] = sum(1 for member in guild.members if member.bot)
            cache_data['human_count'] = await self._count_human_members(guild)  # NEW: Track humans separately

            # Voice channel activity
            cache_data['voice_channels_active'] = sum(1 for vc in guild.voice_channels if vc.members)

            # Role distribution - only for human members
            role_dist = defaultdict(int)
            for member in guild.members:
                if not member.bot:  # NEW: Only count human members for role distribution
                    for role in member.roles:
                        if not role.is_default():
                            role_dist[role.name] += 1
            cache_data['role_distribution'] = dict(role_dist)

            # Channel activity — scanned in background to avoid blocking init
            cache_data['popular_channels'] = {}
            asyncio.create_task(self._scan_channel_activity(guild, cache_data))

            # Initialize today's counters
            cache_data['new_member_joins_today'] = 0
            cache_data['kicks_today'] = 0
            cache_data['last_activity'] = datetime.now(timezone.utc).isoformat()

            # Security metrics initialization
            cache_data['security_metrics']['suspicious_joins'] = 0
            cache_data['security_metrics']['account_age_violations'] = 0
            cache_data['security_metrics']['rapid_joins'] = 0

            cache_data['_initialized'] = True

            self.logger.info(f"Guild cache initialized: {guild.member_count} members, "
                             f"{cache_data['bot_count']} bots, {cache_data['human_count']} humans")

        except Exception as e:
            self.logger.error(f"Error initializing guild cache for {guild.name}: {e}")

    async def _scan_channel_activity(self, guild: discord.Guild, cache_data: dict):
        """Scan channel message history in the background with throttling. Populates popular_channels."""
        try:
            channel_activity = {}
            # Cap at 15 channels sorted by position (most visible first)
            channels_to_scan = sorted(guild.text_channels, key=lambda c: c.position)[:15]

            for channel in channels_to_scan:
                try:
                    recent_count = 0
                    async for _msg in channel.history(
                        after=datetime.now(timezone.utc) - timedelta(hours=24), limit=100
                    ):
                        recent_count += 1
                    channel_activity[channel.name] = recent_count
                except discord.Forbidden:
                    channel_activity[channel.name] = 0
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = getattr(e, 'retry_after', 5.0)
                        self.logger.warning(f"Rate limited scanning {channel.name}, retrying in {retry_after}s")
                        await asyncio.sleep(retry_after)
                        try:
                            recent_count = 0
                            async for _msg in channel.history(
                                after=datetime.now(timezone.utc) - timedelta(hours=24), limit=100
                            ):
                                recent_count += 1
                            channel_activity[channel.name] = recent_count
                        except Exception:
                            channel_activity[channel.name] = 0
                    else:
                        channel_activity[channel.name] = 0

                await asyncio.sleep(1.5)

            cache_data['popular_channels'] = dict(
                sorted(channel_activity.items(), key=lambda x: x[1], reverse=True)[:5]
            )
            self.logger.info(f"Channel activity scan complete for {guild.name}: {len(channel_activity)} channels scanned")

        except Exception as e:
            self.logger.error(f"Error scanning channel activity for {guild.name}: {e}")

    async def update_guild_metrics(self, guild: discord.Guild, event_type: str, **kwargs):
        """Update guild metrics based on events with human member tracking"""
        try:
            cache_data = self.guild_cache[guild.id]
            now = datetime.now(timezone.utc)

            if event_type == "member_join":
                member = kwargs.get('member')
                # member_count is a cheap cached int. human/bot counts are kept
                # incrementally (seeded once by initialize_guild_cache) so a join
                # burst never triggers an O(members) rescan on the event loop.
                cache_data['member_count'] = guild.member_count
                if member and member.bot:
                    cache_data['bot_count'] = cache_data.get('bot_count', 0) + 1
                elif member:
                    cache_data['human_count'] = cache_data.get('human_count', 0) + 1
                    cache_data['new_member_joins_today'] += 1

                    # Track join patterns only for humans
                    hour = now.hour
                    day = now.strftime('%Y-%m-%d')
                    week = now.strftime('%Y-W%U')

                    cache_data['join_patterns']['hourly'][hour] += 1
                    cache_data['join_patterns']['daily'][day] += 1
                    cache_data['join_patterns']['weekly'][week] += 1

                    # Check for rapid joins (security metric)
                    recent_joins = cache_data['join_patterns']['hourly'][hour]
                    if recent_joins > 10:  # More than 10 joins in an hour
                        cache_data['security_metrics']['rapid_joins'] += 1

                    account_age = now - member.created_at
                    if account_age.days < self.rate_limits['new_account_days']:
                        cache_data['security_metrics']['account_age_violations'] += 1

            elif event_type == "member_remove":
                member = kwargs.get('member')
                cache_data['member_count'] = guild.member_count
                if member and member.bot:
                    cache_data['bot_count'] = max(0, cache_data.get('bot_count', 0) - 1)
                elif member:
                    cache_data['human_count'] = max(0, cache_data.get('human_count', 0) - 1)

            elif event_type == "member_kick":
                member = kwargs.get('member')
                if member and not member.bot:  # NEW: Only count human kicks
                    cache_data['kicks_today'] += 1

            cache_data['last_activity'] = now.isoformat()

            # Update database cache periodically
            await self.cache_manager.cache_guild_info(guild)

        except Exception as e:
            self.logger.error(f"Error updating guild metrics for {guild.name}: {e}")

    async def get_guild_analytics(self, guild_id: int) -> Dict[str, Any]:
        """Get comprehensive guild analytics with accurate human counts"""
        cache_data = self.guild_cache.get(guild_id, {})

        analytics = {
            'basic_stats': {
                'total_members': cache_data.get('member_count', 0),
                'bot_count': cache_data.get('bot_count', 0),
                'human_members': cache_data.get('human_count', 0)
            },
            'activity_stats': {
                'joins_today': cache_data.get('new_member_joins_today', 0),
                'kicks_today': cache_data.get('kicks_today', 0),
                'active_voice_channels': cache_data.get('voice_channels_active', 0),
                'popular_channels': cache_data.get('popular_channels', {})
            },
            'security_metrics': cache_data.get('security_metrics', {}),
            'join_patterns': cache_data.get('join_patterns', {}),
            'role_distribution': cache_data.get('role_distribution', {}),
            'last_updated': cache_data.get('last_activity')
        }

        return analytics

    async def can_send_dm(self, member: discord.Member) -> tuple[bool, str]:
        """Enhanced DM rate limiting with guild-specific tracking"""
        # NEW: Skip rate limiting for bots entirely
        if member.bot:
            return False, "Bots cannot receive DMs"

        now = datetime.now(timezone.utc)
        account_age = now - member.created_at

        # Only apply rate limits to new accounts
        if account_age.days >= self.rate_limits['new_account_days']:
            return True, "Account old enough"

        user_limits = self.dm_rate_limits[member.id]

        # Initialize first attempt tracking
        if user_limits['first_attempt'] is None:
            user_limits['first_attempt'] = now

        user_limits['total_attempts'] += 1

        # Check if user is currently blocked
        if user_limits.get('blocked_until') and now < user_limits['blocked_until']:
            remaining = user_limits['blocked_until'] - now
            return False, f"Blocked for {remaining.seconds // 3600}h {(remaining.seconds % 3600) // 60}m"

        # Reset counters if needed (hourly reset)
        if now - user_limits['last_reset'] >= timedelta(hours=1):
            user_limits['count'] = 0
            user_limits['last_reset'] = now
            user_limits['blocked_until'] = None

        # Check hourly limit
        if user_limits['count'] >= self.rate_limits['max_dms_per_hour']:
            # Block the user
            user_limits['blocked_until'] = now + timedelta(hours=self.rate_limits['block_duration_hours'])
            self.logger.warning(
                f"User {member} ({member.id}) hit DM rate limit, blocked for {self.rate_limits['block_duration_hours']} hours"
            )
            return False, "Rate limit exceeded"

        return True, "Within limits"

    async def record_dm_sent(self, member: discord.Member):
        """Record that a DM was sent with enhanced tracking"""
        # NEW: Don't record DMs for bots
        if member.bot:
            return

        user_limits = self.dm_rate_limits[member.id]
        user_limits['count'] += 1

        # Update guild security metrics
        await self.update_guild_metrics(
            member.guild,
            "dm_sent",
            member=member,
            reason="account_age_restriction"
        )

        self.logger.info(f"DM count for {member} ({member.id}): {user_limits['count']}")

    async def _seed_guild_default_config(self, guild: discord.Guild) -> None:
        """Persist a default GuildConfig for a newly joined guild with all features
        disabled. The guild owner enables individual features via the settings flow."""
        try:
            manager = await get_guild_config_manager()

            # Skip if a config was already saved for this guild
            existing = await manager._collection.find_one({'guild_id': guild.id})
            if existing:
                self.logger.info(f"\n{s}Guild {guild.name} already has a config, skipping seed\n")
                return

            config = GuildConfig(guild_id=guild.id)

            # Disable all toggleable features — owner turns them on in settings
            config.new_members['enabled'] = False
            config.new_members['auto_kick'] = False
            config.new_members['welcome_message_enabled'] = False
            config.new_members['whitelist_enabled'] = False
            config.announcement['thread_auto_create'] = False
            config.announcement['auto_delete_threads'] = False
            config.tag_tracker['enabled'] = False

            saved = await manager.save_config(config)
            if saved:
                self.logger.info(f"\n{s}Default config seeded for {guild.name} ({guild.id})\n")
            else:
                self.logger.error(f"\n{s}Failed to seed default config for {guild.name} ({guild.id})\n")
        except Exception as e:
            self.logger.error(f"\n{s}Error seeding default config for {guild.name}: {e}\n", exc_info=True)

    async def handle_member_join(self, member: discord.Member):
        """Entry point for joins. Bounds concurrency so a raid of simultaneous
        joins can't fan out into an unbounded DM/kick burst."""
        async with self._join_sem:
            await self._process_member_join(member)

    async def _process_member_join(self, member: discord.Member):
        """Handle member join with bot filtering and comprehensive tracking"""
        self.logger.info(f"\n{s}New member joined: {member} ({member.id}) in {member.guild.name}\n")

        # NEW: Skip processing for bot accounts entirely
        if member.bot:
            self.logger.info(f"\n{s}Skipping bot account: {member} ({member.id})\n")
            return

        now = datetime.now(timezone.utc)
        account_age = now - member.created_at
        guild = member.guild

        # Seed the comprehensive cache once (one-time O(members) scan) BEFORE
        # metrics, so the incremental counters start from a correct baseline.
        # (Previously this ran after update_guild_metrics, which vivified the
        # defaultdict key first, so this branch never fired.)
        cache_data = self.guild_cache[guild.id]
        if not cache_data.get('_initialized'):
            await self.initialize_guild_cache(guild)

        # Update guild metrics (will only count humans due to our update_guild_metrics changes)
        await self.update_guild_metrics(guild, "member_join", member=member)

        # Default avatar fallback
        avatar_url = member.display_avatar.url if member.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

        # Load guild config for new member settings
        guild_config = await get_config(guild.id)
        if not guild_config.new_members.get("enabled", False):
            return

        if guild_config.new_members["auto_kick"] and account_age.days < guild_config.new_members["account_age_requirement_days"]:
            # Check if user is whitelisted before kicking
            if guild_config.new_members["whitelist_enabled"]:
                from storage.manager import db_manager
                try:
                    whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')
                    whitelist_entry = await whitelist_collection.find_one({
                        'guild_id': guild.id,
                        'user_id': member.id,
                        'is_active': True
                    })

                    if whitelist_entry:
                        # User is whitelisted - allow them to join and assign role
                        self.logger.info(f"\n{s}Member {member} is whitelisted, bypassing age restriction (account age: {account_age.days} days)\n")

                        # Assign whitelist role if not already assigned
                        if not whitelist_entry.get('role_assigned', False):
                            try:
                                from Features.NewMembers.admin.whitelist import WHITELIST_ROLE_COLOR
                                whitelist_role_name = guild_config.new_members["whitelist_role_name"]
                                role = None
                                if guild_config.new_members["whitelist_role_id"]:
                                    role = guild.get_role(guild_config.new_members["whitelist_role_id"])
                                if not role:
                                    role = discord.utils.get(guild.roles, name=whitelist_role_name)
                                if not role:
                                    # Create role if it doesn't exist
                                    role = await guild.create_role(
                                        name=whitelist_role_name,
                                        color=WHITELIST_ROLE_COLOR,
                                        reason="Whitelist role for new members with new accounts",
                                        mentionable=False,
                                        hoist=True
                                    )
                                await member.add_roles(role, reason="Whitelisted new member")

                                # Update database
                                await whitelist_collection.update_one(
                                    {'guild_id': guild.id, 'user_id': member.id},
                                    {'$set': {
                                        'role_assigned': True,
                                        'role_assigned_at': datetime.now(timezone.utc),
                                        'account_age_at_join': account_age.days
                                    }}
                                )
                                self.logger.info(f"\n{s}Assigned whitelist role to {member}\n")
                            except Exception as role_error:
                                self.logger.error(f"\n{s}Failed to assign whitelist role to {member}: {role_error}\n")

                        # Continue with normal welcome flow (skip the kick)
                        channel = member.guild.get_channel(guild_config.new_members["welcome_channel_id"]) if guild_config.new_members["welcome_channel_id"] else None
                        if channel and guild_config.new_members["welcome_message_enabled"]:
                            try:
                                # Update members cache for this guild
                                await self.cache_manager.cache_members(member.guild)
                                self.logger.info(f"\n{s}Member cache updated for {member.guild.name}\n")
                            except Exception as e:
                                self.logger.error(f"\n{s}Error updating member cache for {member.guild.name}: {e}\n")

                            try:
                                await asyncio.sleep(1.2)
                                await self.send_welcome_message(member)
                                self.logger.info(f"Interactive welcome message sent for whitelisted member {member}\n")
                            except Exception as e:
                                self.logger.error(f"Error sending welcome message: {e}\n")
                        return  # Exit early, don't kick
                except Exception as whitelist_error:
                    self.logger.error(f"\n{s}Error checking whitelist: {whitelist_error}\n", exc_info=True)
                    # Continue with normal flow if whitelist check fails

            # Account is too new. The kick is the priority: every millisecond
            # before it is a window where the new account can read channels, so
            # the DM is strictly best-effort and the old artificial sleeps are
            # gone. (DMs require a mutual guild, so we still send before kicking,
            # but never block the kick on it.) For hard gatekeeping, gate channel
            # access behind a verification role — an age-kick is a backstop, not
            # a true gate, since it runs after the member is already in.
            can_dm, reason = await self.can_send_dm(member)
            if can_dm:
                try:
                    await member.send(
                        f"Hey {member.name}! 👋\n\n"
                        f"Unfortunately, your Discord account is too new to join our server (created {account_age.days} days ago).\n"
                        f"We require accounts to be at least {guild_config.new_members['account_age_requirement_days']} days old to help prevent spam and protect our community.\n\n"
                        f"You're welcome to try again once your account is older. Thanks for understanding! 🙏"
                    )
                    await self.record_dm_sent(member)
                    self.logger.info(f"\n{s}Sent DM to {member} about new account restriction.\n")
                except discord.Forbidden:
                    self.logger.warning(f"\n{s}Could not DM {member} before kick (Forbidden).\n")
                except Exception as e:
                    self.logger.error(f"\n{s}Failed to DM {member}: {e}")
            else:
                self.logger.info(f"\n{s}Skipped DM to {member} due to rate limiting: {reason}\n")

            try:
                await member.kick(
                    reason=f"Account too new ({account_age.days} days old, requires {guild_config.new_members['account_age_requirement_days']})"
                )
                await self.update_guild_metrics(guild, "member_kick", member=member)
                self.logger.info(f"\n{s}Kicked {member} due to account age ({account_age.days} days).\n")
            except discord.Forbidden:
                self.logger.error(
                    f"\n{s}Cannot kick {member}: missing Kick Members permission or role hierarchy too low.\n"
                )
            except Exception as e:
                self.logger.error(f"\n{s}Failed to kick {member}: {e}\n")
            return

        # Account is old enough (or auto-kick disabled) - proceed with welcome
        channel = member.guild.get_channel(guild_config.new_members["welcome_channel_id"]) if guild_config.new_members["welcome_channel_id"] else None
        if channel and guild_config.new_members["welcome_message_enabled"]:
            try:
                # Update members cache for this guild
                await self.cache_manager.cache_members(member.guild)
                self.logger.info(f"\n{s}Member cache updated for {member.guild.name}\n")
            except Exception as e:
                self.logger.error(f"\n{s}Error updating member cache for {member.guild.name}: {e}\n")

            try:
                await asyncio.sleep(1.2)
                await self.send_welcome_message(member)
                self.logger.info(f"Interactive welcome message sent for {member}\n")
            except Exception as e:
                self.logger.error(f"Error sending welcome message: {e}\n")

    async def send_welcome_message(self, member: discord.Member, avatar_url: str = None):
        """Send enhanced welcome message using Discord components v2 through discord.py"""
        # Get guild config for channel IDs
        guild_config = await get_config(member.guild.id)

        if not guild_config.new_members["welcome_channel_id"]:
            self.logger.warning(f"Welcome channel not configured for guild {member.guild.name} ({member.guild.id})")
            return

        channel = member.guild.get_channel(guild_config.new_members["welcome_channel_id"])
        if not channel:
            self.logger.error(f"Welcome channel {guild_config.new_members['welcome_channel_id']} not found in guild {member.guild.name}")
            return

        # Store guild_id for URL building
        guild_id = member.guild.id

        if avatar_url is None:
            avatar_url = member.display_avatar.url if member.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

        try:
            # Get guild analytics for personalized welcome
            analytics = await self.get_guild_analytics(member.guild.id)
            member_number = analytics['basic_stats']['human_members']  # This now uses accurate human count

            # Render welcome message from JSON builder config
            welcome_components = guild_config.new_members.get("welcome_components")
            if not welcome_components:
                self.logger.warning(
                    f"[WELCOME] No welcome_components configured for guild {member.guild.id} — skipping welcome message for {member}"
                )
                return

            from Features.NewMembers.welcome_renderer import WelcomeRenderer
            layout_view = WelcomeRenderer.render(
                welcome_components, member, member_number, analytics=analytics
            )
            await channel.send(view=layout_view)

            self.logger.info(f"\n{s}[WELCOME] Successfully sent welcome message for {member}\n")

        except Exception as e:
            self.logger.error(f"Error sending Components v2 welcome message: {e}", exc_info=True)

    async def handle_interaction(self, interaction: discord.Interaction):
        """Handle component interactions — routes to welcome or guide dispatchers."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")

        # Route guide interactions (g: prefix) to the guide dispatcher
        if custom_id.startswith("g:"):
            from Features.Guide.guide import dispatch_guide_interaction
            await dispatch_guide_interaction(interaction)
            return

        # Route welcome interactions (w: prefix)
        from Features.NewMembers.welcome_actions import dispatch_welcome_action
        handled = await dispatch_welcome_action(interaction)
        if not handled:
            self.logger.debug(f"Unhandled component interaction: {custom_id}")

    async def handle_member_remove(self, member: discord.Member):
        """Handle member removal with enhanced tracking and cache cleanup"""
        self.logger.info(f"\n{s}Member left: {member.name} ({member.id}) in guild: {member.guild.name}\n")

        # Update guild metrics (handles human/bot distinction internally)
        await self.update_guild_metrics(member.guild, "member_remove", member=member)

        # NEW: Clean up rate limit data for users who leave (humans only)
        if not member.bot and member.id in self.dm_rate_limits:
            del self.dm_rate_limits[member.id]
            self.logger.info(f"Cleaned up rate limit data for {member.id}")

        try:
            # Update members cache for this guild
            await self.cache_manager.cache_members(member.guild)
            self.logger.info(f"\n{s}Member cache updated for {member.guild.name}\n")
        except Exception as e:
            self.logger.error(f"\n{s}Error updating member cache for {member.guild.name}: {e}\n")

    async def handle_guild_role_update(self, before: discord.Role, after: discord.Role):
        """Handle role updates with caching"""
        self.logger.info(f"\n{s}Role updated: {after.name} ({after.id}) in guild: {after.guild.name}\n")

        # Update guild role distribution cache - only for human members
        guild_data = self.guild_cache[after.guild.id]
        role_dist = defaultdict(int)
        for member in after.guild.members:
            if not member.bot:  # NEW: Only count human members for role distribution
                for role in member.roles:
                    if not role.is_default():
                        role_dist[role.name] += 1
        guild_data['role_distribution'] = dict(role_dist)

        try:
            # Update roles cache for this guild
            await self.cache_manager.cache_roles(after.guild)
            self.logger.info(f"\n{s}Roles cache updated for {after.guild.name}\n")
        except Exception as e:
            self.logger.error(f"Error updating roles cache for {after.guild.name}: {e}\n")

    async def handle_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """Handle channel updates with caching"""
        self.logger.info(f"\n{s}Channel updated: {after.name} ({after.id}) in guild: {after.guild.name}\n")
        try:
            # Update channels cache for this guild
            await self.cache_manager.cache_channels(after.guild)
            self.logger.info(f"\n{s}Channels cache updated for {after.guild.name}\n")
        except Exception as e:
            self.logger.error(f"\n{s}Error updating channels cache for {after.guild.name}: {e}\n")

    async def _cleanup_guild_data(self, guild_id: int, guild_name: str) -> None:
        """
        Delete all database records scoped to a guild after the bot is removed.

        # TODO (future): Before deleting, check a per-guild opt-in preference that allows
        #   guild owners / members to retain their data (e.g. stats, profile themes) after
        #   the bot leaves.  If the guild opted in, skip the relevant collections or mark
        #   them as archived instead of deleting.
        """
        self.logger.info(f"Starting data cleanup for guild {guild_name} ({guild_id})")
        totals: dict[str, int] = {}

        def col(key: str):
            return db_manager.get_collection_manager(key)

        try:
            # --- Settings ---
            # delete_one returns bool; delete_many returns int (deleted count directly)
            totals["settings_guild_config"] = 1 if await col("settings_guild_config").delete_one({"guild_id": guild_id}) else 0

            # Invalidate in-memory config cache
            manager = await get_guild_config_manager()
            await manager.invalidate_cache(guild_id)

            # --- WYR (Would You Rather) ---
            # Question pool is shared across guilds; only strip this guild's per-guild block.
            gid_str = str(guild_id)
            totals["daily_wyr"] = await col("daily_wyr").update_many(
                {f"guilds.{gid_str}": {"$exists": True}},
                {"$unset": {f"guilds.{gid_str}": ""}},
            )
            totals["daily_wyr_leaderboard"] = await col("daily_wyr_leaderboard").delete_many({"guild_id": gid_str})
            totals["daily_wyr_mappings"] = await col("daily_wyr_mappings").delete_many({"guild_id": guild_id})

            # --- Suggestions (votes/notifications reference suggestion_id, not guild_id directly) ---
            suggestion_ids = await col("suggestions_suggestions").collection.distinct(
                "suggestion_id", {"guild_id": guild_id}
            )
            if suggestion_ids:
                totals["suggestions_votes"] = await col("suggestions_votes").delete_many(
                    {"suggestion_id": {"$in": suggestion_ids}}
                )
                totals["suggestions_notification_queue"] = await col("suggestions_notification_queue").delete_many(
                    {"suggestion_id": {"$in": suggestion_ids}}
                )
            totals["suggestions_suggestions"] = await col("suggestions_suggestions").delete_many({"guild_id": guild_id})

            # --- Updates / Drops stats (compound _id embeds guild_id) ---
            totals["updates_monthly"] = await col("updates_monthly").delete_many({"_id.guild_id": guild_id})
            totals["updates_weekly"] = await col("updates_weekly").delete_many({"_id.guild_id": guild_id})
            totals["updates_totals"] = await col("updates_totals").delete_many({"_id.guild_id": guild_id})

            # --- ServerData ---
            totals["serverdata_boosts"] = await col("serverdata_boosts").delete_many({"guild_id": guild_id})
            totals["serverdata_boost_events"] = await col("serverdata_boost_events").delete_many({"guild_id": guild_id})
            totals["serverdata_whitelist"] = await col("serverdata_whitelist").delete_many({"guild_id": guild_id})
            totals["color_color_sets"] = await col("color_color_sets").delete_many({"guild_id": guild_id})
            totals["color_color_set_assignments"] = await col("color_color_set_assignments").delete_many({"guild_id": guild_id})

            # --- ServerData cache collections ---
            totals["serverdata_guilds"] = await col("serverdata_guilds").delete_many({"id": guild_id})
            totals["serverdata_channels"] = await col("serverdata_channels").delete_many({"guild_id": guild_id})
            totals["serverdata_members"] = await col("serverdata_members").delete_many({"guild_id": guild_id})
            totals["serverdata_roles"] = await col("serverdata_roles").delete_many({"guild_id": guild_id})
            totals["serverdata_analytics"] = await col("serverdata_analytics").delete_many({"guild_id": guild_id})
            totals["serverdata_events"] = await col("serverdata_events").delete_many({"guild_id": guild_id})

            # --- Guide content ---
            totals["guide_content"] = await col("guide_content").delete_many({"guild_id": guild_id})

            deleted_total = sum(totals.values())
            self.logger.info(
                f"Guild data cleanup complete for {guild_name} ({guild_id}): "
                f"{deleted_total} records removed — {totals}"
            )

        except Exception as e:
            self.logger.error(
                f"Error during guild data cleanup for {guild_name} ({guild_id}): {e}",
                exc_info=True
            )


# Create the guild event handler instance
guild_handler = GuildEventHandler(bot)


# Keep your existing event handlers but delegate to the class

# Section: Interactions
# Missing in this section:
# - (None, all handled via on_interaction)
@bot.listen()
async def on_interaction(interaction: discord.Interaction):
    await guild_handler.handle_interaction(interaction)

# Section: Member lifecycle and moderation
# Missing in this section:
# - on_member_chunk
@bot.event
async def on_member_join(member):
    await guild_handler.handle_member_join(member)

@bot.event
async def on_member_remove(member: discord.Member):
    await guild_handler.handle_member_remove(member)

# Section: Guild lifecycle and cache
# Missing in this section:
# - on_guild_integrations_update
# - on_audit_log_entry_create

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    await guild_handler.handle_guild_role_update(before, after)

@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    await guild_handler.handle_guild_channel_update(before, after)

@bot.event
async def on_guild_join(guild):
    guild_handler.logger.info(f"Event: on_guild_join - joined guild {guild.name} ({guild.id})")
    try:
        await guild_handler._seed_guild_default_config(guild)
    except Exception as e:
        guild_handler.logger.error(f"Error seeding default config on guild join: {e}")
    try:
        await guild_handler.initialize_guild_cache(guild)
    except Exception as e:
        guild_handler.logger.error(f"Error initializing cache on guild join: {e}")

@bot.event
async def on_guild_remove(guild):
    guild_handler.logger.info(f"Event: on_guild_remove - removed from guild {guild.name} ({guild.id})")
    # Clear in-memory guild cache
    if guild.id in guild_handler.guild_cache:
        del guild_handler.guild_cache[guild.id]
        guild_handler.logger.info(f"Cleared memory cache for guild {guild.id}")
    # Remove all guild-scoped data from the database
    await guild_handler._cleanup_guild_data(guild.id, guild.name)
    # Drop in-memory snapshot state for the departed guild (leaves stored snapshots intact)
    if guild_handler.cache_manager:
        guild_handler.cache_manager.forget(guild.id)

# Section: Roles
# Missing in this section:
# - (None)
@bot.event
async def on_guild_role_create(role):
    guild_handler.logger.info(f"Event: on_guild_role_create - {role.name} ({role.id}) in {role.guild.name}")
    # update role distribution cache
    try:
        await guild_handler.handle_guild_role_update(role, role)
    except Exception:
        # fallback to cache refresh
        await guild_handler.cache_manager.cache_roles(role.guild)
    pass

@bot.event
async def on_guild_role_delete(role):
    guild_handler.logger.info(f"Event: on_guild_role_delete - {role.name} ({role.id}) in {role.guild.name}")
    # refresh roles cache
    try:
        await guild_handler.cache_manager.cache_roles(role.guild)
    except Exception as e:
        guild_handler.logger.error(f"Error updating roles cache after delete: {e}")
    pass