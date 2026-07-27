"""
Guide System V2

Components V2 guide with page-tree navigation, search, and interaction dispatch.
Guide content is stored as a JSON page tree in the guide_content collection.
"""

import re
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from rapidfuzz import fuzz

from startup.bot import bot
from storage.log import get_logger, PerformanceLogger
from storage.settings.collections import db_manager
from Features.Guide.guide_store import guide_store
from Features.Guide.guide_renderer import GuideRenderer
from Features.Guide.guide_actions import (
	decode_custom_id,
	decode_select_value,
	CUSTOM_ID_SEARCH,
)
from utils.setup_notice import setup_notice_text

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
# Navigation Breadcrumbs - per-guild, per-user
# ─────────────────────────────────────────────────────────────────────────────

class NavigationBreadcrumbs:
	"""Tracks user navigation path per guild (bounded to _MAX_USERS)."""

	_MAX_USERS = 5000

	def __init__(self):
		self.breadcrumbs: Dict[tuple, list] = {}  # (guild_id, user_id) -> [page_id, ...]

	def push(self, guild_id: int, user_id: int, page_id: str):
		key = (guild_id, user_id)
		# Bound memory: evict the oldest tracked user when over capacity.
		if key not in self.breadcrumbs and len(self.breadcrumbs) >= self._MAX_USERS:
			self.breadcrumbs.pop(next(iter(self.breadcrumbs)), None)
		path = self.breadcrumbs.setdefault(key, [])
		# Avoid duplicates at the end
		if not path or path[-1] != page_id:
			path.append(page_id)

	def pop(self, guild_id: int, user_id: int) -> Optional[str]:
		key = (guild_id, user_id)
		path = self.breadcrumbs.get(key, [])
		if len(path) > 1:
			path.pop()
			return path[-1]
		return None

	def get_path(self, guild_id: int, user_id: int) -> list:
		return list(self.breadcrumbs.get((guild_id, user_id), []))

	def reset(self, guild_id: int, user_id: int):
		self.breadcrumbs.pop((guild_id, user_id), None)


# ─────────────────────────────────────────────────────────────────────────────
# Guide Manager - core orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class GuideManager:
	"""Loads guide data, navigates pages, renders via GuideRenderer."""

	def __init__(self):
		self.search_engine = SearchEngine()
		self.navigation = NavigationBreadcrumbs()
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
		self, guild_id: int, user_id: int,
		interaction: discord.Interaction = None,
		guild: discord.Guild = None,
		member: Union[discord.Member, discord.User] = None,
	) -> discord.ui.LayoutView:
		"""Render the "how to use the guide" instructions (shown on a bare mention)."""
		guide_data = await self._get_guide(guild_id)

		self.navigation.reset(guild_id, user_id)

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
		self, guild_id: int, user_id: int, page_id: str,
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
		self.navigation.push(guild_id, user_id, page_id)

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
		self, guild_id: int, user_id: int,
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

		self.navigation.reset(guild_id, user_id)
		home_id = self._home_page_id(pages)
		return await self.get_page_view(
			guild_id, user_id, home_id,
			interaction=interaction, guild=guild, member=member,
		)

	async def handle_back(
		self, guild_id: int, user_id: int,
		interaction: discord.Interaction = None,
	) -> discord.ui.LayoutView:
		"""Navigate back one level."""
		guide_data = await self._get_guide(guild_id)
		pages = guide_data.get("pages", [])

		# Get current path
		nav_path = self.navigation.get_path(guild_id, user_id)
		if len(nav_path) <= 1:
			return await self.get_home_view(guild_id, user_id, interaction=interaction)

		# Pop current, navigate to parent
		self.navigation.pop(guild_id, user_id)
		nav_path = self.navigation.get_path(guild_id, user_id)

		if not nav_path:
			return await self.get_home_view(guild_id, user_id, interaction=interaction)

		parent_id = nav_path[-1]
		page = self._find_page(pages, parent_id)
		if not page:
			return await self.get_home_view(guild_id, user_id, interaction=interaction)

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

class GuideSearchModal(discord.ui.Modal):
	"""Modal for searching guide content."""

	def __init__(self, guild_id: int):
		super().__init__(title="🔍 Search Guide")
		self.guild_id = guild_id
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
			layout = await guide_manager.handle_search(query, self.guild_id, interaction.user.id)
			await interaction.response.edit_message(view=layout)
		except Exception as e:
			logger.error(f"Search error: {e}", exc_info=True)
			await interaction.response.send_message(
				"An error occurred while searching. Please try again.",
				ephemeral=True,
			)


# ─────────────────────────────────────────────────────────────────────────────
# Action dispatch helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_channel_action(interaction: discord.Interaction, channel_id: str):
	"""Respond with an ephemeral channel link."""
	await interaction.response.send_message(
		f"Head over to <#{channel_id}>!",
		ephemeral=True,
	)


