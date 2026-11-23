"""
Guide System V2

Components V2 guide with page-tree navigation, search, and interaction dispatch.
Guide content is stored as a JSON page tree in the guide_content collection.
"""

import asyncio
import re
import weakref
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from rapidfuzz import fuzz

from startup.bot import bot
from storage.log import get_logger, PerformanceLogger
from storage.settings.collections import db_manager
from Features.Guide.guide_store import guide_store
from Features.Guide.guide_renderer import GuideRenderer
from Features.Guide.guide_sessions import (
	guide_sessions,
	has_interactive_items,
	now_ts,
	push_page,
	pop_page,
	reset_path,
	SWEEP_INTERVAL_SECONDS,
)
from Features.Guide.guide_actions import (
	decode_custom_id,
	decode_select_value,
	CUSTOM_ID_SEARCH,
)
from admin.setup_notice import setup_notice_text
from Features.interaction_errors import SupportAwareModalMixin, send_unexpected_failure
from commands.help.help_content import SUPPORT_LINE
from Features.role_safety import blocked_role_reason, is_blocked
from utils.component_builders import strip_duplicate_suffix

logger = get_logger("Guide")


# ─────────────────────────────────────────────────────────────────────────────
# Search Engine - indexes V2 page trees
# ─────────────────────────────────────────────────────────────────────────────

