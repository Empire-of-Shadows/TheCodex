"""Feature-usage tracking.

Answers the question the owner actually asked: "how much is each feature used, and
which part of it" - after noticing features had quietly fallen out of use without it
being obvious which, or when.

WHY THIS IS ONE COG AND NOT INSTRUMENTATION IN FIFTY COMMANDS
-------------------------------------------------------------
discord.py's CommandTree dispatches `app_command_completion` for every application
command that finishes successfully, and `on_interaction` fires for every component
interaction. Listening to those two events records the whole bot from one file. No
command has to remember to call a tracker, so nothing can be missed by omission, and
adding a feature later needs no instrumentation work at all.

Only COMPLETED commands are counted. A command that raised is not usage of a working
feature - it is a fault, and the error handler already owns that story.

PRIVACY: AGGREGATE ONLY, BY CONSTRUCTION
----------------------------------------
No user id is ever written. Counters are per guild, per day, per feature, per action.
That is a deliberate design constraint, not an oversight: it means this creates no new
personal data, needs no opt-out, cannot profile a member, and does not have to be
touched when someone exercises their privacy rights. If a future change wants per-user
figures, that is a NEW decision with a privacy review, not an extension of this file.

FAILURE ISOLATION
-----------------
Tracking must never break the thing it is measuring. Every path is wrapped; a failure
is logged and swallowed. A missing counter is a cosmetic loss, a broken command is not.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

import discord
from discord.ext import commands

from storage.settings.collections import db_manager
from storage.log import get_logger

logger = get_logger(__name__)

COLLECTION_KEY = "serverdata_feature_usage"

# Mongo forbids "." in a key and treats a leading "$" as an operator, and these
# segments are built from command and component names we do not control.
_UNSAFE = re.compile(r"[.$\x00]")
_MAX_SEGMENT = 48


def _safe_key(value: str, fallback: str = "unknown") -> str:
    """Make an arbitrary name safe to use as a Mongo document key."""
    cleaned = _UNSAFE.sub("_", (value or "").strip())
    cleaned = cleaned.lstrip("$").strip()
    return (cleaned[:_MAX_SEGMENT] or fallback)


def split_command_name(qualified_name: str) -> Tuple[str, str]:
    """Split a slash command's qualified name into (feature, action).

    discord.py gives group commands a space-separated qualified name, which maps
    exactly onto the feature / sub-feature split the owner asked for:

        "wyr submit"   -> ("wyr", "submit")
        "guide"        -> ("guide", "use")
        "embed edit"   -> ("embed", "edit")

    A bare command has no sub-feature, so it records the action "use" rather than
    duplicating the feature name - that keeps `features.<name>.actions` meaningful
    for grouped and ungrouped commands alike.
    """
    parts = [p for p in (qualified_name or "").split() if p]
    if not parts:
        return "unknown", "use"
    if len(parts) == 1:
        return _safe_key(parts[0]), "use"
    return _safe_key(parts[0]), _safe_key("_".join(parts[1:]))


def split_custom_id(custom_id: str) -> Optional[Tuple[str, str]]:
    """Derive (feature, action) from a component's custom_id.

    Codex custom_ids are colon- or underscore-delimited, e.g. "guide:page:3" or
    "wyr_vote". The first segment is the feature and the second (when present) the
    action. Returns None for an id with nothing usable in it, so an unrecognised
    component is skipped rather than recorded as noise.
    """
    if not custom_id:
        return None
    parts = [p for p in re.split(r"[:|]", custom_id) if p]
    if not parts:
        return None
    if len(parts) == 1:
        sub = [p for p in parts[0].split("_") if p]
        if not sub:
            return None
        feature = _safe_key(sub[0])
        action = _safe_key("_".join(sub[1:])) if len(sub) > 1 else "click"
        return feature, action
    return _safe_key(parts[0]), _safe_key(parts[1])


async def record_usage(guild_id: Optional[int | str], feature: str, action: str,
                       surface: str = "command") -> bool:
    """Increment the counters for one use of one feature. Never raises.

    Returns True when a counter was written, False when the event was skipped or the
    write failed - the caller does not care, but the tests do.
    """
    if guild_id is None:
        return False  # DMs have no guild to attribute usage to
    try:
        feature = _safe_key(feature)
        action = _safe_key(action)
        surface = _safe_key(surface, "other")
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        collection = db_manager.get_collection_manager(COLLECTION_KEY)
        await collection.update_one(
            {"guild_id": str(guild_id), "date": today},
            {
                "$inc": {
                    "total": 1,
                    f"features.{feature}.total": 1,
                    f"features.{feature}.actions.{action}": 1,
                    f"surfaces.{surface}": 1,
                },
                "$setOnInsert": {"created_at": datetime.now(tz=timezone.utc)},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        # Never let measurement break the thing being measured.
        logger.warning(f"Feature usage not recorded ({feature}/{action}): {e}")
        return False


class UsageTracker(commands.Cog):
    """Records which features get used, from two central listeners."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_app_command_completion(
        self, interaction: discord.Interaction, command
    ) -> None:
        """Every slash command that completes successfully, from one place."""
        try:
            name = getattr(command, "qualified_name", None) or getattr(command, "name", "")
            feature, action = split_command_name(name)
            await record_usage(interaction.guild_id, feature, action, surface="command")
        except Exception as e:
            logger.warning(f"Usage tracking failed for a completed command: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Component usage - the "which part of that feature" half.

        Filtered to components on purpose: on_interaction also fires for application
        commands, which on_app_command_completion already counts. Counting both would
        double every command and make the totals meaningless.
        """
        try:
            if interaction.type is not discord.InteractionType.component:
                return
            custom_id = (interaction.data or {}).get("custom_id", "")
            split = split_custom_id(custom_id)
            if split is None:
                return
            feature, action = split
            await record_usage(interaction.guild_id, feature, action, surface="component")
        except Exception as e:
            logger.warning(f"Usage tracking failed for a component interaction: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UsageTracker(bot))
    logger.info("UsageTracker loaded - feature usage is being recorded")
