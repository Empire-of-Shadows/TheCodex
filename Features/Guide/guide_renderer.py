"""
Guide Renderer - renders a guide page to a discord.ui.LayoutView with navigation chrome.

Layout structure:
  Container (accent_color):
    TextDisplay: breadcrumb trail
    Separator
    [user-defined content components from page.content]
  ActionRow (if page has children):
    Select dropdown with child pages as options
  ActionRow (navigation chrome - always present):
    [Back] [Home] [Search]
"""

import random

import discord
from typing import Any, Dict, List, Optional, Union

from Features.Guide.guide_actions import (
	encode_nav,
	encode_channel,
	encode_role,
	encode_select_value,
	CUSTOM_ID_BACK,
	CUSTOM_ID_HOME,
	CUSTOM_ID_SEARCH,
	CUSTOM_ID_SELECT,
	CUSTOM_ID_USELECT,
	CUSTOM_ID_SECTIONS,
)
from Features.NewMembers.joining_responses import joining_responses
from utils.component_builders import (
	resolve_color,
	apply_placeholders,
	build_component,
	build_link_button,
)
from storage.log import get_logger

logger = get_logger("GuideRenderer")

_STYLE_MAP = {
	"primary":   discord.ButtonStyle.primary,
	"secondary": discord.ButtonStyle.secondary,
	"success":   discord.ButtonStyle.success,
	"danger":    discord.ButtonStyle.danger,
	"link":      discord.ButtonStyle.link,
}

_ACTION_ENCODERS = {
	"navigate": lambda target: encode_nav(target),
	"channel":  lambda target: encode_channel(target),
	"role":     lambda target: encode_role(target),
}


