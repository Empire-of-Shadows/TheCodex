"""
WYR Bank - the write path into the daily question bank (``Daily.WYR``).

Until this module existed there was no way to add a question except by hand in
Mongo, which is why a server could never fill the bank with its own material.

Two kinds of question live in the one collection, told apart by ``scope``:

  * ``scope: "global"``  - the shared bank every guild draws from. No ``guild_id``.
  * ``scope: "guild"``   - private to one server, carrying that ``guild_id``.

Selection always filters on scope, so a guild's private questions can never
surface in another server. Promotion moves a question from the second kind to
the first and is the bot owner's call alone.

Three formats, differing only in how many options they carry:

  * ``wyr``  - Would You Rather. 2 or 3 options.
  * ``poll`` - a general question with 2 to 5 answers.
  * ``open`` - an open-ended prompt with no options at all.

Two identifiers, and they are not interchangeable:

  * ``_id`` is an ObjectId assigned by Mongo. It is the question's identity, and
    what ``WYR_Mappings.question_id`` and ``WYR_Votes.question_id`` store.
  * ``id`` is an int question number, unique, and the one shown to humans - in
    the panel, and in the ``{question_num}`` thread placeholder. New questions
    continue that sequence through ``Daily.Counters``.

``source`` is NOT ours. In production it holds where a question was scraped from
(``griproom.com``, ``either.io``, ...) across all 4968 seeded questions. How a
question entered the bank is recorded separately, in ``added_via``.

Document shape::

    {
      _id: ObjectId("..."),             # identity, assigned by Mongo
      id: 5007,                         # int question number, from the counter
      original: "Would you rather ...",
      option_1 .. option_5,             # present per format
      nsfw: False, tags: ["silly"],
      source: "griproom.com",           # where it came from, when scraped
      scope: "guild", guild_id: "123",
      origin_guild_id: "123",           # set on promotion, when guild_id is dropped
      format: "wyr",
      text_key: "<sha256>",             # duplicate detection
      added_via: "admin",               # seed | admin | import | submission | owner
      submitted_by / approved_by / approved_at / promoted_by / promoted_at,
      created_at,
      guilds: { "<gid>": {used_count, last_posted, vote_counts} }   # written by the cog
    }
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError, DuplicateKeyError

from storage.log import get_logger
from storage.settings.collections import db_manager

logger = get_logger("WYRBank")


# ── Formats ──────────────────────────────────────────────────────────────────

FORMAT_WYR = "wyr"
FORMAT_POLL = "poll"
FORMAT_OPEN = "open"

#: Every format the bank accepts, in display order.
FORMATS: Tuple[str, ...] = (FORMAT_WYR, FORMAT_POLL, FORMAT_OPEN)

#: Human labels, used by the panel, the submission builder and every warning.
FORMAT_LABELS: Dict[str, str] = {
    FORMAT_WYR: "Would You Rather",
    FORMAT_POLL: "Question with answers",
    FORMAT_OPEN: "Open-ended question",
}

#: (minimum, maximum) options each format may carry. Would You Rather stays at
#: 3 because a fourth "would you rather" branch is a different kind of question -
#: that is what the poll format is for.
FORMAT_OPTION_RANGE: Dict[str, Tuple[int, int]] = {
    FORMAT_WYR: (2, 3),
    FORMAT_POLL: (2, 5),
    FORMAT_OPEN: (0, 0),
}

#: The hard ceiling across all formats. The vote buttons, the vote counters and
#: the leaderboard columns are all built to this number.
MAX_OPTIONS = 5

MAX_QUESTION_LENGTH = 500
MAX_OPTION_LENGTH = 200
MAX_TAGS = 8
MAX_TAG_LENGTH = 32

_COUNTER_ID = "wyr_question_id"
_MAX_ID_ATTEMPTS = 5

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)


# ── Shared helpers (imported by the cog, the panel and the migration) ─────────

def question_options(question: Dict[str, Any]) -> List[Tuple[int, str]]:
    """Return ``[(1, "..."), (2, "...")]`` for whichever options are present.

    The single place that knows options are stored as ``option_1`` .. ``option_5``
    rather than a list. Every renderer, vote handler and results tally reads
    through this, so raising the ceiling means changing ``MAX_OPTIONS`` alone.

    Discrete keys rather than a list is deliberate: a list would force a rewrite
    of every question already in production AND break the ``{option_1}``
    placeholders inside every guild's customized thread-starter template.
    """
    out: List[Tuple[int, str]] = []
    for n in range(1, MAX_OPTIONS + 1):
        value = question.get(f"option_{n}")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out.append((n, text))
    return out


def normalize_text_key(question_format: str, original: str,
                       options: Optional[List[str]] = None) -> str:
    """Build the duplicate-detection key for a question.

    Case, punctuation, accents and spacing are all discarded, and the options
    are sorted, so "Would you rather fly or swim?" and "would you rather swim
    or FLY" collapse to the same key. The result is a sha256 hex digest rather
    than the normalized text: it is fixed width, indexes cleanly, and cannot be
    truncated into a false match between two long questions sharing a prefix.

    The migration that backfills ``text_key`` imports THIS function rather than
    reimplementing it. A divergence between the two would silently disable
    duplicate detection against every pre-existing question.
    """
    parts = [_normalize_fragment(original)]
    # Sorted, so two submissions that differ only in option order collide.
    parts.extend(sorted(_normalize_fragment(o) for o in (options or []) if o))
    joined = f"{question_format}\x1f" + "\x1f".join(p for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _normalize_fragment(value: Any) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _NON_ALNUM.sub(" ", text.lower())
    return _WHITESPACE.sub(" ", text).strip()


def validate_question(question_format: str, original: str,
                      options: Optional[List[str]] = None,
                      tags: Optional[List[str]] = None
                      ) -> Tuple[bool, Dict[str, Any], str]:
    """Validate and clean one question.

    Returns ``(ok, cleaned, error)``. ``cleaned`` carries ``format``,
    ``original``, ``option_1``.. and ``tags``, ready to hand to
    :meth:`WYRBank.insert_question`.

    Shared by the add-question modal, the bulk importer and the submission
    builder so the three cannot drift into accepting different things.
    """
    fmt = (question_format or "").strip().lower()
    if fmt not in FORMATS:
        return False, {}, f"Unknown question type '{question_format}'."

    text = (original or "").strip()
    if not text:
        return False, {}, "The question text cannot be empty."
    if len(text) > MAX_QUESTION_LENGTH:
        return False, {}, f"The question is too long (max {MAX_QUESTION_LENGTH} characters)."

    cleaned_options = [str(o).strip() for o in (options or []) if str(o or "").strip()]
    low, high = FORMAT_OPTION_RANGE[fmt]

    if fmt == FORMAT_OPEN:
        if cleaned_options:
            return False, {}, "An open-ended question cannot have answer options."
    else:
        if len(cleaned_options) < low:
            return False, {}, (
                f"{FORMAT_LABELS[fmt]} needs at least {low} options - "
                f"you gave {len(cleaned_options)}."
            )
        if len(cleaned_options) > high:
            return False, {}, (
                f"{FORMAT_LABELS[fmt]} allows at most {high} options - "
                f"you gave {len(cleaned_options)}."
            )
        for option in cleaned_options:
            if len(option) > MAX_OPTION_LENGTH:
                return False, {}, f"An option is too long (max {MAX_OPTION_LENGTH} characters)."
        if len({o.lower() for o in cleaned_options}) != len(cleaned_options):
            return False, {}, "Two of the options are the same."

    cleaned_tags: List[str] = []
    for tag in tags or []:
        tag = str(tag).strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            return False, {}, f"A tag is too long (max {MAX_TAG_LENGTH} characters)."
        if tag not in cleaned_tags:
            cleaned_tags.append(tag)
    if len(cleaned_tags) > MAX_TAGS:
        return False, {}, f"Too many tags (max {MAX_TAGS})."

    cleaned: Dict[str, Any] = {"format": fmt, "original": text, "tags": cleaned_tags}
    for index, option in enumerate(cleaned_options, start=1):
        cleaned[f"option_{index}"] = option
    return True, cleaned, ""


class WYRBank:
    """Reads and writes for the ``Daily.WYR`` question bank."""

    def __init__(self):
        self._collection_key = "daily_wyr"
        self._counter_key = "daily_counters"

    @property
    def _col(self):
        return db_manager.get_collection_manager(self._collection_key)

    @property
    def _counters(self):
        return db_manager.get_collection_manager(self._counter_key)

    # ── Question numbers ─────────────────────────────────────────────────────

    async def _next_number(self, count: int = 1) -> int:
        """Reserve ``count`` consecutive question NUMBERS, returning the first.

        Allocates ``id``, not ``_id``. ``_id`` is an ObjectId that Mongo assigns
        and that the mapping and vote collections key off; the question number
        is the separate int humans see. One atomic ``$inc`` hands out a block,
        which is what makes a 500-question import one round trip rather than 500.
        """
        doc = await self._counters.collection.find_one_and_update(
            {"_id": _COUNTER_ID},
            {"$inc": {"seq": count}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        last = int(doc["seq"])
        return last - count + 1

    async def _resync_counter(self) -> int:
        """Raise the counter to the highest question number actually in the bank.

        The bank was populated out of band for its whole life before this module
        existed, so a number arriving from outside the counter is a real case,
        not a theoretical one. ``$max`` never lowers the counter, so this is safe
        to call from anywhere at any time.
        """
        rows = await self._col.find_many(
            {"id": {"$type": "int"}}, projection={"id": 1},
            sort=[("id", -1)], limit=1,
        )
        top = int(rows[0]["id"]) if rows else 0
        await self._counters.collection.update_one(
            {"_id": _COUNTER_ID}, {"$max": {"seq": top}}, upsert=True
        )
        logger.info(f"Resynced the question-number counter to {top}")
        return top

    # ── Reads ────────────────────────────────────────────────────────────────

    @staticmethod
    def _visible_filter(guild_id: Optional[int]) -> Dict[str, Any]:
        """Match the questions a guild may see: the global bank plus its own."""
        if guild_id is None:
            return {"scope": "global"}
        return {"$or": [{"scope": "global"},
                        {"scope": "guild", "guild_id": str(guild_id)}]}

    @staticmethod
    def _owned_filter(guild_id: Optional[int]) -> Dict[str, Any]:
        """Match only the questions a guild owns, and may therefore delete."""
        if guild_id is None:
            return {"scope": "global"}
        return {"scope": "guild", "guild_id": str(guild_id)}

    async def get_question(self, number: int) -> Optional[Dict[str, Any]]:
        """Look a question up by its question NUMBER (``id``), not its ObjectId."""
        try:
            return await self._col.find_one({"id": int(number)})
        except (TypeError, ValueError):
            logger.error(f"Not a question number: {number!r}")
            return None
        except Exception as e:
            logger.error(f"Failed to read question {number}: {e}", exc_info=True)
            return None

    async def find_duplicate(self, text_key: str,
                             guild_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Return an existing question with the same key, if this guild would see it.

        Scoped on purpose: two servers are allowed to hold the same question
        privately, but a guild may not add one that is already in the shared
        bank, because it would then be in that guild's rotation twice.
        """
        try:
            query = dict(self._visible_filter(guild_id))
            query["text_key"] = text_key
            return await self._col.find_one(query)
        except Exception as e:
            logger.error(f"Duplicate check failed for guild {guild_id}: {e}", exc_info=True)
            return None

    async def list_questions(self, guild_id: Optional[int], *,
                             owned_only: bool = True,
                             question_format: Optional[str] = None,
                             skip: int = 0,
                             limit: int = 25) -> List[Dict[str, Any]]:
        """Page through a bank, newest question number first."""
        try:
            query = dict(self._owned_filter(guild_id) if owned_only
                         else self._visible_filter(guild_id))
            if question_format:
                query["format"] = question_format
            return await self._col.find_many(query, sort=[("id", -1)],
                                             skip=skip, limit=limit)
        except Exception as e:
            logger.error(f"Failed to list questions for guild {guild_id}: {e}", exc_info=True)
            return []

    async def count_questions(self, guild_id: Optional[int], *,
                              owned_only: bool = True,
                              question_format: Optional[str] = None) -> int:
        try:
            query = dict(self._owned_filter(guild_id) if owned_only
                         else self._visible_filter(guild_id))
            if question_format:
                query["format"] = question_format
            return await self._col.count_documents(query)
        except Exception as e:
            logger.error(f"Failed to count questions for guild {guild_id}: {e}", exc_info=True)
            return 0

    async def count_by_format(self, guild_id: Optional[int], *,
                              owned_only: bool = True) -> Dict[str, int]:
        """Count a bank grouped by format.

        Feeds the warning that tells an admin their bank holds questions in a
        format the server is not currently posting - the trap this whole feature
        exists to avoid.
        """
        try:
            match = dict(self._owned_filter(guild_id) if owned_only
                         else self._visible_filter(guild_id))
            rows = await self._col.aggregate([
                {"$match": match},
                {"$group": {"_id": "$format", "count": {"$sum": 1}}},
            ])
            counts = {fmt: 0 for fmt in FORMATS}
            for row in rows:
                # A question predating the format field is a Would You Rather.
                fmt = row.get("_id") or FORMAT_WYR
                if fmt in counts:
                    counts[fmt] += int(row.get("count", 0))
            return counts
        except Exception as e:
            logger.error(f"Failed to count formats for guild {guild_id}: {e}", exc_info=True)
            return {fmt: 0 for fmt in FORMATS}

    # ── Writes ───────────────────────────────────────────────────────────────

    def _build_document(self, cleaned: Dict[str, Any], *,
                        guild_id: Optional[int],
                        source: str,
                        nsfw: bool,
                        submitted_by: Optional[int],
                        approved_by: Optional[int]) -> Dict[str, Any]:
        """Assemble a bank document from validated fields.

        Allocates neither identifier: ``_id`` is left for Mongo to assign, and
        the question number is set by the caller from the counter.
        """
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "original": cleaned["original"],
            "format": cleaned["format"],
            "nsfw": bool(nsfw),
            "tags": list(cleaned.get("tags") or []),
            "text_key": normalize_text_key(
                cleaned["format"],
                cleaned["original"],
                [v for _, v in question_options(cleaned)],
            ),
            # NOT "source" - that field already holds where a scraped question
            # came from across the whole seeded bank.
            "added_via": source,
            "created_at": now,
        }
        for n in range(1, MAX_OPTIONS + 1):
            key = f"option_{n}"
            if key in cleaned:
                doc[key] = cleaned[key]

        if guild_id is None:
            doc["scope"] = "global"
        else:
            doc["scope"] = "guild"
            doc["guild_id"] = str(guild_id)

        if submitted_by is not None:
            doc["submitted_by"] = str(submitted_by)
        if approved_by is not None:
            doc["approved_by"] = str(approved_by)
            doc["approved_at"] = now
        return doc

    async def insert_question(self, cleaned: Dict[str, Any], *,
                              guild_id: Optional[int] = None,
                              source: str = "admin",
                              nsfw: bool = False,
                              submitted_by: Optional[int] = None,
                              approved_by: Optional[int] = None
                              ) -> Optional[Dict[str, Any]]:
        """Insert one validated question. Returns the stored document, or None.

        ``cleaned`` is the second element of :func:`validate_question`; passing
        raw user input here is a bug.

        A ``DuplicateKeyError`` means a question number was taken by something
        other than the counter, so the counter is resynced and the insert
        retried rather than failing back to the admin.
        """
        doc = self._build_document(cleaned, guild_id=guild_id, source=source, nsfw=nsfw,
                                   submitted_by=submitted_by, approved_by=approved_by)
        for attempt in range(_MAX_ID_ATTEMPTS):
            try:
                doc["id"] = await self._next_number()
                await self._col.create_one(doc)
                logger.info(
                    f"Added question {doc['id']} ({doc['format']}, scope={doc['scope']}, "
                    f"added_via={source}) for guild {guild_id}"
                )
                return doc
            except DuplicateKeyError:
                logger.warning(
                    f"Question number {doc.get('id')} was already taken - resyncing the "
                    f"counter (attempt {attempt + 1}/{_MAX_ID_ATTEMPTS})"
                )
                await self._resync_counter()
            except Exception as e:
                logger.error(f"Failed to add a question for guild {guild_id}: {e}", exc_info=True)
                return None

        logger.error(
            f"Gave up allocating a question number after {_MAX_ID_ATTEMPTS} attempts "
            f"(guild {guild_id})"
        )
        return None

    async def insert_many_questions(self, cleaned_items: List[Dict[str, Any]], *,
                                    guild_id: Optional[int] = None,
                                    source: str = "import",
                                    nsfw_flags: Optional[List[bool]] = None
                                    ) -> Dict[str, Any]:
        """Bulk-insert validated questions, skipping ones already in the bank.

        Returns ``{"added": int, "duplicates": int, "failed": int,
        "formats": {fmt: count}}``. Best-effort: a batch that partially fails
        still reports what actually landed, because telling an admin "0 added"
        when 140 went in would be worse than the failure itself.
        """
        summary = {"added": 0, "duplicates": 0, "failed": 0,
                   "formats": {fmt: 0 for fmt in FORMATS}}
        if not cleaned_items:
            return summary

        flags = list(nsfw_flags or [])
        docs: List[Dict[str, Any]] = []
        seen_keys: set = set()

        for index, cleaned in enumerate(cleaned_items):
            nsfw = bool(flags[index]) if index < len(flags) else False
            doc = self._build_document(cleaned, guild_id=guild_id, source=source, nsfw=nsfw,
                                       submitted_by=None, approved_by=None)
            # Duplicates within the uploaded file itself, before touching Mongo.
            if doc["text_key"] in seen_keys:
                summary["duplicates"] += 1
                continue
            if await self.find_duplicate(doc["text_key"], guild_id):
                summary["duplicates"] += 1
                continue
            seen_keys.add(doc["text_key"])
            docs.append(doc)

        if not docs:
            return summary

        try:
            first_number = await self._next_number(len(docs))
            for offset, doc in enumerate(docs):
                doc["id"] = first_number + offset
            await self._col.create_many(docs, ordered=False)
            summary["added"] = len(docs)
        except BulkWriteError as e:
            # ordered=False, so the good documents landed and only the clashing
            # ones did not. Count what survived instead of reporting total loss.
            written = int((e.details or {}).get("nInserted", 0))
            summary["added"] = written
            summary["failed"] = len(docs) - written
            logger.error(f"Bulk question import partially failed for guild {guild_id}: {e}")
            await self._resync_counter()
        except Exception as e:
            summary["failed"] = len(docs)
            logger.error(f"Bulk question import failed for guild {guild_id}: {e}", exc_info=True)
            return summary

        for doc in docs[:summary["added"]]:
            summary["formats"][doc["format"]] += 1
        logger.info(
            f"Imported {summary['added']} questions for guild {guild_id} "
            f"({summary['duplicates']} duplicates, {summary['failed']} failed)"
        )
        return summary

    async def delete_question(self, number: int,
                              guild_id: Optional[int]) -> bool:
        """Delete a question the caller owns, by its question number.

        Scoped to the owner's questions, so a guild admin cannot reach into the
        shared bank or another server's questions through the panel.
        """
        try:
            query = dict(self._owned_filter(guild_id))
            query["id"] = int(number)
        except (TypeError, ValueError):
            logger.error(f"Refusing to delete a non-numeric question number: {number!r}")
            return False
        try:
            deleted = await self._col.delete_one(query)
            logger.info(f"Deleted question {number} for guild {guild_id}: {deleted}")
            return bool(deleted)
        except Exception as e:
            logger.error(f"Failed to delete question {number}: {e}", exc_info=True)
            return False

    async def promote_to_global(self, number: int, actor_id: int) -> bool:
        """Move a guild's private question into the shared bank. Owner only.

        ``guild_id`` is unset rather than kept, so it means exactly one thing -
        "the guild that privately owns this" - and the partial index over
        guild-scoped questions stays correct. The origin is preserved separately.

        ``guilds.<gid>.used_count`` is deliberately NOT reset: the origin guild
        has already seen this question, and least-used-first correctly puts it
        behind everything that server has not seen yet.
        """
        try:
            question = await self.get_question(number)
            if not question:
                logger.warning(f"Cannot promote question {number}: it does not exist")
                return False
            if question.get("scope") == "global":
                logger.info(f"Question {number} is already global")
                return False

            update: Dict[str, Any] = {
                "$set": {
                    "scope": "global",
                    "promoted_by": str(actor_id),
                    "promoted_at": datetime.now(timezone.utc),
                },
                "$unset": {"guild_id": ""},
            }
            if question.get("guild_id"):
                update["$set"]["origin_guild_id"] = str(question["guild_id"])

            # Keyed by the ObjectId we just read, so the write lands on exactly
            # the document that was checked.
            updated = await self._col.update_one({"_id": question["_id"]}, update)
            logger.info(f"Promoted question {number} to the global bank: {updated}")
            return bool(updated)
        except Exception as e:
            logger.error(f"Failed to promote question {number}: {e}", exc_info=True)
            return False


# Global instance - imported directly, like board_store. Feature stores are not
# attached to the bot.
wyr_bank = WYRBank()
