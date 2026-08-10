"""
Whitelist browse admin-panel node.

Replaces the two admin-only whitelist screens that were slash commands:

* ``/whitelist list``  - a flat embed capped at 25 entries, with no way past it.
* ``/whitelist check`` - "is this one person whitelisted?", which browsing the
  whole list answers without anybody having to type a snowflake.

Both were admin-tier reads, so they belong on the panel rather than in the
command tree. Acting on one named person stays a command: the single
``/whitelist`` command resolves them, shows where they stand, and offers the one
action that state allows. Its Remove step calls ``remove_entry`` below, so there
is one removal implementation and not two.

Shape follows ``wyr_question_nodes.build_wyr_question_bank_node``: a
``paginated_list`` node, so the engine owns the paging, the per-item select
(bounded to one page, never over Discord's 25-option cap), the Confirm/Cancel
step in front of the destructive action, the autosave cooldown, the audit entry
and the cache invalidation. What is left here is the queries and the formatting.

Storage is the same collection the command uses (``serverdata_whitelist``) with
the same filters - guild id and user id are STRINGS in storage, so every filter
casts, or it matches nothing and reports a silent failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import discord

from storage.log import get_logger
from storage.settings.collections import db_manager
from storage.settings.config_manager import get_config

from ..views.panel_engine import PanelNode

logger = get_logger("WhitelistNodes")

NODE_KEY = "nm_whitelist_browse"
NODE_LABEL = "Whitelisted Members"

_COLLECTION = "serverdata_whitelist"

#: Items per page. Well under Discord's 25-option cap on the per-item select.
_PAGE_SIZE = 10

#: Upper bound on one fetch, so browsing never pulls an unbounded result set into
#: memory for a single screen. The summary count is exact and unbounded, so a
#: guild holding more than this sees a true total with only the newest entries
#: reachable by paging - which is the right trade for a screening exemption list
#: that is a handful of people in practice.
_FETCH_LIMIT = 500

#: Discord audit-log reason written when the panel's Remove takes the whitelist
#: role back off a member. It is the DEFAULT rather than a literal down in
#: ``_strip_whitelist_role`` so the command path can name its own surface and
#: the acting admin; leaving the default alone keeps the panel path unchanged.
_PANEL_STRIP_REASON = "Removed from the whitelist through the admin panel"


def _collection():
    """The whitelist collection manager. Resolved per call, never at import."""
    return db_manager.get_collection_manager(_COLLECTION)


def _added_at_text(entry: Dict[str, Any]) -> str:
    """Relative timestamp for when an entry was added, or a plain fallback."""
    added_at = entry.get("added_at")
    if isinstance(added_at, datetime):
        return f"<t:{int(added_at.timestamp())}:R>"
    return "at an unknown time"


def _added_by_text(entry: Dict[str, Any]) -> str:
    """Who added the entry - a mention, since the panel is ephemeral and cannot ping."""
    added_by = entry.get("added_by")
    if added_by:
        return f"<@{added_by}>"
    return entry.get("added_by_username") or "someone no longer recorded"


class WhitelistPanelActions:
    """Static async methods backing the whitelist browse node."""

    # -- reads -------------------------------------------------------------

    @staticmethod
    async def list_entries(guild_id: int) -> List[Dict[str, Any]]:
        """Every member currently on this guild's whitelist, newest first.

        Only active entries: a removal is a soft delete (``is_active: False``),
        and a removed member is not on the whitelist any more, so showing them
        would make the screen disagree with what the join gate actually does.
        """
        try:
            return await _collection().find_many(
                {"guild_id": str(guild_id), "is_active": True},
                sort=[("added_at", -1)],
                limit=_FETCH_LIMIT,
            )
        except Exception:
            logger.error(
                f"Could not list whitelist entries for guild {guild_id}", exc_info=True
            )
            return []

    @staticmethod
    async def count_entries(guild_id: int) -> int:
        """Exact count of active entries, done in Mongo.

        The engine falls back to ``len(list_get_items(...))`` when this is absent,
        which would fetch and discard every document just to render one summary
        line on the parent menu.
        """
        try:
            return await _collection().count_documents(
                {"guild_id": str(guild_id), "is_active": True}
            )
        except Exception:
            logger.error(
                f"Could not count whitelist entries for guild {guild_id}", exc_info=True
            )
            return 0

    # -- formatting --------------------------------------------------------

    @staticmethod
    def format_line(entry: Dict[str, Any], index: int) -> str:
        """The display block for one whitelisted member.

        ``index`` is the absolute 0-based position in the full list, so the
        numbering keeps counting across pages.
        """
        username = entry.get("username") or "Unknown"
        user_id = entry.get("user_id")
        role_state = "role assigned" if entry.get("role_assigned") else "no role"
        reason = str(entry.get("reason") or "No reason recorded")
        if len(reason) > 90:
            reason = reason[:87] + "..."
        return (
            f"**{index + 1}. {username}** - <@{user_id}> (`{user_id}`)\n"
            f"> Added {_added_at_text(entry)} by {_added_by_text(entry)} "
            f"· {role_state}\n"
            f"> {reason}"
        )

    @staticmethod
    def item_value(entry: Dict[str, Any]) -> str:
        """Stable id for the per-item select.

        Returned as a STRING, which is also how the id is stored - the value comes
        back off the select as a string and is used in the filter unchanged.
        """
        return str(entry.get("user_id"))

    @staticmethod
    def item_option_label(entry: Dict[str, Any], index: int) -> str:
        """Select-option label. Discord caps these at 100 characters."""
        username = entry.get("username") or "Unknown"
        label = f"{index + 1}. {username} ({entry.get('user_id')})"
        return label[:97] + "..." if len(label) > 100 else label

    @staticmethod
    def confirm_line(entry: Dict[str, Any]) -> str:
        """Text of the Confirm step the engine puts in front of a removal."""
        username = entry.get("username") or "Unknown"
        extra = (
            "\nTheir whitelist role will be taken off as well."
            if entry.get("role_assigned")
            else ""
        )
        return (
            f"Take **{username}** (`{entry.get('user_id')}`) off the whitelist?\n"
            f"They will be screened on account age like anyone else from now on."
            f"{extra}"
        )

    # -- the per-item action -----------------------------------------------

    @staticmethod
    async def remove_entry(
        guild_id: int,
        value: str,
        actor_id: int | None = None,
        role_reason: str | None = None,
    ) -> bool:
        """Take one member off the whitelist. The only removal implementation.

        Both callers land here: the panel's per-item Remove, and the Remove step
        on the ``/whitelist`` card.

        A soft delete: readers everywhere filter on ``is_active: True``, and
        keeping the document preserves who added the member and why.

        ``actor_id`` records who did the removal and ``role_reason`` is the
        Discord audit-log reason for taking the whitelist role back off. Both are
        optional because the engine calls ``list_action(guild_id, value)``
        positionally with nothing else to give - so the panel path is unchanged
        and keeps ``_PANEL_STRIP_REASON``, while the command passes the admin who
        pressed the button and a reason naming the command.

        Returns False for an entry that is already gone or already inactive, which
        the engine turns into a "Failed to remove" notice and a re-render - the
        right answer when two admins are looking at the same list.
        """
        guild_key = str(guild_id)
        user_key = str(value)
        try:
            collection = _collection()
            entry = await collection.find_one(
                {"guild_id": guild_key, "user_id": user_key}
            )
            if not entry or not entry.get("is_active", True):
                return False

            updates: Dict[str, Any] = {
                "is_active": False,
                "removed_at": datetime.now(timezone.utc),
            }
            if actor_id is not None:
                updates["removed_by"] = str(actor_id)

            removed = await collection.update_one(
                {"guild_id": guild_key, "user_id": user_key},
                {"$set": updates},
            )
        except Exception:
            logger.error(
                f"Could not remove {user_key} from the whitelist in guild {guild_key}",
                exc_info=True,
            )
            return False

        if not removed:
            return False

        if entry.get("role_assigned"):
            await WhitelistPanelActions._strip_whitelist_role(
                guild_key, user_key, role_reason or _PANEL_STRIP_REASON
            )

        actor = f"by {actor_id}" if actor_id is not None else "through the admin panel"
        logger.info(
            f"Whitelist entry {user_key} removed {actor} in guild {guild_key}"
        )
        return True

    @staticmethod
    async def _strip_whitelist_role(
        guild_key: str, user_key: str, reason: str = _PANEL_STRIP_REASON
    ) -> None:
        """Take the whitelist role back off a member, best effort.

        The engine hands ``list_action`` only ``(guild_id, value)``, so the guild
        object is resolved from the bot singleton the same way the hourly
        ``WhitelistRoleCleanupTask`` does. Imported lazily so importing the panel
        tree does not pull in the gateway client.

        ``reason`` is what Discord's audit log shows. It defaults to the panel's
        wording so that path is unchanged; the ``/whitelist`` command passes one
        naming the command and the admin who pressed the button.

        Failure here is logged and swallowed on purpose: the member is already off
        the whitelist in storage, and reporting the whole removal as failed would
        invite an admin to retry an action that has already happened. The stored
        ``role_assigned`` flag below is therefore the only signal a caller has
        about whether the role actually came off - it is cleared on this path and
        nowhere else in this function.
        """
        try:
            from startup.bot import bot

            guild = bot.get_guild(int(guild_key))
            if guild is None:
                return
            member = guild.get_member(int(user_key))
            if member is None:
                return

            config = await get_config(int(guild_key))
            role = None
            if config.new_members["whitelist_role_id"]:
                role = guild.get_role(config.new_members["whitelist_role_id"])
            if role is None:
                role = discord.utils.get(
                    guild.roles, name=config.new_members["whitelist_role_name"]
                )
            if role is None or role not in member.roles:
                return

            await member.remove_roles(role, reason=reason)
            # The role is off, so the stored flag has to follow it. The hourly
            # cleanup task clears the flag the same way when it removes the role;
            # leaving it set would tell a later re-add that the member still has
            # a role they no longer have.
            await _collection().update_one(
                {"guild_id": guild_key, "user_id": user_key},
                {"$set": {"role_assigned": False}},
            )
            logger.info(f"Removed the whitelist role from {member} in guild {guild_key}")
        except Exception:
            logger.error(
                f"Could not remove the whitelist role from {user_key} "
                f"in guild {guild_key}",
                exc_info=True,
            )


async def whitelist_summary(guild_id: int) -> str:
    """Summary line for this node on the New Members menu."""
    total = await WhitelistPanelActions.count_entries(guild_id)
    if not total:
        return "Empty"
    return f"{total} member(s)" if total != 1 else "1 member"


def build_whitelist_browse_node() -> PanelNode:
    """Browse the whitelist, with removal behind the engine's confirm step.

    ``counts_as_setting=False`` is required, not cosmetic. ``paginated_list``
    otherwise infers True and the "N of M configured" badge on New Members would
    read this row as unconfigured on every server whose whitelist is empty - and
    an empty whitelist is a perfectly configured server, not a missing setting.
    The summary line still renders, because ``summary_builder`` is independent of
    the badge.
    """
    return PanelNode(
        key=NODE_KEY,
        label=NODE_LABEL,
        kind="paginated_list",
        description=(
            "Everyone allowed past the account-age check on this server, newest "
            "first.\n\n"
            "Removing someone takes them off the list and takes the whitelist role "
            "back off them; from then on they are screened like anybody else. Use "
            "`/whitelist` to look one person up and put them on the list or take "
            "them off."
        ),
        list_get_items=WhitelistPanelActions.list_entries,
        list_count=WhitelistPanelActions.count_entries,
        list_format_line=WhitelistPanelActions.format_line,
        list_item_value=WhitelistPanelActions.item_value,
        list_item_option_label=WhitelistPanelActions.item_option_label,
        list_action_label="Remove",
        list_action=WhitelistPanelActions.remove_entry,
        list_action_confirm_line=WhitelistPanelActions.confirm_line,
        list_page_size=_PAGE_SIZE,
        summary_builder=whitelist_summary,
        counts_as_setting=False,
    )
