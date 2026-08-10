"""
Member question submissions awaiting a moderator decision.

A submission is not a question. It lives in its own collection with its own
lifecycle, and approving one COPIES it into the guild's bank
(``Features.daily.wyr_bank``) while the submission document stays as the record
of who sent it and who decided.

Status moves in one direction only::

    pending ──> reviewing ──> approved
        │           │
        │           └──────> rejected
        └──────────────────> rejected

``reviewing`` is a claim, not a screen. A moderator's click takes it atomically,
so a double-click, or two moderators acting at the same moment, cannot both
insert the same question into the bank. Every transition is written as a
conditional update on the status the caller expected to find; if nothing
matched, somebody else got there first and the caller is told so.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from storage.log import get_logger
from storage.settings.collections import db_manager

from Features.daily.wyr_bank import MAX_OPTIONS, normalize_text_key, question_options

logger = get_logger("WYRSubmissions")

STATUS_PENDING = "pending"
STATUS_REVIEWING = "reviewing"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

#: A claim older than this is treated as abandoned - the moderator's client died
#: between claiming and deciding. The queue shows it again with a warning rather
#: than stranding the submission forever.
STALE_CLAIM = timedelta(minutes=10)

#: Statuses still awaiting a decision.
OPEN_STATUSES = (STATUS_PENDING, STATUS_REVIEWING)


class WYRSubmissionStore:
    """Reads and writes for ``Daily.WYR_Submissions``."""

    def __init__(self):
        self._collection_key = "daily_wyr_submissions"

    @property
    def _col(self):
        return db_manager.get_collection_manager(self._collection_key)

    # ── Reads ────────────────────────────────────────────────────────────

    async def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._col.find_one({"submission_id": str(submission_id)})
        except Exception as e:
            logger.error(f"Failed to read submission {submission_id}: {e}", exc_info=True)
            return None

    async def find_by_review_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Recover the submission behind a review post.

        A review view rebuilt after a restart carries no submission id, so every
        button click on an older post resolves through this lookup. That is why
        ``review_message_id`` is indexed.
        """
        try:
            return await self._col.find_one({"review_message_id": str(message_id)})
        except Exception as e:
            logger.error(
                f"Failed to resolve a submission from message {message_id}: {e}",
                exc_info=True,
            )
            return None

    async def list_open(self, guild_id: int, *, limit: int = 100) -> List[Dict[str, Any]]:
        """Submissions still awaiting a decision, oldest first."""
        try:
            return await self._col.find_many(
                {"guild_id": str(guild_id), "status": {"$in": list(OPEN_STATUSES)}},
                sort=[("created_at", 1)],
                limit=limit,
            )
        except Exception as e:
            logger.error(
                f"Failed to list open submissions for guild {guild_id}: {e}", exc_info=True
            )
            return []

    async def count_open(self, guild_id: int) -> int:
        try:
            return await self._col.count_documents(
                {"guild_id": str(guild_id), "status": {"$in": list(OPEN_STATUSES)}}
            )
        except Exception as e:
            logger.error(
                f"Failed to count open submissions for guild {guild_id}: {e}", exc_info=True
            )
            return 0

    async def count_open_for_user(self, guild_id: int, user_id: int) -> int:
        """How many of this member's submissions are still waiting.

        Backs the per-member cap, which is the only thing standing between the
        queue and one enthusiastic member filling it.
        """
        try:
            return await self._col.count_documents({
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "status": {"$in": list(OPEN_STATUSES)},
            })
        except Exception as e:
            logger.error(
                f"Failed to count pending submissions for user {user_id}: {e}", exc_info=True
            )
            # Fail closed: an unknown count must not read as "room for more".
            return 10 ** 6

    async def find_duplicate(self, guild_id: int, text_key: str) -> Optional[Dict[str, Any]]:
        """An open or already-approved submission of the same question."""
        try:
            return await self._col.find_one({
                "guild_id": str(guild_id),
                "text_key": text_key,
                "status": {"$in": list(OPEN_STATUSES) + [STATUS_APPROVED]},
            })
        except Exception as e:
            logger.error(f"Duplicate submission check failed: {e}", exc_info=True)
            return None

    @staticmethod
    def is_claim_stale(submission: Dict[str, Any]) -> bool:
        """Whether a ``reviewing`` claim has been abandoned."""
        if submission.get("status") != STATUS_REVIEWING:
            return False
        claimed = submission.get("reviewed_at")
        if not claimed:
            return True
        if claimed.tzinfo is None:
            claimed = claimed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - claimed > STALE_CLAIM

    # ── Writes ───────────────────────────────────────────────────────────

    async def create_submission(self, *, guild_id: int, user_id: int,
                                cleaned: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Store a new submission. ``cleaned`` comes from ``validate_question``.

        A submission is always stored ``nsfw: False``. Members cannot mark their
        own question age-restricted - only the reviewer can, at approve time,
        because the review post itself renders in a channel that may not be
        age-restricted.
        """
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "submission_id": str(uuid.uuid4()),
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "format": cleaned["format"],
            "original": cleaned["original"],
            "tags": list(cleaned.get("tags") or []),
            "text_key": normalize_text_key(
                cleaned["format"], cleaned["original"],
                [v for _, v in question_options(cleaned)],
            ),
            "status": STATUS_PENDING,
            "review_channel_id": None,
            "review_message_id": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "review_reason": None,
            "question_id": None,
            "created_at": now,
        }
        for n in range(1, MAX_OPTIONS + 1):
            key = f"option_{n}"
            if key in cleaned:
                doc[key] = cleaned[key]

        try:
            await self._col.create_one(doc)
            logger.info(
                f"Member {user_id} submitted a {doc['format']} question in guild "
                f"{guild_id} ({doc['submission_id'][:8]})"
            )
            return doc
        except Exception as e:
            logger.error(f"Failed to store a submission for guild {guild_id}: {e}",
                         exc_info=True)
            return None

    async def set_review_message(self, submission_id: str, channel_id: int,
                                 message_id: int) -> bool:
        try:
            return await self._col.update_one(
                {"submission_id": str(submission_id)},
                {"$set": {
                    "review_channel_id": str(channel_id),
                    "review_message_id": str(message_id),
                }},
            )
        except Exception as e:
            logger.error(f"Failed to record the review message for {submission_id}: {e}",
                         exc_info=True)
            return False

    async def delete_submission(self, submission_id: str) -> bool:
        """Remove a submission outright.

        Used when the review post could not be delivered: leaving the row would
        put a question in a queue nobody can see, and "my question vanished" is
        a better failure than "my question is in limbo".
        """
        try:
            return await self._col.delete_one({"submission_id": str(submission_id)})
        except Exception as e:
            logger.error(f"Failed to delete submission {submission_id}: {e}", exc_info=True)
            return False

    async def claim_for_review(self, submission_id: str, reviewer_id: int) -> bool:
        """Atomically take a pending submission for a decision.

        Returns False when nothing matched, which means another moderator (or
        this one's second click) already has it. The conditional filter on
        ``status: pending`` is the whole safety mechanism - without it a
        double-click inserts the same question into the bank twice.
        """
        try:
            return await self._col.update_one(
                {"submission_id": str(submission_id), "status": STATUS_PENDING},
                {"$set": {
                    "status": STATUS_REVIEWING,
                    "reviewed_by": str(reviewer_id),
                    "reviewed_at": datetime.now(timezone.utc),
                }},
            )
        except Exception as e:
            logger.error(f"Failed to claim submission {submission_id}: {e}", exc_info=True)
            return False

    async def release_claim(self, submission_id: str) -> bool:
        """Put a claimed submission back in the queue.

        Called whenever a decision could not be completed, so a failed approve
        never strands a member's question in ``reviewing`` forever.
        """
        try:
            return await self._col.update_one(
                {"submission_id": str(submission_id), "status": STATUS_REVIEWING},
                {"$set": {"status": STATUS_PENDING, "reviewed_by": None,
                          "reviewed_at": None}},
            )
        except Exception as e:
            logger.error(f"Failed to release submission {submission_id}: {e}", exc_info=True)
            return False

    async def mark_approved(self, submission_id: str, question_id: int,
                            reviewer_id: int) -> bool:
        try:
            return await self._col.update_one(
                {"submission_id": str(submission_id)},
                {"$set": {
                    "status": STATUS_APPROVED,
                    "question_id": int(question_id),
                    "reviewed_by": str(reviewer_id),
                    "reviewed_at": datetime.now(timezone.utc),
                }},
            )
        except Exception as e:
            logger.error(f"Failed to approve submission {submission_id}: {e}", exc_info=True)
            return False

    async def mark_rejected(self, submission_id: str, reviewer_id: int,
                            reason: str = "") -> bool:
        try:
            return await self._col.update_one(
                {"submission_id": str(submission_id)},
                {"$set": {
                    "status": STATUS_REJECTED,
                    "review_reason": (reason or "").strip() or None,
                    "reviewed_by": str(reviewer_id),
                    "reviewed_at": datetime.now(timezone.utc),
                }},
            )
        except Exception as e:
            logger.error(f"Failed to reject submission {submission_id}: {e}", exc_info=True)
            return False


# Global instance - imported directly, like the other feature stores.
wyr_submissions = WYRSubmissionStore()