class GuideRenderer:
	"""Renders a guide page into a discord.ui.LayoutView with navigation chrome."""

	@classmethod
	def render_page(
		cls,
		page: Dict[str, Any],
		guide_data: Dict[str, Any],
		breadcrumb_path: List[str],
		is_root: bool = False,
		interaction: Optional[discord.Interaction] = None,
		guild: Optional[discord.Guild] = None,
		member: Optional[Union[discord.Member, discord.User]] = None,
	) -> discord.ui.LayoutView:
		"""Render a single guide page as a LayoutView.

		Args:
			page: The page dict from the guide JSON.
			guide_data: The top-level guide data (for accent_color).
			breadcrumb_path: List of page labels for the breadcrumb trail.
			is_root: True if this is the root page list (no Back button).
			interaction: The triggering interaction (for placeholder substitution).
			guild: Guild context (alternative to interaction).
			member: Member context (alternative to interaction).
		"""
		layout = discord.ui.LayoutView(timeout=600.0)

		accent_color = resolve_color(guide_data.get("accent_color", "#4D0EB3"))

		# ── Page content ────────────────────────────────────────────────
		# Components are added directly to the layout - containers as
		# containers, text/separators/etc. as bare top-level items.
		content = page.get("content")
		if content and "components" in content:
			resolved_member = member or (interaction.user if interaction else None)
			placeholders = cls._build_placeholders(
				guild=guild or (interaction.guild if interaction else None),
				member=resolved_member,
			)

			def resolve_media(media: str) -> str:
				if media == "member_avatar" and resolved_member:
					return cls._resolve_avatar(resolved_member)
				return media

			for comp in content["components"]:
				item = build_component(
					comp,
					placeholders,
					button_builder=cls._build_guide_button,
					select_builder=cls._build_guide_select,
					resolve_media=resolve_media,
				)
				if item is not None:
					layout.add_item(item)
		else:
			# No content - show title/description header
			label = page.get("label", "Guide")
			desc = page.get("description", "")
			header = f"## {label}"
			if desc:
				header += f"\n{desc}"
			layout.add_item(discord.ui.TextDisplay(header))

		# ── Children dropdown ───────────────────────────────────────────
		children = page.get("children", [])
		if children:
			layout.add_item(cls._build_children_select(children))

		# ── Top-level sections (Home page only) ──────────────────────────
		# Keeps the other top-level sections reachable now that there's no menu.
		# Exclude the Home page itself, identified by id (its label may vary).
		if is_root:
			home_id = page.get("id")
			sections = [p for p in guide_data.get("pages", []) if p.get("id") != home_id]
			if sections:
				layout.add_item(cls._build_children_select(
					sections,
					custom_id=CUSTOM_ID_SECTIONS,
					placeholder="Jump to a section...",
				))

		# ── Breadcrumb ──────────────────────────────────────────────────
		if breadcrumb_path:
			breadcrumb_text = " › ".join(breadcrumb_path)
			layout.add_item(discord.ui.TextDisplay(f"-# {breadcrumb_text}"))

		# ── Navigation chrome ───────────────────────────────────────────
		layout.add_item(cls._build_nav_row(is_root=is_root))

		return layout

	@classmethod
	def render_empty(
		cls,
		guide_data: Dict[str, Any],
		interaction: Optional[discord.Interaction] = None,
		guild: Optional[discord.Guild] = None,
		member: Optional[Union[discord.Member, discord.User]] = None,
		setup_hint: str = "",
	) -> discord.ui.LayoutView:
		"""Render a friendly placeholder when the guide has no pages yet.

		``setup_hint`` carries the "here is how to fix this" text, built by the
		caller (it needs an async config read, which this renderer cannot do).
		"""
		layout = discord.ui.LayoutView(timeout=600.0)

		accent_color = resolve_color(guide_data.get("accent_color", "#4D0EB3"))

		container = discord.ui.Container(
			discord.ui.TextDisplay("## 📖 Server Guide"),
			discord.ui.TextDisplay("This guide doesn't have any pages yet."),
		)
		if setup_hint:
			container.add_item(discord.ui.Separator())
			container.add_item(discord.ui.TextDisplay(setup_hint))
		container.accent_colour = accent_color
		layout.add_item(container)

		return layout

	@classmethod
	def render_usage(
		cls,
		guide_data: Dict[str, Any],
		interaction: Optional[discord.Interaction] = None,
		guild: Optional[discord.Guild] = None,
		member: Optional[Union[discord.Member, discord.User]] = None,
	) -> discord.ui.LayoutView:
		"""Render the "how to use the guide" instructions shown on a bare mention."""
		layout = discord.ui.LayoutView(timeout=600.0)

		accent_color = resolve_color(guide_data.get("accent_color", "#4D0EB3"))

		intro = (
			"Mention me whenever you need a hand finding your way around the "
			"server. Here are the ways to use me:\n\n"
			"**🔎 Ask about a topic**\n"
			"Mention me with a keyword and I'll take you straight to the closest "
			"match - for example *rules*, *roles*, or *how do I level up*.\n\n"
			"**📖 Open the guide**\n"
			"Mention me with **help** (or *guide*, *faq*, *support*) and I'll "
			"drop you on the guide's Home page - explore everything from there.\n\n"
			"**👋 Just mention me**\n"
			"Mention me on my own (like you just did) to see this quick how-to "
			"any time."
		)

		details = (
			"**Getting around the guide**\n"
			"- Use the **dropdown** on a page to open its sub-sections.\n"
			"- Tap **🔍 Search** to look through everything by keyword.\n"
			"- Use **◀ Back** and **🏠 Home** to move around.\n\n"
			"**💡 Tips**\n"
			"- The more specific your wording, the better the match - try the "
			"exact name of what you're after.\n"
			"- Can't find it? Open the guide and browse, or hit Search."
		)

		container = discord.ui.Container(
			discord.ui.TextDisplay("## 📖 How to Use the Server Guide"),
			discord.ui.TextDisplay(intro),
			discord.ui.Separator(),
			discord.ui.TextDisplay(details),
		)
		container.accent_colour = accent_color
		layout.add_item(container)

		# Entry buttons - reuse the existing home/search handlers so no new
		# interaction routing is needed.
		nav_row = discord.ui.ActionRow()
		nav_row.add_item(discord.ui.Button(
			label="Open Guide",
			style=discord.ButtonStyle.primary,
			custom_id=CUSTOM_ID_HOME,
			emoji="📖",
		))
		nav_row.add_item(discord.ui.Button(
			label="Search",
			style=discord.ButtonStyle.secondary,
			custom_id=CUSTOM_ID_SEARCH,
			emoji="🔍",
		))
		layout.add_item(nav_row)

		return layout

	# ─────────────────────────────────────────────────────────────────────────
	# Private builders
	# ─────────────────────────────────────────────────────────────────────────

	@staticmethod
	def _build_placeholders(
		guild: Optional[discord.Guild] = None,
		member: Optional[Union[discord.Member, discord.User]] = None,
	) -> Dict[str, str]:
		"""Build placeholder dict from guild/member context.

		Supports the same placeholders as the greeting system:
		{member}, {member_name}, {member_count}, {guild_name},
		{voice_active}, {random_greeting}
		"""
		if member is None:
			return {}

		member_count = "0"
		voice_active = "0"
		guild_name = ""
		if guild:
			guild_name = guild.name
			member_count = str(sum(1 for m in guild.members if not m.bot))
			voice_active = str(sum(
				1 for vc in guild.voice_channels if len(vc.members) > 0
			))

		greeting = random.choice(joining_responses).replace(
			"{member.mention}", f"<@{member.id}>"
		)

		return {
			"{member}": f"<@{member.id}>",
			"{member_name}": member.display_name,
			"{member_count}": member_count,
			"{guild_name}": guild_name,
			"{voice_active}": voice_active,
			"{random_greeting}": greeting,
		}

	@staticmethod
	def _resolve_avatar(member: Union[discord.Member, discord.User]) -> str:
		if hasattr(member, 'display_avatar') and member.display_avatar:
			return member.display_avatar.url
		return "https://cdn.discordapp.com/embed/avatars/0.png"

	@classmethod
	def _build_guide_button(cls, btn_def: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.Button:
		"""Build a guide button. Supports navigate, channel, role actions and link style."""
		style_str = btn_def.get("style", "primary")

		if style_str == "link":
			return build_link_button(btn_def, placeholders)

		style = _STYLE_MAP.get(style_str, discord.ButtonStyle.primary)
		label = apply_placeholders(btn_def.get("label", "Button"), placeholders)
		emoji = btn_def.get("emoji")

		action = btn_def.get("action", "")
		target = btn_def.get("target", "")
		encoder = _ACTION_ENCODERS.get(action)
		if encoder:
			custom_id = encoder(target)
		else:
			custom_id = f"g:{action}"

		return discord.ui.Button(
			style=style,
			label=label,
			custom_id=custom_id,
			emoji=emoji,
		)

	@classmethod
	def _build_guide_select(cls, sel_def: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.Select:
		"""Build a user-defined guide select with mixed action types."""
		options = []
		for opt in sel_def.get("options", [])[:25]:
			action = opt.get("action", "navigate")
			target = opt.get("target", "")
			value = encode_select_value(action, target)
			label = apply_placeholders(opt.get("label", "Option"), placeholders)
			desc = opt.get("description")
			if desc:
				desc = apply_placeholders(desc, placeholders)[:100]
			emoji = opt.get("emoji")

			options.append(discord.SelectOption(
				label=label[:100],
				value=value,
				description=desc or None,
				emoji=emoji,
			))

		placeholder = apply_placeholders(sel_def.get("placeholder", "Choose..."), placeholders)

		return discord.ui.Select(
			custom_id=CUSTOM_ID_USELECT,
			placeholder=placeholder[:150],
			options=options,
		)

	@classmethod
	def _build_children_select(
		cls,
		children: List[Dict[str, Any]],
		custom_id: str = CUSTOM_ID_SELECT,
		placeholder: str = "Select a topic...",
	) -> discord.ui.ActionRow:
		"""Build a select dropdown for child pages (or top-level sections)."""
		# Sort by order
		sorted_children = sorted(children, key=lambda p: p.get("order", 999))

		options = []
		for child in sorted_children[:25]:  # Discord max 25 options
			page_id = child.get("id", "")
			label = child.get("label", "Page")[:100]
			desc = child.get("description", "")[:100] or None
			emoji = child.get("icon")

			options.append(discord.SelectOption(
				label=label,
				value=page_id,
				description=desc,
				emoji=emoji,
			))

		select = discord.ui.Select(
			custom_id=custom_id,
			placeholder=placeholder,
			options=options,
		)

		row = discord.ui.ActionRow()
		row.add_item(select)
		return row

	@classmethod
	def _build_nav_row(cls, is_root: bool = False) -> discord.ui.ActionRow:
		"""Build the navigation chrome action row."""
		row = discord.ui.ActionRow()

		if not is_root:
			row.add_item(discord.ui.Button(
				label="Back",
				style=discord.ButtonStyle.secondary,
				custom_id=CUSTOM_ID_BACK,
				emoji="◀",
			))
			row.add_item(discord.ui.Button(
				label="Home",
				style=discord.ButtonStyle.secondary,
				custom_id=CUSTOM_ID_HOME,
				emoji="🏠",
			))

		row.add_item(discord.ui.Button(
			label="Search",
			style=discord.ButtonStyle.primary,
			custom_id=CUSTOM_ID_SEARCH,
			emoji="🔍",
		))

		return row