async def _handle_role_action(interaction: discord.Interaction, role_id: str):
	"""Toggle a role on the interacting member."""
	guild = interaction.guild
	member = interaction.user
	if not guild or not isinstance(member, discord.Member):
		await interaction.response.send_message("This action is only available in a server.", ephemeral=True)
		return

	role = guild.get_role(int(role_id))
	if not role:
		await interaction.response.send_message("That role no longer exists.", ephemeral=True)
		return

	try:
		if role in member.roles:
			await member.remove_roles(role, reason="Guide role toggle")
			await interaction.response.send_message(f"Removed **{role.name}** from you.", ephemeral=True)
		else:
			await member.add_roles(role, reason="Guide role toggle")
			await interaction.response.send_message(f"Gave you **{role.name}**!", ephemeral=True)
	except discord.Forbidden:
		await interaction.response.send_message("I don't have permission to manage that role.", ephemeral=True)
	except discord.HTTPException as e:
		logger.error(f"Role toggle error: {e}", exc_info=True)
		await interaction.response.send_message("Something went wrong managing the role.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Interaction Dispatch
# ─────────────────────────────────────────────────────────────────────────────

async def _dispatch_action(
	interaction: discord.Interaction, action: str, target: str | None,
	guild_id: int, user_id: int,
):
	"""Route a decoded action to the appropriate handler."""
	if action == "nav":
		layout = await guide_manager.get_page_view(guild_id, user_id, target, interaction=interaction)
		await interaction.response.edit_message(view=layout)

	elif action == "back":
		layout = await guide_manager.handle_back(guild_id, user_id, interaction=interaction)
		await interaction.response.edit_message(view=layout)

	elif action == "home":
		layout = await guide_manager.get_home_view(guild_id, user_id, interaction=interaction)
		await interaction.response.edit_message(view=layout)

	elif action == "search":
		modal = GuideSearchModal(guild_id)
		await interaction.response.send_modal(modal)

	elif action == "channel":
		await _handle_channel_action(interaction, target)

	elif action == "role":
		await _handle_role_action(interaction, target)


async def dispatch_guide_interaction(interaction: discord.Interaction) -> bool:
	"""Dispatch a g:-prefixed component interaction.

	Returns True if handled, False if the custom_id doesn't match our prefix.
	Called by the central interaction router in joining.py.
	"""
	if interaction.type != discord.InteractionType.component:
		return False
	if not interaction.guild:
		return False

	custom_id = interaction.data.get("custom_id", "")
	if not custom_id.startswith("g:"):
		return False

	component_type = interaction.data.get("component_type")
	guild_id = interaction.guild.id
	user_id = interaction.user.id

	try:
		# Handle select menus
		if component_type == 3:  # String select
			# Auto-generated children / sections / search select - value is a page_id
			if custom_id in ("g:_select", "g:_sections"):
				values = interaction.data.get("values", [])
				if not values:
					return True
				page_id = values[0]
				layout = await guide_manager.get_page_view(guild_id, user_id, page_id, interaction=interaction)
				await interaction.response.edit_message(view=layout)
				return True

			# User-defined select - value encodes action:target
			if custom_id == "g:_uselect":
				values = interaction.data.get("values", [])
				if not values:
					return True
				action, target = decode_select_value(values[0])
				await _dispatch_action(interaction, action, target, guild_id, user_id)
				return True

			return False

		# Handle buttons
		action, target = decode_custom_id(custom_id)
		if action is None:
			return False

		await _dispatch_action(interaction, action, target, guild_id, user_id)
		return True

	except Exception as e:
		logger.error(f"Error handling guide interaction '{custom_id}': {e}", exc_info=True)
		if not interaction.response.is_done():
			await interaction.response.send_message(
				"Something went wrong. Please try again.", ephemeral=True,
			)
		return True


class GuideCog(commands.Cog):
	"""Handles guide interactions and commands."""

	def __init__(self, bot_instance):
		self.bot = bot_instance


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers for external callers
# ─────────────────────────────────────────────────────────────────────────────

async def get_help_menu(
	user_id: int, guild_id: int = None,
	interaction: discord.Interaction = None,
	guild: discord.Guild = None,
	member: Union[discord.Member, discord.User] = None,
) -> discord.ui.LayoutView:
	"""Get the guide's Home page. Used by greeting_actions open_guide handler."""
	if guild_id is None:
		raise ValueError("guild_id is required")
	return await guide_manager.get_home_view(
		guild_id, user_id,
		interaction=interaction, guild=guild, member=member,
	)


async def setup(bot_instance):
	await guide_manager.initialize_database()
	await bot_instance.add_cog(GuideCog(bot_instance))
