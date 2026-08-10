"""
Question Bank actions - the admin-panel business logic for a guild's own daily questions.

Splits cleanly from ``wyr_actions.py``, which owns the SCHEDULING settings (channel,
time, threads). This module owns the CONTENT: which bank a guild draws from, which
formats it posts, and the questions it has added itself.

Everything here reaches Mongo through ``Features.daily.wyr_bank``, so the panel, the
bulk importer and (later) the submission approval path all insert questions through one
code path with one set of rules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from storage.log import get_logger

from Features.daily.wyr_bank import (
    FORMAT_LABELS,
    FORMATS,
    question_options,
    validate_question,
    wyr_bank,
)
from Features.daily.wyr_schema import parse_wyr_import

logger = get_logger("WYRQuestionActions")

#: Where a guild's daily questions come from.
QUESTION_SOURCE_OPTIONS = [
    ("both", "Shared + my own (Default)",
     "Post from the shared question bank and this server's own questions"),
    ("guild_only", "Only my own",
     "Post only questions added in this server"),
    ("global_only", "Only the shared bank",
     "Post only questions from the shared bank"),
]

#: The formats a guild posts. Multi-select - a server can run any mix.
QUESTION_FORMAT_OPTIONS = [
    ("wyr", "Would You Rather (Default)", "Two or three choices to pick between"),
    ("poll", "Question with answers", "Any question with up to five answers"),
    ("open", "Open-ended question", "A prompt with no answers - discussion only"),
]


async def _get_gcm():
    """Get the global GuildConfigManager instance."""
    from storage.settings.config_manager import get_guild_config_manager
    return await get_guild_config_manager()


async def _read(guild_id: int, key: str, default=None):
    gcm = await _get_gcm()
    config = await gcm.get_config(guild_id)
    return config.wyr.get(key, default)


async def _write(guild_id: int, key: str, value) -> bool:
    """Write one wyr key.

    Always mutates a config obtained from ``get_config`` so ``save_config`` stays
    surgical - a hand-built GuildConfig has no loaded snapshot and falls back to
    rewriting every section, which can clobber a concurrent dashboard edit.
    """
    gcm = await _get_gcm()
    config = await gcm.get_config(guild_id)
    config.wyr[key] = value
    return await gcm.save_config(config)


class WYRQuestionActions:
    """Static async methods backing the Question Bank panel nodes."""

    # -- Where questions come from ----------------------------------------

    @staticmethod
    async def get_question_source_as_list(guild_id: int) -> List[str]:
        return [str(await _read(guild_id, "question_source", "both"))]

    @staticmethod
    async def set_question_source_from_list(guild_id: int, values: list) -> bool:
        if not values:
            return False
        value = str(values[0])
        if value not in {opt[0] for opt in QUESTION_SOURCE_OPTIONS}:
            return False
        return await _write(guild_id, "question_source", value)

    # -- Which formats this server posts ----------------------------------

    @staticmethod
    async def get_question_formats(guild_id: int) -> List[str]:
        formats = await _read(guild_id, "question_formats", ["wyr"])
        return [f for f in FORMATS if f in (formats or [])] or ["wyr"]

    @staticmethod
    async def set_question_formats(guild_id: int, values: list) -> bool:
        """Save the selected formats.

        An empty selection is refused rather than stored: it would make the
        selection filter match no question at all and silently stop the daily
        post, which is the exact failure this feature exists to prevent.
        """
        chosen = [f for f in FORMATS if f in {str(v) for v in (values or [])}]
        if not chosen:
            return False
        return await _write(guild_id, "question_formats", chosen)

    @staticmethod
    async def enable_format(guild_id: int, question_format: str) -> bool:
        """Add one format to the enabled list, keeping the rest.

        Backs the one-click "enable this format" offered wherever a question is
        added in a format the server does not currently post.
        """
        if question_format not in FORMATS:
            return False
        current = await WYRQuestionActions.get_question_formats(guild_id)
        if question_format in current:
            return True
        merged = [f for f in FORMATS if f in set(current) | {question_format}]
        return await _write(guild_id, "question_formats", merged)

    # -- Submissions -------------------------------------------------------

    @staticmethod
    async def get_submission_settings(guild_id: int) -> Dict[str, Any]:
        gcm = await _get_gcm()
        config = await gcm.get_config(guild_id)
        wyr = config.wyr
        return {
            "enabled": bool(wyr.get("submissions_enabled", False)),
            "review_channel_id": wyr.get("submission_review_channel_id"),
            "moderator_role_id": wyr.get("submission_moderator_role_id"),
            "max_pending": int(wyr.get("submission_max_pending", 3) or 3),
        }

    @staticmethod
    async def get_submissions_enabled(guild_id: int) -> bool:
        return bool(await _read(guild_id, "submissions_enabled", False))

    @staticmethod
    async def set_submissions_enabled(guild_id: int, enabled: bool) -> bool:
        return await _write(guild_id, "submissions_enabled", bool(enabled))

    @staticmethod
    async def get_review_channel_as_list(guild_id: int) -> List[str]:
        channel_id = await _read(guild_id, "submission_review_channel_id")
        return [str(channel_id)] if channel_id else []

    @staticmethod
    async def set_review_channel(guild_id: int, ids: list) -> bool:
        if not ids:
            return False
        return await _write(guild_id, "submission_review_channel_id", int(ids[0]))

    @staticmethod
    async def clear_review_channel(guild_id: int) -> bool:
        return await _write(guild_id, "submission_review_channel_id", None)

    @staticmethod
    async def get_reviewer_role_as_list(guild_id: int) -> List[str]:
        role_id = await _read(guild_id, "submission_moderator_role_id")
        return [str(role_id)] if role_id else []

    @staticmethod
    async def set_reviewer_role(guild_id: int, ids: list) -> bool:
        if not ids:
            return False
        return await _write(guild_id, "submission_moderator_role_id", int(ids[0]))

    @staticmethod
    async def clear_reviewer_role(guild_id: int) -> bool:
        return await _write(guild_id, "submission_moderator_role_id", None)

    @staticmethod
    async def get_max_pending_as_list(guild_id: int) -> List[str]:
        return [str(await _read(guild_id, "submission_max_pending", 3))]

    @staticmethod
    async def set_max_pending_from_list(guild_id: int, values: list) -> bool:
        if not values:
            return False
        try:
            return await _write(guild_id, "submission_max_pending", int(values[0]))
        except (TypeError, ValueError):
            return False

    @staticmethod
    async def submissions_summary(guild_id: int) -> str:
        """Summary for the Member Suggestions entry on the Question Bank menu."""
        try:
            settings = await WYRQuestionActions.get_submission_settings(guild_id)
        except Exception:
            logger.debug("submission summary failed", exc_info=True)
            return "Not configured"
        if not settings["enabled"]:
            return "Not configured"
        if not settings["review_channel_id"] and not settings["moderator_role_id"]:
            return "On, but nobody can review"
        try:
            from Features.daily.wyr_submissions import wyr_submissions
            waiting = await wyr_submissions.count_open(guild_id)
        except Exception:
            logger.debug("submission count failed", exc_info=True)
            waiting = 0
        return f"On, {waiting} waiting" if waiting else "On"

    @staticmethod
    async def can_review(member) -> bool:
        """Whether this member may approve or decline suggestions.

        Administrator, OR a panel admin role, OR the configured reviewer role.
        Shaped on ``DropsActions.has_drops_management``.

        Deliberately not inferred from channel access: a review channel is
        usually visible to more people than may act on what is in it.
        """
        guild = getattr(member, "guild", None)
        if guild is None:
            return False
        perms = getattr(member, "guild_permissions", None)
        if perms is not None and perms.administrator:
            return True

        gcm = await _get_gcm()
        config = await gcm.get_config(guild.id)
        member_role_ids = {r.id for r in getattr(member, "roles", [])}
        if member_role_ids & set(config.roles.get("admin_role_ids") or []):
            return True

        reviewer_role_id = config.wyr.get("submission_moderator_role_id")
        if not reviewer_role_id:
            return False
        try:
            return int(reviewer_role_id) in member_role_ids
        except (TypeError, ValueError):
            return False

    # -- The mismatch warning ---------------------------------------------

    @staticmethod
    async def unposted_formats(guild_id: int) -> Dict[str, int]:
        """Formats present in this guild's bank that the guild does not post.

        Returns ``{format: count}``, empty when everything in the bank is
        postable. This is the trap the whole feature exists to avoid: a server
        approves or imports questions and then never sees them, with nothing
        anywhere saying why.
        """
        enabled = set(await WYRQuestionActions.get_question_formats(guild_id))
        counts = await wyr_bank.count_by_format(guild_id)
        return {fmt: n for fmt, n in counts.items() if n > 0 and fmt not in enabled}

    @staticmethod
    async def mismatch_warning(guild_id: int) -> str:
        """One-line warning about unpostable questions, or "" when all is well."""
        stranded = await WYRQuestionActions.unposted_formats(guild_id)
        if not stranded:
            return ""
        parts = [f"{n} {FORMAT_LABELS[fmt].lower()}" for fmt, n in sorted(stranded.items())]
        return (
            f"⚠️ Your bank holds {' and '.join(parts)} that this server does not post "
            f"right now. Turn the type on under **Question Types** to start using them."
        )

    @staticmethod
    async def warning_for_format(guild_id: int, question_format: str) -> str:
        """Warning shown right after adding a question of a not-posted format."""
        enabled = await WYRQuestionActions.get_question_formats(guild_id)
        if question_format in enabled:
            return ""
        label = FORMAT_LABELS.get(question_format, question_format)
        return (
            f"⚠️ This server does not post **{label}** questions right now, so this one "
            f"will sit in the bank unused until you turn that type on."
        )

    # -- Browsing the bank -------------------------------------------------

    @staticmethod
    async def list_bank_items(guild_id: int) -> List[Dict[str, Any]]:
        """Every question this guild owns, newest first.

        Bounded well above the panel's page size so a large bank still pages,
        without pulling an unbounded result set into memory for one screen.
        """
        return await wyr_bank.list_questions(guild_id, owned_only=True, limit=500)

    @staticmethod
    async def count_bank_items(guild_id: int) -> int:
        return await wyr_bank.count_questions(guild_id, owned_only=True)

    @staticmethod
    async def delete_bank_item(guild_id: int, value: str) -> bool:
        """Delete one of this guild's own questions.

        ``value`` arrives from the panel select as a STRING while the question
        number is an int, so it is cast here. Without that the delete query
        would match nothing and report a silent failure.
        """
        try:
            question_id = int(value)
        except (TypeError, ValueError):
            logger.warning(f"Ignoring a non-numeric question id from the panel: {value!r}")
            return False
        return await wyr_bank.delete_question(question_id, guild_id)

    @staticmethod
    def format_bank_line(item: Dict[str, Any], index: int) -> str:
        """The display line for one question in the browse list."""
        fmt = item.get("format") or "wyr"
        badge = {"wyr": "🎲", "poll": "📊", "open": "💬"}.get(fmt, "•")
        text = str(item.get("original") or "")
        if len(text) > 90:
            text = text[:87] + "..."
        options = question_options(item)
        detail = f" · {len(options)} options" if options else ""
        nsfw = " · 🔞" if item.get("nsfw") else ""
        return f"{badge} **#{item.get('id')}** {text}{detail}{nsfw}"

    @staticmethod
    def bank_item_value(item: Dict[str, Any]) -> str:
        return str(item.get("id"))

    @staticmethod
    def bank_item_option_label(item: Dict[str, Any], index: int) -> str:
        """Select-option label. Discord caps these at 100 characters."""
        text = str(item.get("original") or "")
        label = f"#{item.get('id')} {text}"
        return label[:97] + "..." if len(label) > 100 else label

    @staticmethod
    def bank_confirm_line(item: Dict[str, Any]) -> str:
        text = str(item.get("original") or "")
        if len(text) > 120:
            text = text[:117] + "..."
        return f"Delete question **#{item.get('id')}**?\n> {text}"

    # -- Adding one question ----------------------------------------------

    @staticmethod
    async def add_question(guild_id: int, question_format: str, text: str,
                           options: List[str], tags: List[str],
                           nsfw: bool = False) -> Tuple[bool, str, Optional[dict]]:
        """Validate and add one question to this guild's bank.

        Returns ``(ok, message, question)``. The message is written for an admin
        to read, not for a log.
        """
        ok, cleaned, error = validate_question(question_format, text, options, tags)
        if not ok:
            return False, error, None

        from Features.daily.wyr_bank import normalize_text_key
        text_key = normalize_text_key(
            cleaned["format"], cleaned["original"],
            [v for _, v in question_options(cleaned)],
        )
        existing = await wyr_bank.find_duplicate(text_key, guild_id)
        if existing:
            where = ("the shared bank" if existing.get("scope") == "global"
                     else "this server's questions")
            return False, (
                f"That question is already in {where} as **#{existing.get('id')}**."
            ), None

        question = await wyr_bank.insert_question(
            cleaned, guild_id=guild_id, source="admin", nsfw=nsfw
        )
        if not question:
            return False, "Could not save that question. Please try again.", None
        return True, f"Added as question **#{question['id']}**.", question

    # -- Bulk import -------------------------------------------------------

    #: Handoff for the detail line shown after an upload. The engine calls
    #: set_values and then post_save_hook within the same request, and the
    #: summary is only worth showing once, so it is passed here rather than
    #: stored. A lost entry costs a detail line, nothing more.
    _last_import: Dict[int, Dict[str, Any]] = {}

    @staticmethod
    async def import_questions(guild_id: int, values: list) -> bool:
        """Panel ``set_values`` for the bulk-import node.

        Receives the decoded file text. Re-parses rather than trusting the
        earlier schema pass, so the file that is inserted is exactly the file
        that validated.
        """
        text = values[0] if values else ""
        ok, cleaned_items, nsfw_flags, error = parse_wyr_import(text)
        if not ok:
            logger.warning(f"Rejected a question import for guild {guild_id}: {error}")
            WYRQuestionActions._last_import[int(guild_id)] = {"error": error}
            return False

        summary = await wyr_bank.insert_many_questions(
            cleaned_items, guild_id=guild_id, source="import", nsfw_flags=nsfw_flags
        )
        WYRQuestionActions._last_import[int(guild_id)] = summary
        # An upload whose questions were all duplicates still succeeded as an
        # upload; the summary explains what happened.
        return True

    @staticmethod
    async def import_result_text(guild_id: int) -> str:
        """The detail line for the last import, consumed once."""
        summary = WYRQuestionActions._last_import.pop(int(guild_id), None)
        if not summary:
            return ""
        if summary.get("error"):
            return f"❌ {summary['error']}"

        parts = [f"Added **{summary['added']}** question(s)"]
        if summary.get("duplicates"):
            parts.append(f"skipped **{summary['duplicates']}** already in the bank")
        if summary.get("failed"):
            parts.append(f"**{summary['failed']}** could not be saved")
        line = ", ".join(parts) + "."

        by_format = summary.get("formats") or {}
        breakdown = [f"{n} {FORMAT_LABELS[fmt].lower()}"
                     for fmt, n in by_format.items() if n]
        if breakdown:
            line += f"\nThat is {', '.join(breakdown)}."

        warning = await WYRQuestionActions.mismatch_warning(guild_id)
        if warning:
            line += f"\n\n{warning}"
        return line

    @staticmethod
    async def get_import_placeholder(guild_id: int) -> List[str]:
        """``get_values`` for the import node.

        An import stores no config, so there is no value to show. This reports
        the state that actually matters - what is in the bank now - and is what
        the engine re-renders the screen with after a successful upload.
        """
        total = await WYRQuestionActions.count_bank_items(guild_id)
        if not total:
            return []
        counts = await wyr_bank.count_by_format(guild_id)
        breakdown = ", ".join(f"{n} {FORMAT_LABELS[fmt].lower()}"
                              for fmt, n in counts.items() if n)
        return [f"{total} question(s) in this server's bank ({breakdown})"]

    # -- Summaries ---------------------------------------------------------

    @staticmethod
    async def bank_summary(guild_id: int) -> str:
        """Summary line for the Question Bank entry on the parent menu.

        Must return one of the engine's "unset" strings when there is nothing,
        or the category's "N of M configured" badge over-counts.
        """
        try:
            total = await WYRQuestionActions.count_bank_items(guild_id)
        except Exception:
            logger.debug("question bank summary failed", exc_info=True)
            return "Empty"
        if not total:
            return "Empty"
        stranded = await WYRQuestionActions.unposted_formats(guild_id)
        if stranded:
            return f"{total} question(s), {sum(stranded.values())} not being posted"
        return f"{total} question(s)"

    @staticmethod
    async def bank_summary_values(guild_id: int) -> list:
        """Non-empty when this guild owns any questions - drives "configured"."""
        try:
            return ["bank"] if await WYRQuestionActions.count_bank_items(guild_id) else []
        except Exception:
            logger.debug("question bank summary values failed", exc_info=True)
            return []

    @staticmethod
    async def get_overview(guild_id: int) -> Dict[str, Any]:
        """Everything the WYR status screen needs about question content."""
        try:
            formats = await WYRQuestionActions.get_question_formats(guild_id)
            return {
                "question_source": await _read(guild_id, "question_source", "both"),
                "question_formats": formats,
                "bank_total": await WYRQuestionActions.count_bank_items(guild_id),
                "bank_by_format": await wyr_bank.count_by_format(guild_id),
                "unposted": await WYRQuestionActions.unposted_formats(guild_id),
            }
        except Exception:
            logger.debug("question bank overview failed", exc_info=True)
            return {
                "question_source": "both", "question_formats": ["wyr"],
                "bank_total": 0, "bank_by_format": {}, "unposted": {},
            }
