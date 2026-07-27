"""
Greeting Message Renderer

Converts a validated greeting_components JSON config into a discord.ui.LayoutView.
Delegates shared component building to utils.component_builders.
"""

import random

import discord
from typing import Any, Dict, Optional

from Features.NewMembers.joining_responses import joining_responses
from Features.NewMembers.greeting_actions import encode_custom_id
from utils.component_builders import (
    resolve_color,
    apply_placeholders,
    build_component,
    build_link_button,
)

_STYLE_MAP = {
    "primary":   discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success":   discord.ButtonStyle.success,
    "danger":    discord.ButtonStyle.danger,
    "link":      discord.ButtonStyle.link,
}

_FALLBACK_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png"


class GreetingRenderer:
    """Renders a JSON greeting config into a discord.ui.LayoutView."""

    @classmethod
    def render(
        cls,
        components_config: Dict[str, Any],
        member: discord.Member,
        member_number: int,
        analytics: Optional[Dict[str, Any]] = None,
    ) -> discord.ui.LayoutView:
        placeholders = cls._build_placeholders(member, member_number, analytics)
        layout_view = discord.ui.LayoutView()

        raw_color = components_config.get("accent_color")
        if raw_color is not None:
            layout_view.accent_color = resolve_color(raw_color)

        def resolve_media(media: str) -> str:
            if media == "member_avatar":
                return cls._resolve_avatar(member)
            return media

        for comp in components_config.get("components", []):
            item = build_component(
                comp,
                placeholders,
                button_builder=cls._build_button,
                select_builder=cls._build_select,
                resolve_media=resolve_media,
            )
            if item is not None:
                layout_view.add_item(item)

        return layout_view

    # ─────────────────────────────────────────────────────────────────────────
    # Greeting-specific builders
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _build_button(cls, btn_def: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.Button:
        style = _STYLE_MAP.get(btn_def.get("style", "primary"), discord.ButtonStyle.primary)
        label = apply_placeholders(btn_def.get("label", "Button"), placeholders)
        emoji = btn_def.get("emoji")
        disabled = btn_def.get("disabled", False)

        if btn_def.get("style") == "link":
            return build_link_button(btn_def, placeholders)
        custom_id = encode_custom_id(btn_def["action"], btn_def.get("params"))
        return discord.ui.Button(
            style=style,
            label=label,
            custom_id=custom_id,
            emoji=emoji,
            disabled=disabled,
        )

    @classmethod
    def _build_select(cls, sel_def: Dict[str, Any], placeholders: Dict[str, str]) -> discord.ui.Select:
        options = []
        for opt in sel_def["options"]:
            options.append(discord.SelectOption(
                label=apply_placeholders(opt["label"], placeholders),
                value=encode_custom_id(opt["action"], opt.get("params")),
                description=opt.get("description"),
                emoji=opt.get("emoji"),
            ))
        return discord.ui.Select(
            custom_id="gr:_select",
            placeholder=sel_def.get("placeholder"),
            options=options,
            min_values=sel_def.get("min_values", 1),
            max_values=sel_def.get("max_values", 1),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_placeholders(
        member: discord.Member,
        member_number: int,
        analytics: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        voice_active = "0"
        if analytics:
            voice_active = str(
                analytics.get("activity_stats", {}).get("active_voice_channels", 0)
            )
        greeting = random.choice(joining_responses).replace(
            "{member.mention}", f"<@{member.id}>"
        )
        return {
            "{member}": f"<@{member.id}>",
            "{member_name}": member.display_name,
            "{member_count}": str(member_number),
            "{guild_name}": member.guild.name,
            "{voice_active}": voice_active,
            "{random_greeting}": greeting,
        }

    @staticmethod
    def _resolve_avatar(member: discord.Member) -> str:
        if member.display_avatar:
            return member.display_avatar.url
        return _FALLBACK_AVATAR
