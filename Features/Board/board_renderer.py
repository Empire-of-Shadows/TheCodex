"""
Info Board Renderer

Converts a validated board config into discord.ui.LayoutViews.

Two entry points:
  - ``render_board``    the static message posted to a channel
  - ``render_response`` the private layout a button or option reveals

Both go through the same shared component builders, so a response is as rich as
the board itself - it can carry its own buttons pointing at further responses.
"""

from typing import Any, Dict, Optional, Union

import discord

from Features.Board.board_actions import (
    CUSTOM_ID_SELECT,
    encode_custom_id,
    encode_select_value,
)
from utils.component_builders import (
    apply_placeholders,
    build_component,
    build_link_button,
    resolve_color,
)

_STYLE_MAP = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
    "link":      discord.ButtonStyle.link,
}

_DEFAULT_ACCENT = "#4D0EB3"
_FALLBACK_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png"


class BoardRenderer:
    """Renders an info board config into discord.ui.LayoutViews."""

    # ─────────────────────────────────────────────────────────────────────────
    # Entry points
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_board(
        cls,
        board_data: Dict[str, Any],
        guild: Optional[discord.Guild] = None,
    ) -> discord.ui.LayoutView:
        """Render the static board message.

        timeout=None because this message is posted to a channel and must keep
        working indefinitely. Its interactions are routed by custom_id prefix
        rather than by this view instance, so the view is only a builder here -
        but a finite timeout would still be wrong to imply.
        """
        return cls._render_components(
            board_data.get("components", []),
            accent=board_data.get("accent_color", _DEFAULT_ACCENT),
            guild=guild,
            member=None,
        )

    @classmethod
    def render_response(
        cls,
        response: Dict[str, Any],
        board_data: Dict[str, Any],
        guild: Optional[discord.Guild] = None,
        member: Optional[Union[discord.Member, discord.User]] = None,
    ) -> discord.ui.LayoutView:
        """Render one named response as an ephemeral layout.

        A response without its own accent_color inherits the board's, so a board
        and everything it reveals read as one thing.
        """
        accent = response.get("accent_color") or board_data.get("accent_color", _DEFAULT_ACCENT)
        return cls._render_components(
            response.get("components", []),
            accent=accent,
            guild=guild,
            member=member,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Shared rendering
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _render_components(
        cls,
        components: list,
        accent: Any,
        guild: Optional[discord.Guild],
        member: Optional[Union[discord.Member, discord.User]],
    ) -> discord.ui.LayoutView:
        layout = discord.ui.LayoutView(timeout=None)
        layout.accent_color = resolve_color(accent)

        placeholders = cls._build_placeholders(guild, member)

        def resolve_media(media: str) -> str:
            if media == "member_avatar" and member is not None:
                return cls._resolve_avatar(member)
            return media

        for comp in components:
            item = build_component(
                comp,
                placeholders,
                button_builder=cls._build_button,
                select_builder=cls._build_select,
                resolve_media=resolve_media,
            )
            if item is not None:
                layout.add_item(item)

        return layout

    # ─────────────────────────────────────────────────────────────────────────
    # Board-specific builders
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _build_button(
        cls, btn_def: Dict[str, Any], placeholders: Dict[str, str]
    ) -> discord.ui.Button:
        style_str = btn_def.get("style", "primary")
        if style_str == "link":
            return build_link_button(btn_def, placeholders)

        return discord.ui.Button(
            style=_STYLE_MAP.get(style_str, discord.ButtonStyle.primary),
            label=apply_placeholders(btn_def.get("label", "Button"), placeholders),
            custom_id=encode_custom_id(btn_def.get("action", ""), btn_def.get("target", "")),
            emoji=btn_def.get("emoji"),
            disabled=btn_def.get("disabled", False),
        )

    @classmethod
    def _build_select(
        cls, sel_def: Dict[str, Any], placeholders: Dict[str, str]
    ) -> discord.ui.Select:
        options = []
        for opt in sel_def.get("options", [])[:25]:
            desc = opt.get("description")
            if desc:
                desc = apply_placeholders(desc, placeholders)[:100]
            options.append(discord.SelectOption(
                label=apply_placeholders(opt.get("label", "Option"), placeholders)[:100],
                value=encode_select_value(opt.get("action", "reply"), opt.get("target", "")),
                description=desc or None,
                emoji=opt.get("emoji"),
            ))

        placeholder = apply_placeholders(
            sel_def.get("placeholder", "Choose an option..."), placeholders
        )

        return discord.ui.Select(
            custom_id=CUSTOM_ID_SELECT,
            placeholder=placeholder[:150],
            options=options,
            # A board dropdown is a menu, not a form: always exactly one pick, so
            # re-picking the same option fires again rather than deselecting.
            min_values=1,
            max_values=1,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_placeholders(
        guild: Optional[discord.Guild],
        member: Optional[Union[discord.Member, discord.User]],
    ) -> Dict[str, str]:
        """Build the placeholder map.

        The board is a static message with no member context, so member tokens
        resolve to empty strings there and to the clicker in a private response.
        {member_count} and {voice_active} are deliberately absent: the board is
        posted once and edited rarely, so a live-looking count would be stale
        the moment it went up.
        """
        placeholders = {
            "{guild_name}": guild.name if guild else "",
            "{member}": "",
            "{member_name}": "",
        }
        if member is not None:
            placeholders["{member}"] = f"<@{member.id}>"
            placeholders["{member_name}"] = member.display_name
        return placeholders

    @staticmethod
    def _resolve_avatar(member: Union[discord.Member, discord.User]) -> str:
        if getattr(member, "display_avatar", None):
            return member.display_avatar.url
        return _FALLBACK_AVATAR
