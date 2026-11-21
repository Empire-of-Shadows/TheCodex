"""Tag Tracker: give a role to members wearing THIS server's tag.

How a member's tag is read (rebuilt 2026-11-20 from a live pull of the community
server with TheCodex's token, and Discord's docs):

- Every member carries ``primary_guild``: the server the tag they wear belongs to
  (``identity_guild_id``, discord.py ``PrimaryGuild.id``), whether they are showing
  it (``identity_enabled``), and its text (``tag``). A member counts as wearing our
  tag only when that id is this server's and ``identity_enabled`` is True. The
  tag TEXT is not unique across Discord (the pull found members wearing other
  servers' tags), so it is never used for matching. The old code matched text.
- The server object carries NO tag for a bot (the pull showed the full key set;
  the ``clan`` field the old auto-sync read does not exist), so the tag text is
  learned from members wearing it and saved to ``tag_tracker.server_tag`` for the
  panel and dashboard to show. Nobody types it any more.
- Whether a server CAN have a tag is the ``GUILD_TAGS`` server feature (a boost
  perk). The panel and dashboard refuse to switch the tracker on without it. The
  bot itself does not check it: when a server loses tags Discord clears the
  wearers' identity, they stop matching, and the role is taken back as usual.
- discord.py fires ``on_user_update`` when ``primary_guild`` changes (it compares
  it in ``Member._update_inner_user``; a Discord maintainer confirmed the field
  is sent in GUILD_MEMBER_UPDATE, discord-api-docs discussion #8070).
"""

import asyncio
from typing import Optional

import discord
from discord.ext import commands, tasks

from storage.settings.config_manager import get_config, get_guild_config_manager
from storage.log import get_logger
from Features.role_safety import has_dangerous_permissions, is_blocked

# Logger
logger = get_logger("tag_tracker")

# The Discord server feature that means "this server can set a tag".
GUILD_TAGS_FEATURE = "GUILD_TAGS"


def wears_server_tag(member: discord.abc.User, guild_id: int) -> bool:
    """True when ``member`` is displaying the tag of the server ``guild_id``."""
    primary = getattr(member, "primary_guild", None)
    if primary is None:
        return False
    return primary.id == guild_id and primary.identity_enabled is True


def server_tag_text(member: discord.abc.User, guild_id: int) -> Optional[str]:
    """The text of this server's tag as ``member`` wears it, or None."""
    if not wears_server_tag(member, guild_id):
        return None
    tag = getattr(member.primary_guild, "tag", None)
    return tag or None


def detect_server_tag(guild: discord.Guild) -> tuple[Optional[str], int]:
    """(tag text, number of members wearing it) from the member cache.

    The tag text is the one most wearers show (they all show the same text; the
    count only guards against a stale cache entry mid-rename)."""
    counts: dict[str, int] = {}
    wearers = 0
    for member in guild.members:
        if member.bot or not wears_server_tag(member, guild.id):
            continue
        wearers += 1
        tag = server_tag_text(member, guild.id)
        if tag:
            counts[tag] = counts.get(tag, 0) + 1
    tag = max(counts, key=counts.get) if counts else None
    return tag, wearers


def _tag_identity(user: discord.abc.User) -> tuple:
    """What about a user's tag can change: whose tag, shown or not, and its text."""
    p = getattr(user, "primary_guild", None)
    if p is None:
        return (None, None, None)
    return (p.id, p.identity_enabled, p.tag)


class TagTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        logger.info("TagTracker initialized")

    async def cog_load(self):
        """Start the periodic reconcile loop when the cog loads."""
        self.check_tags.start()
        logger.info("Tag tracker task started")

    def cog_unload(self):
        if self.check_tags.is_running():
            self.check_tags.cancel()

    async def _safe_role_change(self, member: discord.Member, role: discord.Role, *, add: bool) -> bool:
        """Add or remove a role with 429 retry handling. Returns True on success.

        Never ADDS a role carrying moderator powers (Features/role_safety.py);
        removing it still works, so wearers who drop the tag lose it as before.
        The refusal is logged once per sweep in _resolve_tag_settings, not here.
        """
        if add and has_dangerous_permissions(role):
            return False
        for _attempt in range(3):
            try:
                if add:
                    await member.add_roles(role)
                else:
                    await member.remove_roles(role)
                return True
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 5.0)
                    logger.warning(f"Rate limited on role change for {member.name}, retrying in {retry_after}s")
                    await asyncio.sleep(retry_after)
                else:
                    raise
        return False

    async def _resolve_tag_settings(self, guild: discord.Guild) -> Optional[discord.Role]:
        """The tracked role if tag tracking is active for this guild, else None."""
        config = await get_config(guild.id)
        if not config.tag_tracker.get("enabled", False):
            return None
        role_id = config.tag_tracker.get("role_id")
        if not role_id:
            return None
        role = guild.get_role(role_id)
        if not role:
            logger.warning(f"Tag role {role_id} not found in guild {guild.name}. Skipping.")
            return None
        is_blocked(role, where="tag tracker")  # logs; adds are refused in _safe_role_change
        return role

    async def _remember_tag(self, guild: discord.Guild, tag: Optional[str]) -> None:
        """Save the tag text the bot saw members wearing, when it differs from the
        stored one, so the panel and dashboard can show it. Never clears it: nobody
        wearing the tag right now does not mean the server has no tag."""
        if not tag:
            return
        config = await get_config(guild.id)
        if config.tag_tracker.get("server_tag") == tag:
            return
        mgr = await get_guild_config_manager()
        config = await mgr.get_config(guild.id)
        old = config.tag_tracker.get("server_tag")
        config.tag_tracker["server_tag"] = tag
        if await mgr.save_config(config):
            logger.info(f"Learned server tag for {guild.name} from its members: {old!r} -> {tag!r}")

    async def _sync_member(self, member: discord.Member, role: discord.Role) -> bool:
        """Reconcile one member's tag role against their cached primary_guild.

        Reads ``member.primary_guild`` straight from the gateway-populated cache -
        no per-member ``fetch_user`` call - so a full sweep costs zero API calls
        in the steady state. Returns True if a role change was actually made.
        """
        if member.bot:
            return False

        has_tag = wears_server_tag(member, member.guild.id)
        has_role = role in member.roles

        if has_tag and not has_role:
            if await self._safe_role_change(member, role, add=True):
                logger.info(f"Added role {role.name} to {member.name} for having the tag.")
            return True
        if not has_tag and has_role:
            if await self._safe_role_change(member, role, add=False):
                logger.info(f"Removed role {role.name} from {member.name} for not having the tag.")
            return True
        return False

    @tasks.loop(hours=1)
    async def check_tags(self):
        """Periodic safety-net reconcile. Real-time updates flow through
        on_user_update; this catches anything the gateway missed."""
        if self._lock.locked():
            logger.info("Previous tag check still running, skipping this cycle.")
            return

        async with self._lock:
            logger.info("Starting tag check...")

            for guild in self.bot.guilds:
                # Learn the tag text even while the tracker is off, so the panel
                # and dashboard can show it before anyone switches it on.
                try:
                    tag, _wearers = detect_server_tag(guild)
                    await self._remember_tag(guild, tag)
                except Exception as e:
                    logger.error(f"Could not record the server tag for {guild.name}: {e}")

                role = await self._resolve_tag_settings(guild)
                if not role:
                    continue

                logger.info(f"Checking tags in guild: {guild.name} ({len(guild.members)} members from cache)")
                for member in guild.members:
                    try:
                        changed = await self._sync_member(member, role)
                        # Throttle ONLY when a role was actually mutated, so a
                        # converged server costs nothing and an initial rollout
                        # stays under the per-guild role rate limit.
                        if changed:
                            await asyncio.sleep(0.5)
                    except discord.HTTPException as e:
                        logger.error(f"HTTP error while checking tag for {member.name}: {e}")
                    except Exception as e:
                        logger.error(f"An error occurred while checking tag for {member.name}: {e}")

            logger.info("Tag check finished.")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Real-time tag sync when a user changes their primary (clan) guild.

        primary_guild is a user-global attribute, so the change surfaces as a
        user update rather than a member update. Only a change to whose tag is
        worn, whether it is shown, or its text triggers a resync, so unrelated
        profile edits cost nothing.

        A server renaming its tag reaches us the same way: every wearer's text
        changes, and the first one seen updates the stored tag text. (This
        replaced an on_guild_update auto-sync that read a ``clan`` field from the
        server object; that field is not sent to bots, so it never found a tag.)
        """
        if _tag_identity(before) == _tag_identity(after):
            return

        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue
            try:
                await self._remember_tag(guild, server_tag_text(member, guild.id))
            except Exception as e:
                logger.error(f"Could not record the server tag for {guild.name}: {e}")
            role = await self._resolve_tag_settings(guild)
            if not role:
                continue
            try:
                await self._sync_member(member, role)
            except discord.HTTPException as e:
                logger.error(f"Tag sync on user update failed for {after} in {guild.name}: {e}")

    @check_tags.before_loop
    async def before_check_tags(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    cog = TagTracker(bot)
    await bot.add_cog(cog)