class SearchEngine:
	"""Indexes guide page trees and performs fuzzy search."""

	def __init__(self):
		self.content_index: Dict[int, Dict[str, dict]] = {}  # guild_id -> {page_id: indexed_data}

	def index_guide(self, guide_data: Dict[str, Any], guild_id: int):
		"""Index all pages in a guide for searching."""
		guild_index: Dict[str, dict] = {}

		pages = guide_data.get("pages", [])
		self._index_pages(pages, guild_index, path=[])

		self.content_index[guild_id] = guild_index
		logger.info(f"Indexed {len(guild_index)} pages for guild {guild_id}")

	def _index_pages(self, pages: list, index: dict, path: list):
		"""Recursively index pages."""
		for page in pages:
			if not isinstance(page, dict):
				continue

			page_id = page.get("id", "")
			label = page.get("label", "")
			description = page.get("description", "")

			# Extract text from content components
			content_text = ""
			content = page.get("content")
			if content and "components" in content:
				content_text = self._extract_text_from_components(content["components"])

			searchable = f"{label} {description} {content_text}".lower()
			keywords = self._extract_keywords(searchable)

			index[page_id] = {
				"label": label,
				"description": description,
				"searchable": searchable,
				"keywords": keywords,
				"path": list(path),
				"page": page,
			}

			# Index children
			children = page.get("children", [])
			if children:
				self._index_pages(children, index, path + [label])

	def _extract_text_from_components(self, components: list) -> str:
		"""Walk V2 component trees and extract all text content."""
		texts = []
		for comp in components:
			if not isinstance(comp, dict):
				continue
			comp_type = comp.get("type")
			if comp_type == "text":
				texts.append(comp.get("content", ""))
			elif comp_type == "section":
				for sub in comp.get("content", []):
					if isinstance(sub, dict) and sub.get("type") == "text":
						texts.append(sub.get("content", ""))
			elif comp_type == "container":
				texts.append(self._extract_text_from_components(comp.get("components", [])))
		return " ".join(texts)

	def _extract_keywords(self, text: str) -> set:
		"""Extract meaningful keywords from text."""
		words = re.findall(r'\b\w{3,}\b', text.lower())
		stop_words = {
			'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
			'how', 'has', 'had', 'with', 'this', 'that', 'will', 'from',
			'they', 'been', 'have', 'were', 'said', 'each', 'which',
		}
		return {w for w in words if w not in stop_words}

	def smart_search(self, query: str, guild_id: int, limit: int = 5) -> List[Tuple[str, int, str]]:
		"""Search indexed content. Returns [(page_id, score, label), ...]."""
		guild_index = self.content_index.get(guild_id, {})
		if not guild_index:
			return []

		# Cap query length so a pathological input can't drive unbounded scoring.
		query = (query or "")[:200]
		query_lower = query.lower()
		query_words = set(query_lower.split())
		query_keywords = self._extract_keywords(query_lower)
		results = []

		for page_id, data in guild_index.items():
			score = 0
			label_lower = data["label"].lower()

			# Exact label match
			if query_lower == label_lower:
				score += 200
			elif query_lower in label_lower:
				score += 150

			# Word matches in label
			label_words = set(label_lower.split())
			exact_word_matches = len(query_words & label_words)
			score += exact_word_matches * 40

			# Keyword matches in content
			keyword_matches = len(query_keywords & data["keywords"])
			score += keyword_matches * 20

			# Fuzzy match
			fuzzy = fuzz.partial_ratio(query_lower, data["searchable"])
			score += fuzzy // 3

			if score > 20:
				results.append((page_id, score, data["label"]))

		results.sort(key=lambda x: x[1], reverse=True)
		return results[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Guide Manager - core orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class GuideManager:
	"""Loads guide data, navigates pages, renders via GuideRenderer.

	Navigation methods take ``path``: the Back history of ONE guide message (a
	plain list of page ids, kept on that message's session record). They update
	it in place; the caller saves it.
	"""

	def __init__(self):
		self.search_engine = SearchEngine()
		self._guide_cache: Dict[int, Dict[str, Any]] = {}
		self._cache_time: Dict[int, datetime] = {}

	async def initialize_database(self):
		"""Initialize database connection."""
		try:
			await db_manager.initialize()
			logger.info("GuideManager: Database initialized")
			return True
		except Exception as e:
			logger.error(f"GuideManager: Failed to initialize database - {e}")
			return False

	async def _get_guide(self, guild_id: int) -> Dict[str, Any]:
		"""Get guide data with caching. Checks DB updated_at to detect external changes."""
		cache_ts = self._cache_time.get(guild_id)
		if cache_ts and self._guide_cache.get(guild_id) is not None:
			# Lightweight check: has the DB document been updated since we cached?
			doc = await guide_store._col.find_one(
				{"guild_id": str(guild_id)}, projection={"updated_at": 1}
			)
			db_updated = doc.get("updated_at") if doc else None
			if db_updated:
				# updated_at is a datetime stored in UTC
				if isinstance(db_updated, datetime):
					if db_updated.tzinfo is None:
						db_updated = db_updated.replace(tzinfo=timezone.utc)
					if db_updated <= cache_ts:
						return self._guide_cache[guild_id]
				# If we can't compare, fall through to refetch
			else:
				# No updated_at in DB - trust cache for 30 min
				if datetime.now(timezone.utc) - cache_ts < timedelta(minutes=30):
					return self._guide_cache[guild_id]

		data = await guide_store.get_or_create_guide(guild_id)
		self._guide_cache[guild_id] = data
		self._cache_time[guild_id] = datetime.now(timezone.utc)
		self.search_engine.index_guide(data, guild_id)
		return data

	def invalidate_cache(self, guild_id: int):
		"""Force re-load on next access."""
		self._guide_cache.pop(guild_id, None)
		self._cache_time.pop(guild_id, None)

	def _find_page(self, pages: list, page_id: str) -> Optional[Dict[str, Any]]:
		"""Find a page by ID in the tree (recursive)."""
		for page in pages:
			if page.get("id") == page_id:
				return page
			children = page.get("children", [])
			if children:
				result = self._find_page(children, page_id)
				if result:
					return result
		return None

	def _get_breadcrumb_labels(self, pages: list, page_id: str, trail: list = None) -> Optional[list]:
		"""Get the label trail to a page."""
		if trail is None:
			trail = []
		for page in pages:
			current_trail = trail + [page.get("label", "")]
			if page.get("id") == page_id:
				return current_trail
			children = page.get("children", [])
			if children:
				result = self._get_breadcrumb_labels(children, page_id, current_trail)
				if result:
					return result
		return None

	def _get_parent_id(self, pages: list, page_id: str, parent_id: str = None) -> Optional[str]:
		"""Find the parent page ID of a given page."""
		for page in pages:
			if page.get("id") == page_id:
				return parent_id
			children = page.get("children", [])
			if children:
				result = self._get_parent_id(children, page_id, page.get("id"))
				if result is not None:
					return result
		return None

	# ─────────────────────────────────────────────────────────────────────
	# Public rendering methods
	# ─────────────────────────────────────────────────────────────────────

	async def get_usage_view(
		self, guild_id: int, path: List[str],
		interaction: discord.Interaction = None,
		guild: discord.Guild = None,
		member: Union[discord.Member, discord.User] = None,
	) -> discord.ui.LayoutView:
		"""Render the "how to use the guide" instructions (shown on a bare mention)."""
		guide_data = await self._get_guide(guild_id)

		reset_path(path)

		return GuideRenderer.render_usage(
			guide_data,
			interaction=interaction, guild=guild, member=member,
		)

	def _home_page_id(self, pages: List[Dict]) -> Optional[str]:
		"""Return the Home page id - the top-level page with the lowest ``order``."""
		if not pages:
			return None
		return sorted(pages, key=lambda p: p.get("order", 999))[0].get("id")

	async def get_page_view(
		self, guild_id: int, path: List[str], page_id: str,
		interaction: discord.Interaction = None,
		guild: discord.Guild = None,
		member: Union[discord.Member, discord.User] = None,
	) -> discord.ui.LayoutView:
		"""Render a specific guide page."""
		guide_data = await self._get_guide(guild_id)
		pages = guide_data.get("pages", [])

		page = self._find_page(pages, page_id)
		if not page:
			return self._render_not_found(guide_data, page_id)

		# Track
		push_page(path, page_id)

		# Breadcrumb labels
		labels = self._get_breadcrumb_labels(pages, page_id)
		breadcrumb_path = ["Guide"] + (labels or [page.get("label", "")])

		# The Home page (top of the tree) is the root - no Back/Home buttons.
		is_root = page_id == self._home_page_id(pages)

		return GuideRenderer.render_page(
			page, guide_data, breadcrumb_path, is_root=is_root,
			interaction=interaction, guild=guild, member=member,
		)

	async def get_home_view(
		self, guild_id: int, path: List[str],
		interaction: discord.Interaction = None,
		guild: discord.Guild = None,
		member: Union[discord.Member, discord.User] = None,
	) -> discord.ui.LayoutView:
		"""Render the guide's Home page - the page at the top of the tree.

		The top-level page with the lowest ``order`` is the Home page. It is the
		entry point that ``help`` mentions, the Home button, and unmatched
		searches all land on. Navigation state is reset so Home is the root of
		the breadcrumb.
		"""
		guide_data = await self._get_guide(guild_id)
		pages = guide_data.get("pages", [])
		if not pages:
			# No pages authored yet - show a friendly empty state, plus directions
			# so whoever triggered it knows the guide is unwritten, not broken.
			hint = await setup_notice_text(
				guild,
				what="a server guide",
				path="Guide -> Guide JSON Builder",
				viewer=member if isinstance(member, discord.Member) else None,
			)
			return GuideRenderer.render_empty(
				guide_data,
				interaction=interaction, guild=guild, member=member,
				setup_hint=hint,
			)

		reset_path(path)
		home_id = self._home_page_id(pages)
		return await self.get_page_view(
			guild_id, path, home_id,
			interaction=interaction, guild=guild, member=member,
		)

	async def handle_back(
		self, guild_id: int, path: List[str],
		interaction: discord.Interaction = None,
	) -> discord.ui.LayoutView:
		"""Navigate back one level."""
		guide_data = await self._get_guide(guild_id)
		pages = guide_data.get("pages", [])

		# Get current path
		if len(path) <= 1:
			return await self.get_home_view(guild_id, path, interaction=interaction)

		# Pop current, navigate to parent
		pop_page(path)

		if not path:
			return await self.get_home_view(guild_id, path, interaction=interaction)

		parent_id = path[-1]
		page = self._find_page(pages, parent_id)
		if not page:
			return await self.get_home_view(guild_id, path, interaction=interaction)

		labels = self._get_breadcrumb_labels(pages, parent_id)
		breadcrumb_path = ["Guide"] + (labels or [page.get("label", "")])

		is_root = parent_id == self._home_page_id(pages)
		return GuideRenderer.render_page(
			page, guide_data, breadcrumb_path, is_root=is_root, interaction=interaction
		)

	async def handle_search(self, query: str, guild_id: int, user_id: int) -> discord.ui.LayoutView:
		"""Search the guide and render results."""
		guide_data = await self._get_guide(guild_id)
		results = self.search_engine.smart_search(query, guild_id, limit=10)

		from utils.component_builders import resolve_color
		accent_color = resolve_color(guide_data.get("accent_color", "#4D0EB3"))

		layout = discord.ui.LayoutView(timeout=600.0)

		if results:
			# Build results container
			children = [
				discord.ui.TextDisplay(f"## 🔍 Search Results for \"{query}\""),
				discord.ui.TextDisplay(f"Found {len(results)} matches:"),
				discord.ui.Separator(),
			]

			for i, (page_id, score, label) in enumerate(results[:5], 1):
				page = self._find_page(guide_data.get("pages", []), page_id)
				desc = ""
				if page:
					desc = page.get("description", "")
				children.append(discord.ui.TextDisplay(f"**{i}.** {label}" + (f"\n-# {desc}" if desc else "")))

			container = discord.ui.Container(*children)
			container.accent_colour = accent_color
			layout.add_item(container)

			# Results select dropdown
			options = [
				discord.SelectOption(
					label=label[:100],
					value=page_id,
					description=(self._find_page(guide_data.get("pages", []), page_id) or {}).get("description", "")[:100] or None,
				)
				for page_id, score, label in results[:10]
			]
			select = discord.ui.Select(
				custom_id="g:_select",
				placeholder="Select a result...",
				options=options,
			)
			row = discord.ui.ActionRow()
			row.add_item(select)
			layout.add_item(row)
		else:
			container = discord.ui.Container(
				discord.ui.TextDisplay(f"## 🔍 No Results"),
				discord.ui.TextDisplay(f"No matches found for \"{query}\". Try different keywords."),
			)
			container.accent_colour = accent_color
			layout.add_item(container)

		# Nav chrome
		from Features.Guide.guide_actions import CUSTOM_ID_HOME, CUSTOM_ID_SEARCH
		nav_row = discord.ui.ActionRow()
		nav_row.add_item(discord.ui.Button(
			label="Home", style=discord.ButtonStyle.secondary,
			custom_id=CUSTOM_ID_HOME, emoji="🏠",
		))
		nav_row.add_item(discord.ui.Button(
			label="Search Again", style=discord.ButtonStyle.primary,
			custom_id=CUSTOM_ID_SEARCH, emoji="🔍",
		))
		layout.add_item(nav_row)

		return layout

	def _render_not_found(self, guide_data: dict, page_id: str) -> discord.ui.LayoutView:
		from utils.component_builders import resolve_color
		from Features.Guide.guide_actions import CUSTOM_ID_HOME
		accent_color = resolve_color(guide_data.get("accent_color", "#4D0EB3"))

		layout = discord.ui.LayoutView(timeout=600.0)
		container = discord.ui.Container(
			discord.ui.TextDisplay("## Page Not Found"),
			discord.ui.TextDisplay(f"The page \"{page_id}\" could not be found."),
		)
		container.accent_colour = accent_color
		layout.add_item(container)

		nav_row = discord.ui.ActionRow()
		nav_row.add_item(discord.ui.Button(
			label="Home", style=discord.ButtonStyle.secondary,
			custom_id=CUSTOM_ID_HOME, emoji="🏠",
		))
		layout.add_item(nav_row)
		return layout

	# Legacy compatibility - used by guide_mention and greeting_actions
	async def search_content(self, query: str, guild_id: int, user_id: int = None) -> List[Dict]:
		"""Search for content. Returns list of result dicts."""
		await self._get_guide(guild_id)  # Ensure indexed
		results = self.search_engine.smart_search(query, guild_id)
		guide_data = self._guide_cache.get(guild_id, {})
		pages = guide_data.get("pages", [])

		search_results = []
		for page_id, score, label in results:
			page = self._find_page(pages, page_id)
			if page:
				search_results.append({
					"page_id": page_id,
					"name": label,
					"score": score,
					"description": page.get("description", ""),
				})
		return search_results


# Global instances
guide_manager = GuideManager()


# ─────────────────────────────────────────────────────────────────────────────
# Search Modal
# ─────────────────────────────────────────────────────────────────────────────

class GuideSearchModal(SupportAwareModalMixin, discord.ui.Modal):
	"""Modal for searching guide content."""

	def __init__(self, guild_id: int, session: Dict[str, Any]):
		super().__init__(title="🔍 Search Guide")
		self.guild_id = guild_id
		# The guide message this form was opened from, so submitting it renews
		# that guide's timer (or finds it already closed).
		self.session = session
		self.search_input = discord.ui.TextInput(
			label="What are you looking for?",
			placeholder="e.g., rules, commands, music, channels...",
			max_length=100,
			required=True,
		)
		self.add_item(self.search_input)

	async def on_submit(self, interaction: discord.Interaction):
		query = self.search_input.value
		try:
			message_id = int(self.session["message_id"])
			# The guide may have closed while the form was open.
			if not await guide_sessions.touch(message_id):
				await _respond_closed(interaction, self.guild_id, message_id)
				return
			layout = await guide_manager.handle_search(query, self.guild_id, interaction.user.id)
			await interaction.response.edit_message(view=layout)
			await _after_edit(interaction, self.session, message_id, path=None)
		except Exception as e:
			logger.error(f"Search error: {e}", exc_info=True)
			await interaction.response.send_message(
				f"An error occurred while searching. Please try again.\n\n{SUPPORT_LINE}",
				ephemeral=True,
			)


# ─────────────────────────────────────────────────────────────────────────────
# Action dispatch helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _reply_privately(interaction: discord.Interaction, content: str) -> None:
	"""The usual answer to a channel or role button: a private reply."""
	await interaction.response.send_message(content, ephemeral=True)


def _reply_beside_private_guide(message_id: int):
	"""The answer to a channel or role button on a PRIVATE guide.

	A private guide can only be edited later (to close it) through an
	interaction whose original response IS the guide. Deferring the click as a
	message update makes this click one, so it is kept as the guide's newest
	token; the note itself goes out as a private followup.
	"""
	async def reply(interaction: discord.Interaction, content: str) -> None:
		await interaction.response.defer()
		guide_sessions.remember_interaction(message_id, interaction)
		await interaction.followup.send(content, ephemeral=True)
	return reply


async def _handle_channel_action(interaction: discord.Interaction, channel_id: str, reply=_reply_privately):
	"""Respond with an ephemeral channel link."""
	await reply(interaction, f"Head over to <#{channel_id}>!")


async def _handle_role_action(interaction: discord.Interaction, role_id: str, reply=_reply_privately):
	"""Toggle a role on the interacting member."""
	guild = interaction.guild
	member = interaction.user
	if not guild or not isinstance(member, discord.Member):
		await reply(interaction, "This action is only available in a server.")
		return

	role = guild.get_role(int(role_id))
	if not role:
		await reply(interaction, "That role no longer exists.")
		return

	try:
		if role in member.roles:
			await member.remove_roles(role, reason="Guide role toggle")
			await reply(interaction, f"Removed **{role.name}** from you.")
		else:
			if is_blocked(role, where="guide"):
				await reply(interaction, blocked_role_reason(role))
				return
			await member.add_roles(role, reason="Guide role toggle")
			await reply(interaction, f"Gave you **{role.name}**!")
	except discord.Forbidden:
		await reply(interaction, "I don't have permission to manage that role.")
	except discord.HTTPException as e:
		logger.error(f"Role toggle error: {e}", exc_info=True)
		await reply(interaction, f"Something went wrong managing the role.\n\n{SUPPORT_LINE}")


# ─────────────────────────────────────────────────────────────────────────────
# Guide sessions: who a guide is for, and closing it
# ─────────────────────────────────────────────────────────────────────────────

#: Per guide message, held while one click is handled. Weak values: a lock
#: disappears once no click holds or waits on it, so this never grows.
_message_locks: "weakref.WeakValueDictionary[Any, asyncio.Lock]" = weakref.WeakValueDictionary()


def _message_lock(message_id: Any) -> asyncio.Lock:
	lock = _message_locks.get(message_id)
	if lock is None:
		lock = asyncio.Lock()
		_message_locks[message_id] = lock
	return lock


async def _closed_view(guild_id: int) -> discord.ui.LayoutView:
	"""The closed card in the guide's own colour. Reads the guide without
	creating one, so closing a guide in a server the bot has left cannot
	write a fresh default guide there."""
	guide_data = guide_manager._guide_cache.get(guild_id)
	if guide_data is None:
		guide_data = await guide_store.get_guide(guild_id)
	return GuideRenderer.render_closed(guide_data)


async def _respond_closed(interaction: discord.Interaction, guild_id: int, message_id: int) -> None:
	"""Answer a click on a guide that has closed by turning it into the closed card."""
	await guide_sessions.close(message_id)
	await interaction.response.edit_message(view=await _closed_view(guild_id))


async def _open_session(
	interaction: discord.Interaction, guild_id: int, edits_guide: bool = True,
) -> Optional[Dict[str, Any]]:
	"""Return the live session behind this click, or answer the click and return None.

	- No session, or its time is up: the guide is closed and the click says so.
	  This also covers guides posted before sessions existed.
	- Someone other than the owner: a private refusal; the guide is untouched and
	  its timer is NOT renewed.
	- The owner: the timer is renewed and the session handed back.

	``edits_guide`` is False for a click whose response is not the guide itself
	(opening the search form). On a private guide such a click leaves no token
	that can close the guide later, so its renewal stops where the newest
	usable token runs out - otherwise the guide could outlive every token and
	never visibly close.
	"""
	message_id = interaction.message.id
	session = await guide_sessions.get(message_id)
	if session is None or session.get("expires_at", 0) <= now_ts():
		await _respond_closed(interaction, guild_id, message_id)
		return None

	if session.get("owner_id") != str(interaction.user.id):
		await interaction.response.send_message(
			f"This guide was opened by <@{session['owner_id']}>. Mention me to open your own.",
			ephemeral=True,
			allowed_mentions=discord.AllowedMentions.none(),
		)
		return None

	until = None
	if session.get("ephemeral") and not edits_guide:
		until = guide_sessions.token_deadline(message_id)
	if not await guide_sessions.touch(message_id, until=until):
		# The sweep closed it between the read and the renewal.
		await _respond_closed(interaction, guild_id, message_id)
		return None
	return session


async def _after_edit(
	interaction: discord.Interaction, session: Dict[str, Any], message_id: int,
	path: Optional[List[str]],
) -> None:
	"""Bookkeeping after a click edited the guide message itself."""
	if session.get("ephemeral"):
		# Only an interaction that edited the guide can edit it again later.
		guide_sessions.remember_interaction(message_id, interaction)
	if path is not None and path != session.get("path"):
		await guide_sessions.save_path(message_id, path)


async def post_guide(
	channel: Any, layout: Any, *, guild_id: int, owner_id: int, path: List[str],
):
	"""Post a guide message in a channel and open its session.

	``owner_id`` is the member the guide is for. A view with nothing to click
	(the empty-guide notice) gets no session.
	"""
	message = await channel.send(view=layout)
	if message is None or not has_interactive_items(layout):
		return message
	try:
		await guide_sessions.open(
			message_id=message.id, guild_id=guild_id, channel_id=channel.id,
			owner_id=owner_id, path=path, ephemeral=False,
		)
	except Exception as e:
		# The guide is up but untracked: its first click will show it closed.
		logger.error(f"Could not record guide session for message {message.id}: {e}", exc_info=True)
	return message


async def open_private_guide(interaction: discord.Interaction) -> None:
	"""Send the guide's Home page privately to whoever clicked (the greeting's
	"Open Guide" button) and open its session."""
	path: List[str] = []
	layout = await guide_manager.get_home_view(
		interaction.guild.id, path, interaction=interaction,
	)
	callback = await interaction.response.send_message(view=layout, ephemeral=True)
	if not has_interactive_items(layout):
		return
	message_id = getattr(callback, "message_id", None)
	try:
		if message_id is None:
			message_id = (await interaction.original_response()).id
		await guide_sessions.open(
			message_id=message_id, guild_id=interaction.guild.id,
			channel_id=interaction.channel_id, owner_id=interaction.user.id,
			path=path, ephemeral=True,
		)
	except Exception as e:
		# The member already has their guide; only its session is missing, so
		# its first click will show it closed. Not worth a failure notice.
		logger.error(f"Could not record private guide session ({message_id}): {e}", exc_info=True)
		return
	guide_sessions.remember_interaction(message_id, interaction)


async def _close_guide_message(client: Any, session: Dict[str, Any]) -> bool:
	"""Edit one expired guide into the closed card. False when it cannot be reached."""
	layout = await _closed_view(int(session["guild_id"]))
	if session.get("ephemeral"):
		interaction = guide_sessions.take_interaction(session["message_id"])
		if interaction is None:
			# Restarted since, or the token is too old. The member's next click
			# on it gets the closed card instead.
			return False
		await interaction.edit_original_response(view=layout)
		return True

	channel_id = int(session["channel_id"])
	channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
	await channel.get_partial_message(int(session["message_id"])).edit(view=layout)
	return True


async def close_expired_guides(client: Any) -> int:
	"""Close every guide whose time is up. Returns how many were edited."""
	closed = 0
	for session in await guide_sessions.claim_expired():
		try:
			if await _close_guide_message(client, session):
				closed += 1
		except (discord.NotFound, discord.Forbidden) as e:
			# Message deleted, channel gone, or access lost: nothing left to close.
			logger.info(f"Guide {session.get('message_id')} could not be closed ({type(e).__name__})")
		except Exception as e:
			logger.warning(f"Failed to close guide {session.get('message_id')}: {e}")
	if closed:
		logger.info(f"Closed {closed} expired guide(s)")
	return closed


# ─────────────────────────────────────────────────────────────────────────────
# Interaction Dispatch
# ─────────────────────────────────────────────────────────────────────────────

async def _dispatch_action(
	interaction: discord.Interaction, action: str, target: str | None,
	guild_id: int, session: Dict[str, Any],
):
	"""Route a decoded action to the appropriate handler."""
	message_id = interaction.message.id
	path = list(session.get("path") or [])

	if action == "nav":
		layout = await guide_manager.get_page_view(guild_id, path, target, interaction=interaction)
		await interaction.response.edit_message(view=layout)
		await _after_edit(interaction, session, message_id, path)

	elif action == "back":
		layout = await guide_manager.handle_back(guild_id, path, interaction=interaction)
		await interaction.response.edit_message(view=layout)
		await _after_edit(interaction, session, message_id, path)

	elif action == "home":
		layout = await guide_manager.get_home_view(guild_id, path, interaction=interaction)
		await interaction.response.edit_message(view=layout)
		await _after_edit(interaction, session, message_id, path)

	elif action == "search":
		modal = GuideSearchModal(guild_id, session)
		await interaction.response.send_modal(modal)

	elif action in ("channel", "role"):
		handler = _handle_channel_action if action == "channel" else _handle_role_action
		if session.get("ephemeral"):
			await handler(interaction, target, reply=_reply_beside_private_guide(message_id))
		else:
			await handler(interaction, target)


async def dispatch_guide_interaction(interaction: discord.Interaction) -> bool:
	"""Dispatch a g:-prefixed component interaction.

	Returns True if handled, False if the custom_id doesn't match our prefix.
	Called by the central interaction router in joining.py.
	"""
	if interaction.type != discord.InteractionType.component:
		return False
	if not interaction.guild:
		return False

	# Drop a repeat number added by the renderer (g:_uselect~2), so the exact
	# matches below and the decoder see the original id.
	custom_id = strip_duplicate_suffix(interaction.data.get("custom_id", ""))
	if not custom_id.startswith("g:"):
		return False

	component_type = interaction.data.get("component_type")
	guild_id = interaction.guild.id

	try:
		# Work out what was clicked before touching the guide's session, so an
		# id this dispatcher does not own is passed on untouched.
		page_id = None
		action = target = None
		if component_type == 3:  # String select
			# Auto-generated children / sections / search select - value is a page_id.
			# User-defined select (g:_uselect) - value encodes action:target.
			if custom_id not in ("g:_select", "g:_sections", "g:_uselect"):
				return False
			values = interaction.data.get("values", [])
			if not values:
				return True
			if custom_id == "g:_uselect":
				action, target = decode_select_value(values[0])
			else:
				page_id = values[0]
		else:
			# Handle buttons
			action, target = decode_custom_id(custom_id)
			if action is None:
				return False

		# One click at a time per guide message, so two quick clicks cannot both
		# read the same Back history and have the later save undo the earlier.
		async with _message_lock(getattr(getattr(interaction, "message", None), "id", None)):
			# Closed, someone else's, or live (timer renewed) - see _open_session.
			# Opening the search form is the one click whose answer is not the guide.
			session = await _open_session(interaction, guild_id, edits_guide=action != "search")
			if session is None:
				return True

			if page_id is not None:
				path = list(session.get("path") or [])
				layout = await guide_manager.get_page_view(guild_id, path, page_id, interaction=interaction)
				await interaction.response.edit_message(view=layout)
				await _after_edit(interaction, session, interaction.message.id, path)
				return True

			await _dispatch_action(interaction, action, target, guild_id, session)
			return True

	except Exception as e:
		# A raw on_interaction listener never reaches a view's on_error, so this is
		# the only thing between an exception and a bare "This interaction failed".
		await send_unexpected_failure(interaction, e, f"guide interaction {custom_id!r}")
		return True


class GuideCog(commands.Cog):
	"""Owns the guide's background work: closing guides whose time is up."""

	def __init__(self, bot_instance):
		self.bot = bot_instance

	async def cog_load(self):
		# The first pass runs at once, so guides that expired while the bot
		# was down are closed right after startup.
		self._close_expired.start()

	async def cog_unload(self):
		self._close_expired.cancel()

	@tasks.loop(seconds=SWEEP_INTERVAL_SECONDS)
	async def _close_expired(self):
		try:
			await close_expired_guides(self.bot)
		except Exception as e:
			# Never let one bad pass stop the loop for good.
			logger.error(f"Guide close sweep failed: {e}", exc_info=True)

	@_close_expired.before_loop
	async def _before_close_expired(self):
		await self.bot.wait_until_ready()


async def setup(bot_instance):
	await guide_manager.initialize_database()
	await bot_instance.add_cog(GuideCog(bot_instance))
