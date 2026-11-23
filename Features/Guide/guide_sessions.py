"""
Guide Sessions - one record per open guide message.

Every guide the bot posts (a mention reply in a channel, or the private guide the
greeting's "Open Guide" button sends) is one message that each click edits in
place. This store remembers, per message:

- who the guide is for (``owner_id``), so only that member can drive it and the
  page's placeholders always name them;
- the member's Back history for THAT message (``path``), so two guides open at
  once do not share one history;
- when it closes (``expires_at``, integer Unix seconds). Every click by the owner
  pushes it ``SESSION_TTL_SECONDS`` past the click; the sweep in ``GuideCog``
  closes guides whose time has run out.

Records live in Mongo so a restart neither forgets who owns an open guide nor
leaves one open forever: the first sweep after startup closes everything that
expired while the bot was down.

Private (ephemeral) guides can only be edited through an interaction token, which
Discord keeps valid for 15 minutes and which cannot sensibly be stored. The newest
usable interaction per private guide is held in memory (``remember_interaction``);
after a restart there is none, so the sweep just drops the record and the next
click on that guide gets the closed notice.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import discord

from storage.settings.collections import db_manager
from storage.log import get_logger

logger = get_logger("GuideSessions")

#: A guide closes this long after its owner last used it.
SESSION_TTL_SECONDS = 600

#: How often the sweep looks for guides to close.
SWEEP_INTERVAL_SECONDS = 30

#: Back history kept per guide. Older steps fall off; Back past them lands on Home.
MAX_PATH_LENGTH = 50

#: How many expired guides one sweep closes; the rest wait for the next sweep.
_SWEEP_BATCH = 50

#: Discord keeps an interaction token usable for 15 minutes. A stored one older
#: than this is not tried, it would only fail (10 s margin for clock and latency).
_TOKEN_HARD_LIMIT_SECONDS = 15 * 60 - 10

#: A private guide's timer is never renewed past this age of its newest token,
#: leaving the sweep (every SWEEP_INTERVAL_SECONDS) time to close it before the
#: hard limit.
_TOKEN_LIFETIME_SECONDS = 14 * 60


def now_ts() -> int:
	return int(time.time())


class GuideSessionStore:
	"""CRUD for the guide_sessions collection, plus the in-memory private-guide tokens."""

	def __init__(self):
		self._collection_key = "guide_sessions"
		# message_id (str) -> (interaction, unix seconds it was received)
		self._tokens: Dict[str, tuple] = {}

	@property
	def _col(self):
		return db_manager.get_collection_manager(self._collection_key)

	async def open(
		self, *, message_id: int, guild_id: int, channel_id: int, owner_id: int,
		path: List[str], ephemeral: bool,
	) -> None:
		"""Record a guide message that was just posted."""
		now = now_ts()
		await self._col.update_one(
			{"message_id": str(message_id)},
			{"$set": {
				"message_id": str(message_id),
				"guild_id": str(guild_id),
				"channel_id": str(channel_id),
				"owner_id": str(owner_id),
				"path": list(path)[-MAX_PATH_LENGTH:],
				"ephemeral": bool(ephemeral),
				"opened_at": now,
				"expires_at": now + SESSION_TTL_SECONDS,
			}},
			upsert=True,
		)

	async def get(self, message_id: int) -> Optional[Dict[str, Any]]:
		return await self._col.find_one({"message_id": str(message_id)})

	async def touch(self, message_id: int, until: Optional[int] = None) -> bool:
		"""Push a live guide's closing time out again. False if it already expired
		(or the sweep closed it a moment ago), so the caller shows the closed notice.

		``until`` caps the new closing time (a private guide whose newest usable
		token runs out sooner must close while it can still be edited).
		"""
		now = now_ts()
		expires_at = now + SESSION_TTL_SECONDS
		if until is not None:
			expires_at = min(expires_at, until)
		return await self._col.update_one(
			{"message_id": str(message_id), "expires_at": {"$gt": now}},
			{"$set": {"expires_at": expires_at}},
		)

	async def save_path(self, message_id: int, path: List[str]) -> None:
		await self._col.update_one(
			{"message_id": str(message_id)},
			{"$set": {"path": list(path)[-MAX_PATH_LENGTH:]}},
		)

	async def close(self, message_id: int) -> None:
		"""Forget a guide (it is being closed by a click right now)."""
		self._tokens.pop(str(message_id), None)
		await self._col.delete_one({"message_id": str(message_id)})

	async def claim_expired(self) -> List[Dict[str, Any]]:
		"""Return the expired guides this caller now owns the closing of.

		Each record is deleted with its expiry still in the filter, so a click
		that renewed the guide in between wins, and two sweeps can never both
		close the same guide.
		"""
		now = now_ts()
		expired = await self._col.find_many(
			{"expires_at": {"$lte": now}}, limit=_SWEEP_BATCH,
		)
		claimed = []
		for doc in expired:
			if await self._col.delete_one(
				{"message_id": doc["message_id"], "expires_at": {"$lte": now}}
			):
				claimed.append(doc)
		return claimed

	# ── Private guides: the token that can still edit them ───────────────────

	def remember_interaction(self, message_id: int, interaction: discord.Interaction) -> None:
		"""Keep the newest interaction whose original response IS the guide message."""
		now = now_ts()
		# Drop tokens nothing can use any more (their guide was closed by a
		# click, wiped with a departed server, or outlived the token), so the
		# map stays as small as the number of private guides open right now.
		for key, (_, received) in list(self._tokens.items()):
			if now - received > _TOKEN_HARD_LIMIT_SECONDS:
				del self._tokens[key]
		self._tokens[str(message_id)] = (interaction, now)

	def token_deadline(self, message_id: int | str) -> Optional[int]:
		"""When the newest usable token for a private guide stops working, or
		None if there is none (after a restart: the guide closes on its next
		click instead, whatever its timer says)."""
		entry = self._tokens.get(str(message_id))
		if entry is None:
			return None
		return entry[1] + _TOKEN_LIFETIME_SECONDS

	def take_interaction(self, message_id: int | str) -> Optional[discord.Interaction]:
		"""Hand over (and forget) a still-usable interaction for a private guide."""
		entry = self._tokens.pop(str(message_id), None)
		if entry is None:
			return None
		interaction, received = entry
		if now_ts() - received > _TOKEN_HARD_LIMIT_SECONDS:
			return None
		return interaction


def has_interactive_items(layout: Any) -> bool:
	"""Whether a rendered guide view carries anything a member can click.

	A view with nothing to click (the empty-guide notice) needs no session:
	there is nothing to expire and nobody to lock out.
	"""
	if not isinstance(layout, discord.ui.LayoutView):
		return False
	return any(
		isinstance(item, (discord.ui.Button, discord.ui.Select))
		and getattr(item, "style", None) != discord.ButtonStyle.link
		for item in layout.walk_children()
	)


# ── Back history on a plain list (one per guide message) ─────────────────────
# Same rules the old per-member breadcrumbs used: no repeat of the page you are
# already on, Back steps to the previous entry, Home starts over.

def push_page(path: List[str], page_id: str) -> None:
	if not path or path[-1] != page_id:
		path.append(page_id)
	if len(path) > MAX_PATH_LENGTH:
		del path[:-MAX_PATH_LENGTH]


def pop_page(path: List[str]) -> Optional[str]:
	if len(path) > 1:
		path.pop()
		return path[-1]
	return None


def reset_path(path: List[str]) -> None:
	path.clear()


guide_sessions = GuideSessionStore()
