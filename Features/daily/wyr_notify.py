"""Self-serve WYR notification role.

The role handed out here is the same one the daily post pings
(``config.wyr["ping_role_id"]``), so subscribing means exactly "ping me when a
new Would You Rather question goes up". Nothing is hardcoded - a guild that has
not configured a ping role, or where the bot cannot hand that role out, simply
never advertises.

Three ways in, all reversible by the member without asking staff:
  * a "Notify Me" button on every daily question post,
  * a prompt attached to the ephemeral reply after voting or viewing results,
    shown only to members who do not already have the role,
  * ``/wyr notify`` at any time.

Member preferences (a permanent "not interested" dismissal and when we last
advertised) live in ``daily_wyr_notify_prefs``, one document per guild/user, so
the prompt cannot turn into nagging. A member's roles are only ever changed by
their own click.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord

from storage.log import get_logger
from storage.settings.collections import db_manager
from storage.settings.config_manager import get_config
from admin.setup_notice import setup_notice_text

logger = get_logger("WYRNotify")

# Persistent custom_id for the button on the daily post. It is registered with
# the bot through WYRView, so it keeps working after a restart.
NOTIFY_BUTTON_ID = "wyr:notify"

# How long before the same member is advertised to again. Slightly under a day
# so a daily voter sees the offer at most once per question.
_PROMPT_COOLDOWN = timedelta(hours=20)

SUBSCRIBE_LABEL = "🔔 Notify Me"
UNSUBSCRIBE_LABEL = "🔕 Turn Off Pings"

async def _not_available(
    guild: discord.Guild | None,
    viewer: discord.Member | None = None,
) -> str:
    """The "notifications aren't available here" text, with setup directions."""
    return await setup_notice_text(
        guild,
        what="Would You Rather notifications",
        path="WYR Settings -> WYR Ping Role",
        viewer=viewer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Role resolution
# ─────────────────────────────────────────────────────────────────────────────

async def get_notify_role(guild: discord.Guild | None) -> discord.Role | None:
    """Resolve the WYR ping role for a guild, or None if it is unusable.

    Unusable covers every case where handing the role out would fail: no role
    configured, the role was deleted, it is managed by an integration, the bot
    is missing Manage Roles, or the role sits at or above the bot's top role.
    Checking up front means a member is never offered something the bot cannot
    actually give them.
    """
    if guild is None:
        return None

    try:
        config = await get_config(guild.id)
    except Exception as e:
        logger.error(f"Could not read WYR config for guild {guild.id}: {e}", exc_info=True)
        return None

    role_id = config.wyr.get("ping_role_id")
    if not role_id:
        return None

    role = guild.get_role(int(role_id))
    if role is None:
        logger.warning(f"WYR ping role {role_id} no longer exists in guild {guild.id}")
        return None

    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        logger.warning(f"Cannot manage WYR ping role in guild {guild.id}: missing Manage Roles")
        return None
    if role.managed:
        logger.warning(f"WYR ping role {role.id} in guild {guild.id} is integration-managed")
        return None
    if role >= me.top_role:
        logger.warning(
            f"WYR ping role {role.id} in guild {guild.id} is not below the bot's top role"
        )
        return None

    return role


async def _prompt_enabled(guild_id: int) -> bool:
    """Whether this guild wants the feature advertised in-line."""
    try:
        config = await get_config(guild_id)
    except Exception as e:
        logger.error(f"Could not read WYR config for guild {guild_id}: {e}", exc_info=True)
        return False
    return bool(config.wyr.get("subscribe_prompt_enabled", True))


# ─────────────────────────────────────────────────────────────────────────────
# Per-member prompt preferences
# ─────────────────────────────────────────────────────────────────────────────

async def _get_prefs(guild_id: int, user_id: int) -> dict:
    try:
        doc = await db_manager.daily_wyr_notify_prefs.find_one(
            {"guild_id": str(guild_id), "user_id": str(user_id)}
        )
        return doc or {}
    except Exception as e:
        logger.error(f"Error reading WYR notify prefs for {user_id} in {guild_id}: {e}", exc_info=True)
        return {}


async def _write_prefs(guild_id: int, user_id: int, changes: dict) -> None:
    now = datetime.now(timezone.utc)
    try:
        await db_manager.daily_wyr_notify_prefs.update_one(
            {"guild_id": str(guild_id), "user_id": str(user_id)},
            {
                "$set": {**changes, "updated_at": now},
                "$setOnInsert": {
                    "guild_id": str(guild_id),
                    "user_id": str(user_id),
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Error writing WYR notify prefs for {user_id} in {guild_id}: {e}", exc_info=True)


async def set_dismissed(guild_id: int, user_id: int, dismissed: bool = True) -> None:
    """Remember that a member does (or no longer does) want to be left alone."""
    await _write_prefs(guild_id, user_id, {"dismissed": dismissed})


def _as_utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# The prompt
# ─────────────────────────────────────────────────────────────────────────────

async def _should_advertise(member: discord.Member, role: discord.Role | None) -> bool:
    """Whether this member should see the subscribe offer right now."""
    if role is None or not isinstance(member, discord.Member) or member.bot:
        return False
    if role in member.roles:
        # Already subscribed - never advertise something they have.
        return False
    if not await _prompt_enabled(member.guild.id):
        return False

    prefs = await _get_prefs(member.guild.id, member.id)
    if prefs.get("dismissed"):
        return False

    last_prompted = _as_utc(prefs.get("last_prompted_at"))
    if last_prompted and datetime.now(timezone.utc) - last_prompted < _PROMPT_COOLDOWN:
        return False

    return True


async def prompt_kwargs(member: discord.Member) -> dict:
    """Extra ``send_message`` kwargs that attach the subscribe offer, or ``{}``.

    Callers splat this into their own ephemeral reply, so the offer rides along
    with the vote confirmation or results instead of arriving as a second
    message. Returns an empty dict whenever the member should not be
    advertised to, and swallows its own errors - a failure here must never cost
    someone their vote.
    """
    try:
        role = await get_notify_role(getattr(member, "guild", None))
        if not await _should_advertise(member, role):
            return {}

        await _write_prefs(member.guild.id, member.id, {"last_prompted_at": datetime.now(timezone.utc)})

        return {
            "content": (
                f"Want a heads-up when the next question drops? "
                f"Grab **{role.name}** and you'll be pinged with each new one."
            ),
            "view": NotifyManageView(member_id=member.id, subscribed=False, offer_dismiss=True),
        }
    except Exception as e:
        logger.error(f"Error building WYR notify prompt for {getattr(member, 'id', '?')}: {e}", exc_info=True)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Subscribing / unsubscribing
# ─────────────────────────────────────────────────────────────────────────────

def _is_ephemeral(interaction: discord.Interaction) -> bool:
    """Whether this interaction came from a button on an ephemeral message.

    Those messages are ours to replace; a button on the public daily post is
    not, so its click gets a fresh ephemeral reply instead.
    """
    message = interaction.message
    return bool(message is not None and message.flags.ephemeral)


async def _reply(interaction: discord.Interaction, content: str, view: discord.ui.View | None) -> None:
    """Answer a notification click, replacing our own ephemeral message if that
    is where the click came from."""
    if _is_ephemeral(interaction):
        # Leave any embed alone - the vote confirmation stays readable.
        await interaction.response.edit_message(content=content, view=view)
    elif view is None:
        # send_message treats a None view as a real view, so omit it entirely.
        await interaction.response.send_message(content=content, ephemeral=True)
    else:
        await interaction.response.send_message(content=content, view=view, ephemeral=True)


async def apply_subscription(interaction: discord.Interaction, *, subscribe: bool) -> None:
    """Add or remove the WYR ping role for the member who clicked, then reply."""
    member = interaction.user
    guild = interaction.guild

    if guild is None or not isinstance(member, discord.Member):
        await _reply(interaction, "WYR notifications can only be managed inside a server.", None)
        return

    role = await get_notify_role(guild)
    if role is None:
        await _reply(interaction, await _not_available(guild, member), None)
        return

    already_has = role in member.roles

    try:
        if subscribe and not already_has:
            await member.add_roles(role, reason="WYR notifications: member opted in")
            logger.info(f"Gave WYR ping role to {member} ({member.id}) in guild {guild.id}")
            # Opting in clears any earlier "not interested" so the prompt works
            # normally again if they later opt back out and change their mind.
            await set_dismissed(guild.id, member.id, False)
        elif not subscribe and already_has:
            await member.remove_roles(role, reason="WYR notifications: member opted out")
            logger.info(f"Removed WYR ping role from {member} ({member.id}) in guild {guild.id}")
            # An explicit opt-out is an answer, not an accident - stop offering.
            await set_dismissed(guild.id, member.id, True)
    except discord.Forbidden:
        logger.warning(f"Forbidden managing WYR ping role for {member.id} in guild {guild.id}")
        await _reply(
            interaction,
            f"I could not change **{role.name}** for you - I am missing permission to manage it. "
            "Please let a server admin know.",
            None,
        )
        return
    except discord.HTTPException as e:
        logger.error(f"HTTP error managing WYR ping role for {member.id}: {e}", exc_info=True)
        await _reply(interaction, "Something went wrong changing your notifications. Please try again.", None)
        return

    if subscribe:
        content = (
            f"🔔 You're on the list - you'll be pinged as **{role.name}** when a new "
            f"Would You Rather question is posted."
            if not already_has else
            f"🔔 You already have **{role.name}**, so you're being pinged for new questions."
        )
    else:
        content = (
            "🔕 Done - no more pings for new questions. Turn them back on any time with "
            "`/wyr notify` or the **Notify Me** button on a question."
            if already_has else
            "You are not signed up for question pings right now."
        )

    # Whatever happened, they now sit on the side they asked for, so the view
    # offers the opposite move.
    await _reply(interaction, content, NotifyManageView(member_id=member.id, subscribed=subscribe))


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class NotifyManageView(discord.ui.View):
    """One button showing the member the opposite of their current state.

    Subscribed members get "turn it off", everyone else gets "notify me", so
    leaving is always exactly as easy as joining. ``offer_dismiss`` adds the
    quiet way out used by the in-line prompt.
    """

    def __init__(self, *, member_id: int, subscribed: bool, offer_dismiss: bool = False):
        super().__init__(timeout=600)
        self.member_id = member_id

        if subscribed:
            toggle = discord.ui.Button(label=UNSUBSCRIBE_LABEL, style=discord.ButtonStyle.secondary)
            toggle.callback = self._unsubscribe
        else:
            toggle = discord.ui.Button(label=SUBSCRIBE_LABEL, style=discord.ButtonStyle.success)
            toggle.callback = self._subscribe
        self.add_item(toggle)

        if offer_dismiss and not subscribed:
            dismiss = discord.ui.Button(label="Not Interested", style=discord.ButtonStyle.secondary)
            dismiss.callback = self._dismiss
            self.add_item(dismiss)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member_id:
            await interaction.response.send_message(
                "That button belongs to someone else - use `/wyr notify` to manage your own pings.",
                ephemeral=True,
            )
            return False
        return True

    async def _subscribe(self, interaction: discord.Interaction):
        await apply_subscription(interaction, subscribe=True)

    async def _unsubscribe(self, interaction: discord.Interaction):
        await apply_subscription(interaction, subscribe=False)

    async def _dismiss(self, interaction: discord.Interaction):
        await set_dismissed(interaction.guild_id, interaction.user.id, True)
        logger.info(f"{interaction.user} ({interaction.user.id}) dismissed the WYR notify prompt")
        await _reply(
            interaction,
            "Got it - I won't bring this up again. `/wyr notify` is there if you change your mind.",
            None,
        )


class NotifyButton(discord.ui.Button):
    """The persistent "Notify Me" button carried by every daily question post.

    Deliberately not a toggle: a stray click on a public message should never
    silently take someone's role away. Members who already have it get told so,
    with the turn-off button attached.
    """

    def __init__(self):
        super().__init__(
            label="Notify Me",
            style=discord.ButtonStyle.secondary,
            emoji="🔔",
            custom_id=NOTIFY_BUTTON_ID,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "WYR notifications can only be managed inside a server.", ephemeral=True
            )
            return

        role = await get_notify_role(guild)
        if role is None:
            await interaction.response.send_message(
                await _not_available(guild, member), ephemeral=True
            )
            return

        if role in member.roles:
            await interaction.response.send_message(
                f"🔔 You already have **{role.name}** - you're being pinged for new questions.",
                view=NotifyManageView(member_id=member.id, subscribed=True),
                ephemeral=True,
            )
            return

        await apply_subscription(interaction, subscribe=True)


async def build_status_view(member: discord.Member) -> tuple[str, discord.ui.View | None]:
    """Message and controls describing where a member stands. Used by /wyr notify."""
    guild = getattr(member, "guild", None)
    role = await get_notify_role(guild)
    if role is None:
        return await _not_available(guild, member), None

    subscribed = role in member.roles
    if subscribed:
        content = (
            f"🔔 **Notifications on.** You have **{role.name}**, so you'll be pinged "
            f"when a new Would You Rather question is posted."
        )
    else:
        content = (
            f"🔕 **Notifications off.** Pick up **{role.name}** to get pinged when a new "
            f"Would You Rather question is posted."
        )
    return content, NotifyManageView(member_id=member.id, subscribed=subscribed)