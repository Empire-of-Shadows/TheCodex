"""
Admin Panel Config Trees.

Defines PanelNode config trees for panels migrated to the generic engine.
Each top-level node is passed to AdminCog._navigate_to() from the relevant
_show_* handler.
"""

import json
import os
from functools import partial

import discord

from .views.panel_engine import PanelNode
from .views.embed_views import TIER_NAMES, TIER_LABELS, FEATURE_OPTIONS
from .panel_branding import PANEL_TITLE, PANEL_DESCRIPTION
from storage.config_manager import get_config_manager
from .actions.embed_config_actions import EmbedConfigActions
from .actions.wyr_actions import WYRConfigActions
from .actions.new_member_actions import NewMemberActions
from .actions.announcement_actions import AnnouncementActions
from .actions.suggestion_actions import SuggestionActions
from .actions.guide_actions import GuideActions
from .actions.drops_actions import DropsActions
from .actions.color_set_actions import ColorSetActions
from storage.setup_gatekeeper import setup_gatekeeper
from Features.NewMembers.welcome_schema import validate_welcome_schema
from Features.Guide.guide_schema import validate_guide_schema

def _value_diverges(getter, default_str: str):
    """Build an `is_customized` predicate that returns True when the leaf's
    current value (stringified) differs from the supplied default."""
    async def _pred(guild_id: int) -> bool:
        try:
            vals = list(await getter(guild_id))
        except Exception:
            return False
        if not vals:
            return False
        return str(vals[0]) != default_str
    return _pred

# ── Template download helpers ────────────────────────────────────────────────

_WELCOME_TEMPLATE = {
    "accent_color": "#5865F2",
    "components": [
        {"type": "separator"},
        {
            "type": "section",
            "content": [{"type": "text", "content": "# Welcome to {guild_name}, {member}!\n*You are member #{member_count}!*"}],
            "accessory": {"type": "thumbnail", "media": "member_avatar"},
        },
        {
            "type": "action_row",
            "buttons": [
                {"type": "button", "style": "success", "label": "Guide", "action": "open_guide"},
                {"type": "button", "style": "link", "label": "Rules", "url": "https://discord.com/channels/GUILD/CHANNEL"},
                {"type": "button", "style": "link", "label": "Come Chat!", "url": "https://discord.com/channels/GUILD/CHANNEL"},
            ],
        },
        {"type": "separator"},
        {
            "type": "section",
            "content": [{"type": "text", "content": "**Explore and have fun!**\n- Play games, compete in leaderboards\n- Join voice ({voice_active} active now!)"}],
            "accessory": {"type": "button", "style": "link", "label": "Server Info", "url": "https://discord.com/channels/GUILD/CHANNEL"},
        },
        {"type": "separator"},
        {
            "type": "section",
            "content": [{"type": "text", "content": "Some other channels you might like"}],
            "accessory": {"type": "button", "style": "secondary", "label": "All Channels", "action": "channel_list"},
        },
        {
            "type": "action_row",
            "buttons": [
                {"type": "button", "style": "link", "label": "Media", "url": "https://discord.com/channels/GUILD/CHANNEL"},
                {"type": "button", "style": "link", "label": "Game Clips", "url": "https://discord.com/channels/GUILD/CHANNEL"},
                {"type": "button", "style": "link", "label": "Gamer Chat", "url": "https://discord.com/channels/GUILD/CHANNEL"},
            ],
        },
        {"type": "separator"},
        {"type": "text", "content": "-# {random_greeting}"},
    ],
}

_GUIDE_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "defaults", "guide_template.json",
)


def _welcome_template_data() -> tuple[bytes, str]:
    return json.dumps(_WELCOME_TEMPLATE, indent=2, ensure_ascii=False).encode("utf-8"), "welcome_template.json"


def _guide_template_data() -> tuple[bytes, str]:
    with open(_GUIDE_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"), "guide_template.json"


class _SkipInitialPostView(discord.ui.View):
    """One-shot view attached to the WYR auto-enable message.

    Lets the admin skip the first catch-up post that would fire immediately
    when WYR is enabled after the scheduled time has already passed today.
    """

    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id

    @discord.ui.button(label="Skip First Post", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await WYRConfigActions.set_skip_initial_post(self.guild_id, True)
        button.disabled = True
        button.label = "First Post Skipped"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            "The first WYR post has been skipped. Posts will begin at the next scheduled time.",
            ephemeral=True,
        )
        self.stop()


_FEATURE_AUTO_ENABLE = {
    "embed": {
        "get_enabled": EmbedConfigActions.get_enabled,
        "has_config":  EmbedConfigActions.has_any_tier_configured,
        "set_enabled": EmbedConfigActions.set_enabled,
        "invalidate":  setup_gatekeeper.invalidate_embed,
        "message": (
            "✅ **Embed creation is now enabled.** At least one tier has roles assigned, "
            "so members with those roles can use `/embed create`. "
            "Configure **Color Tiers** and **Feature Access** to control what they can do."
        ),
    },
    "wyr": {
        "get_enabled": WYRConfigActions.get_enabled,
        "has_config":  WYRConfigActions.has_channel_configured,
        "set_enabled": WYRConfigActions.set_enabled,
        "invalidate":  setup_gatekeeper.invalidate_wyr,
        "message": (
            "✅ **WYR is now enabled.** Questions will post daily at the configured time. "
            "If the scheduled time has already passed today, a post will be sent shortly. "
            "Use the button below to skip that first post if you'd prefer to wait.\n\n"
            "Use **WYR Schedule** to set the posting time and **WYR Thread Settings** to "
            "customize how discussions are created."
        ),
        "view_factory": lambda guild_id: _SkipInitialPostView(guild_id),
    },
    "new_members": {
        "get_enabled": NewMemberActions.get_enabled,
        "has_config":  NewMemberActions.has_channel_configured,
        "set_enabled": NewMemberActions.set_enabled,
        "invalidate":  setup_gatekeeper.invalidate_new_members,
        "message": (
            "✅ **New Member processing is now enabled.** Members will now be screened on join. "
            "Use **General Settings** to configure the age requirement and auto-kick, and "
            "**Welcome Message Builder** to upload a custom JSON layout."
        ),
    },
}


async def _auto_enable_feature_if_ready(
    interaction, guild_id: int, selected_values: list, *, feature_key: str
) -> None:
    """Generic post-save hook that auto-enables a feature when its minimum config is met.

    Bind feature_key via functools.partial before assigning to PanelNode.post_save_hook.
    """
    cfg = _FEATURE_AUTO_ENABLE[feature_key]

    if await cfg["get_enabled"](guild_id):
        return  # Already enabled — nothing to do

    if not await cfg["has_config"](guild_id):
        return  # Config still empty (values were cleared, not added)

    ok = await cfg["set_enabled"](guild_id, True)
    if not ok:
        return

    cfg["invalidate"](guild_id)

    view_factory = cfg.get("view_factory")
    view = view_factory(guild_id) if view_factory else None
    await interaction.followup.send(cfg["message"], view=view, ephemeral=True)


async def _warn_unconfigured_feature_tiers(interaction, guild_id: int, selected_tiers: list) -> None:
    """Post-save hook for Feature Access nodes.

    After the admin saves which tiers can access a feature, checks each selected
    tier and sends an ephemeral followup warning for any that have no roles assigned
    (so the access setting will silently have no effect for those tiers).
    """
    unconfigured = [
        TIER_LABELS[t] for t in selected_tiers
        if not await setup_gatekeeper.is_tier_ready(guild_id, t)
    ]
    if not unconfigured:
        return

    count = len(unconfigured)
    names = ", ".join(f"**{t}**" for t in unconfigured)
    await interaction.followup.send(
        f"\u26a0\ufe0f {names} {'has' if count == 1 else 'have'} no roles assigned yet \u2014 "
        f"{'that tier' if count == 1 else 'those tiers'} won\u2019t grant access to this feature "
        "until roles are configured in **Role Tier Mapping**.",
        ephemeral=True,
    )


# ── Description Limits helpers ────────────────────────────────────────────────

def _validate_char_limit(raw: str):
    """Validator for modal_input: ensures value is an integer in 1–4000."""
    try:
        val = int(raw.strip())
    except ValueError:
        return False, None, "Please enter a valid number (1–4000)."
    if not (1 <= val <= 4000):
        return False, None, "Limit must be between 1 and 4000."
    return True, val, ""


async def _get_default_limit(guild_id: int) -> list:
    data = await EmbedConfigActions.get_description_limits(guild_id)
    return [str(data.get("default_limit", 500))]


async def _set_default_limit(guild_id: int, values: list) -> bool:
    try:
        return await EmbedConfigActions.set_default_limit(guild_id, int(values[0]))
    except (ValueError, IndexError):
        return False


async def _get_tier_limit(guild_id: int, tier_name: str) -> list:
    data = await EmbedConfigActions.get_description_limits(guild_id)
    limit = data.get("tier_limits", {}).get(tier_name, 0)
    return [str(limit)] if limit else []


async def _set_tier_limit(guild_id: int, values: list, tier_name: str) -> bool:
    try:
        return await EmbedConfigActions.set_tier_description_limit(guild_id, tier_name, int(values[0]))
    except (ValueError, IndexError):
        return False


async def _clear_tier_limit(guild_id: int, tier_name: str) -> bool:
    return await EmbedConfigActions.remove_tier_description_limit(guild_id, tier_name)


# ── Role-to-Tier ─────────────────────────────────────────────────────────────

_TIER_DESCRIPTIONS = {
    "tier_1": (
        "**Widest access.** Assign every role that should unlock basic embed features — typically "
        "all 5 progression roles. Any member holding at least one of these roles gets Tier 1 access."
    ),
    "tier_2": (
        "**Second tier.** Assign all roles except the entry role (usually roles 2–5). "
        "Members who have progressed past Tier 1 will automatically qualify."
    ),
    "tier_3": (
        "**Mid-tier.** Assign the middle and higher roles (usually roles 3–5). "
        "Only members who have reached at least this progression level will qualify."
    ),
    "tier_4": (
        "**Near-top tier.** Assign only the top two roles (usually roles 4–5). "
        "Reserved for active, long-standing members."
    ),
    "tier_5": (
        "**Most exclusive.** Assign only your single top progression role. "
        "Only the highest-level members will unlock Tier 5 features."
    ),
}

ROLE_TIER_CONFIG = PanelNode(
    key="role_tiers",
    label="Role Tier Mapping",
    kind="menu",
    description=(
        "Tiers control which embed features and colors a member can access based on their roles.\n\n"
        "**How it works:** Members hold one progression role at a time — when they level up, they "
        "lose their current role and gain the next. Assign roles to tiers so that access updates "
        "automatically as members progress.\n\n"
        "**Typical setup** (5 roles: R1 = entry → R5 = top):\n"
        "- **Tier 1** → R1, R2, R3, R4, R5 — everyone gets basic access\n"
        "- **Tier 2** → R2, R3, R4, R5\n"
        "- **Tier 3** → R3, R4, R5\n"
        "- **Tier 4** → R4, R5\n"
        "- **Tier 5** → R5 only — most exclusive\n\n"
        "**Before you begin:** Create 5 Discord roles in your server, one per progression level."
    ),
    children={
        t: PanelNode(
            key=t,
            label=TIER_LABELS[t],
            kind="role_select",
            description=_TIER_DESCRIPTIONS[t],
            get_values=lambda guild_id, _t=t: EmbedConfigActions.get_roles_for_tier(guild_id, _t),
            set_values=lambda guild_id, ids, _t=t: EmbedConfigActions.set_roles_for_tier(guild_id, _t, ids),
            clear_values=lambda guild_id, _t=t: EmbedConfigActions.clear_tier(guild_id, _t),
            post_save_hook=partial(_auto_enable_feature_if_ready, feature_key="embed"),
            min_values=1,
            max_values=25,
        )
        for t in TIER_NAMES
    },
)


# ── Feature Access ────────────────────────────────────────────────────────────

FEATURE_ACCESS_CONFIG = PanelNode(
    key="feature_access",
    label="Feature Access",
    kind="menu",
    children={
        key: PanelNode(
            key=key,
            label=label,
            kind="option_select",
            description=f"Select which tiers can access **{label}**.",
            get_values=lambda guild_id, _k=key: EmbedConfigActions.get_tiers_for_feature(guild_id, _k),
            set_values=lambda guild_id, tiers, _k=key: EmbedConfigActions.set_feature_tiers(guild_id, _k, tiers),
            clear_values=lambda guild_id, _k=key: EmbedConfigActions.remove_feature(guild_id, _k),
            post_save_hook=_warn_unconfigured_feature_tiers,
            options=[(t, TIER_LABELS[t]) for t in TIER_NAMES],
            min_values=1,
            max_values=len(TIER_NAMES),
        )
        for key, label, _ in FEATURE_OPTIONS
    },
)


# ── Description Limits ────────────────────────────────────────────────────────

DESCRIPTION_LIMITS_CONFIG = PanelNode(
    key="description_limits",
    label="Description Limits",
    kind="menu",
    description="Configure character limits for embed descriptions.",
    default_summary="Using defaults",
    children={
        "default_limit": PanelNode(
            key="default_limit",
            label="Default Limit",
            kind="option_select",
            description="Set the default character limit applied to all users.",
            get_values=_get_default_limit,
            set_values=_set_default_limit,
            is_customized=_value_diverges(_get_default_limit, "500"),
            options=[(str(v), f"{v} characters") for v in [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]],
            min_values=1,
            max_values=1,
        ),
        **{
            t: PanelNode(
                key=f"{t}_limit",
                label=f"{TIER_LABELS[t]} Limit",
                kind="modal_input",
                description=f"Set the character limit for {TIER_LABELS[t]} embed descriptions (1–4000).",
                get_values=lambda guild_id, _t=t: _get_tier_limit(guild_id, _t),
                set_values=lambda guild_id, vals, _t=t: _set_tier_limit(guild_id, vals, _t),
                clear_values=lambda guild_id, _t=t: _clear_tier_limit(guild_id, _t),
                pre_check=lambda inter, gid, _t=t: setup_gatekeeper.get_tier_gate_layout(gid, _t),
                modal_title=f"Set {TIER_LABELS[t]} Description Limit",
                modal_label="Character Limit",
                modal_placeholder="e.g., 1000  (1–4000)",
                modal_min_length=0,
                modal_max_length=4,
                modal_required=False,
                modal_validator=_validate_char_limit,
            )
            for t in TIER_NAMES
        },
    },
)


# ── WYR option constants ──────────────────────────────────────────────────────

_WYR_TIMEZONE_OPTIONS = [
    ("America/New_York", "US Eastern"),
    ("America/Chicago", "US Central"),
    ("America/Denver", "US Mountain"),
    ("America/Los_Angeles", "US Pacific"),
    ("Europe/London", "UK / GMT"),
    ("Europe/Paris", "Central Europe"),
    ("Europe/Berlin", "Germany"),
    ("Asia/Tokyo", "Japan"),
    ("Australia/Sydney", "Australia Eastern"),
]

_WYR_ARCHIVE_OPTIONS = [
    ("60", "1 Hour"),
    ("1440", "1 Day"),
    ("4320", "3 Days"),
    ("10080", "1 Week"),
]

_WYR_CATEGORY_OPTIONS = [
    ("sfw", "SFW", "Safe-for-work questions only"),
    ("nsfw", "NSFW", "Not-safe-for-work questions only"),
    ("mixed", "Mixed", "Both SFW and NSFW questions"),
]

_WYR_CLEANUP_OPTIONS = [
    ("7", "7 Days"),
    ("14", "14 Days"),
    ("30", "30 Days"),
    ("60", "60 Days"),
    ("90", "90 Days"),
]


# ── WYR PanelNode configs ─────────────────────────────────────────────────────

async def _set_wyr_channel(guild_id: int, ids: list) -> bool:
    ok = await WYRConfigActions.set_wyr_channel(guild_id, int(ids[0]))
    if ok:
        setup_gatekeeper.invalidate_wyr(guild_id)
    return ok


async def _clear_wyr_channel(guild_id: int) -> bool:
    ok = await WYRConfigActions.set_wyr_channel(guild_id, None)
    if ok:
        setup_gatekeeper.invalidate_wyr(guild_id)
    return ok


WYR_CHANNEL_CONFIG = PanelNode(
    key="wyr_channel",
    label="WYR Channel",
    kind="channel_select",
    description="Select the channel where WYR questions will be posted daily.",
    get_values=WYRConfigActions._get_channel_list,
    set_values=_set_wyr_channel,
    clear_values=_clear_wyr_channel,
    post_save_hook=partial(_auto_enable_feature_if_ready, feature_key="wyr"),
    min_values=1,
    max_values=1,
)

WYR_PING_ROLE_CONFIG = PanelNode(
    key="wyr_ping_role",
    label="WYR Ping Role",
    kind="role_select",
    description="Role pinged when a WYR question is posted. Leave empty for no ping.",
    get_values=WYRConfigActions.get_ping_role,
    set_values=WYRConfigActions.set_ping_role,
    clear_values=WYRConfigActions.clear_ping_role,
    min_values=1,
    max_values=1,
)

WYR_SCHEDULE_CONFIG = PanelNode(
    key="wyr_schedule",
    label="WYR Schedule",
    kind="menu",
    description="Configure when WYR questions post each day. Each field autosaves independently.",
    default_summary="Using defaults",
    children={
        "wyr_hour": PanelNode(
            key="wyr_hour",
            label="Post Hour",
            kind="option_select",
            description="Hour of day for WYR posts (24-hour clock, server local time).",
            options=[(str(h), f"{h:02d}:00") for h in range(24)],
            get_values=WYRConfigActions.get_schedule_hour,
            set_values=WYRConfigActions.set_schedule_hour,
            is_customized=_value_diverges(WYRConfigActions.get_schedule_hour, "6"),
            min_values=1,
            max_values=1,
        ),
        "wyr_minute": PanelNode(
            key="wyr_minute",
            label="Post Minute",
            kind="option_select",
            description="Minute offset for WYR posts.",
            options=[("0", ":00"), ("15", ":15"), ("30", ":30"), ("45", ":45")],
            get_values=WYRConfigActions.get_schedule_minute,
            set_values=WYRConfigActions.set_schedule_minute,
            is_customized=_value_diverges(WYRConfigActions.get_schedule_minute, "0"),
            min_values=1,
            max_values=1,
        ),
        "wyr_timezone": PanelNode(
            key="wyr_timezone",
            label="Timezone",
            kind="option_select",
            description="Timezone used when interpreting the post hour/minute.",
            options=_WYR_TIMEZONE_OPTIONS,
            get_values=WYRConfigActions.get_schedule_timezone,
            set_values=WYRConfigActions.set_schedule_timezone,
            is_customized=_value_diverges(WYRConfigActions.get_schedule_timezone, "America/Chicago"),
            min_values=1,
            max_values=1,
        ),
    },
)

WYR_CATEGORY_CONFIG = PanelNode(
    key="wyr_category",
    label="WYR Category",
    kind="option_select",
    description="Default question category for this server.",
    options=_WYR_CATEGORY_OPTIONS,
    get_values=WYRConfigActions.get_category_as_list,
    set_values=lambda gid, vals: WYRConfigActions.set_category(gid, vals[0]),
    is_customized=_value_diverges(WYRConfigActions.get_category_as_list, "sfw"),
    min_values=1,
    max_values=1,
)

WYR_THREAD_CONFIG = PanelNode(
    key="wyr_thread",
    label="WYR Thread Settings",
    kind="menu",
    description="Configure discussion threads created with each WYR post.",
    default_summary="Using defaults",
    children={
        "wyr_thread_format": PanelNode(
            key="wyr_thread_format",
            label="Thread Name & Message",
            kind="dual_modal_input",
            description=(
                "Thread name is capped at 100 characters after substitution.\n"
                "**Placeholders:** `{date}` (MM/DD) · `{question_num}` · `{category}` · "
                "`{option_1}` · `{option_2}` · `{option_3}` · `{question}`"
            ),
            modal_title="Thread Name & Starter Message",
            modal_label="Thread Name Format",
            modal_placeholder="e.g., 🎲 WYR · Q{question_num} · {date}",
            modal_min_length=1,
            modal_max_length=100,
            modal_label_2="Starter Message",
            modal_placeholder_2="e.g., 🎲 **{question}**\n\n1️⃣ {option_1}\n2️⃣ {option_2}",
            modal_min_length_2=0,
            modal_max_length_2=500,
            get_values=WYRConfigActions.get_thread_format_and_message,
            set_values=WYRConfigActions.set_thread_format_and_message,
        ),
        "wyr_thread_archive": PanelNode(
            key="wyr_thread_archive",
            label="Auto-Archive Duration",
            kind="option_select",
            description="How long before discussion threads auto-archive.",
            options=_WYR_ARCHIVE_OPTIONS,
            get_values=WYRConfigActions.get_thread_auto_archive,
            set_values=WYRConfigActions.set_thread_auto_archive,
            is_customized=_value_diverges(WYRConfigActions.get_thread_auto_archive, "1440"),
            min_values=1,
            max_values=1,
        ),
    },
)

WYR_CLEANUP_CONFIG = PanelNode(
    key="wyr_cleanup",
    label="WYR Cleanup",
    kind="option_select",
    description="Days before old message-question mappings are cleaned up.",
    options=_WYR_CLEANUP_OPTIONS,
    get_values=WYRConfigActions.get_cleanup_days_as_list,
    set_values=lambda gid, vals: WYRConfigActions.set_cleanup_days(gid, int(vals[0])),
    is_customized=_value_diverges(WYRConfigActions.get_cleanup_days_as_list, "30"),
    min_values=1,
    max_values=1,
)


# ── Drops PanelNode configs ──────────────────────────────────────────────────

DROPS_SCHEDULE_CONFIG = PanelNode(
    key="drops_schedule",
    label="Drops Schedule",
    kind="menu",
    description="Configure when daily Prime Gaming drops post. Each field autosaves independently.",
    default_summary="Using defaults",
    children={
        "drops_hour": PanelNode(
            key="drops_hour",
            label="Post Hour",
            kind="option_select",
            description="Hour of day for drops posts (24-hour clock, in selected timezone).",
            options=[(str(h), f"{h:02d}:00") for h in range(24)],
            get_values=DropsActions.get_schedule_hour,
            set_values=DropsActions.set_schedule_hour,
            is_customized=_value_diverges(DropsActions.get_schedule_hour, "6"),
            min_values=1,
            max_values=1,
        ),
        "drops_minute": PanelNode(
            key="drops_minute",
            label="Post Minute",
            kind="option_select",
            description="Minute offset for drops posts.",
            options=[("0", ":00"), ("15", ":15"), ("30", ":30"), ("45", ":45")],
            get_values=DropsActions.get_schedule_minute,
            set_values=DropsActions.set_schedule_minute,
            is_customized=_value_diverges(DropsActions.get_schedule_minute, "30"),
            min_values=1,
            max_values=1,
        ),
        "drops_timezone": PanelNode(
            key="drops_timezone",
            label="Timezone",
            kind="option_select",
            description="Timezone used when interpreting the post hour/minute.",
            options=_WYR_TIMEZONE_OPTIONS,
            get_values=DropsActions.get_schedule_timezone,
            set_values=DropsActions.set_schedule_timezone,
            is_customized=_value_diverges(DropsActions.get_schedule_timezone, "America/Chicago"),
            min_values=1,
            max_values=1,
        ),
    },
)


# ── New Members ───────────────────────────────────────────────────────────────

_NM_ACCOUNT_AGE_OPTIONS = [
    ("30", "30 Days"),
    ("60", "60 Days"),
    ("90", "90 Days"),
    ("120", "120 Days"),
    ("180", "180 Days"),
]

_NM_TOGGLE_OPTIONS = [("true", "Enabled"), ("false", "Disabled")]

NM_WELCOME_CHANNEL_CONFIG = PanelNode(
    key="nm_welcome_channel",
    label="Welcome Channel",
    kind="channel_select",
    description="Channel where welcome messages are sent when new members join.",
    get_values=NewMemberActions.get_welcome_channel_as_list,
    set_values=NewMemberActions.set_welcome_channel_from_list,
    clear_values=NewMemberActions.clear_welcome_channel,
    min_values=1,
    max_values=1,
)

NM_WELCOME_TEXT_CONFIG = PanelNode(
    key="nm_welcome_builder",
    label="Welcome Message Builder",
    kind="file_upload",
    description=(
        "Upload a JSON file to define a fully custom welcome message layout.\n\n"
        "**To upload:** Click **Upload JSON** below and attach a `.json` file.\n"
        "**To get the template:** Click **Download Template** for a ready-to-edit example.\n\n"
        "**Placeholders:** `{member}` · `{member_name}` · `{member_count}` · `{guild_name}` · `{voice_active}` · `{random_greeting}` (random themed greeting)\n\n"
        "Use **Clear** below to remove the custom layout. "
        "If no layout is configured, welcome messages will be skipped."
    ),
    get_values=NewMemberActions.get_welcome_components_raw,
    set_values=NewMemberActions.set_welcome_components_from_list,
    clear_values=NewMemberActions.clear_welcome_components,
    schema_validator=validate_welcome_schema,
    template_data=_welcome_template_data,
)

NM_SETTINGS_CONFIG = PanelNode(
    key="nm_settings",
    label="General Settings",
    kind="menu",
    description="Account age requirement, auto-kick, and system feature toggles.",
    default_summary="Using defaults",
    children={
        "nm_enabled": PanelNode(
            key="nm_enabled",
            label="New Members Processing",
            kind="option_select",
            description="Master toggle — enable or disable all new-member processing (screening, welcome messages, whitelist).",
            options=_NM_TOGGLE_OPTIONS,
            get_values=NewMemberActions.get_enabled_as_list,
            set_values=NewMemberActions.set_enabled_from_list,
            is_customized=_value_diverges(NewMemberActions.get_enabled_as_list, "false"),
            min_values=1,
            max_values=1,
        ),
        "nm_account_age": PanelNode(
            key="nm_account_age",
            label="Account Age Requirement",
            kind="option_select",
            description="Minimum account age (in days) required to pass the new-member check.",
            options=_NM_ACCOUNT_AGE_OPTIONS,
            get_values=NewMemberActions.get_account_age_as_list,
            set_values=NewMemberActions.set_account_age_from_list,
            is_customized=_value_diverges(NewMemberActions.get_account_age_as_list, "90"),
            min_values=1,
            max_values=1,
        ),
        "nm_auto_kick": PanelNode(
            key="nm_auto_kick",
            label="Auto-Kick",
            kind="option_select",
            description="Automatically kick accounts that don't meet the age requirement.",
            options=_NM_TOGGLE_OPTIONS,
            get_values=NewMemberActions.get_auto_kick_as_list,
            set_values=NewMemberActions.set_auto_kick_from_list,
            is_customized=_value_diverges(NewMemberActions.get_auto_kick_as_list, "true"),
            min_values=1,
            max_values=1,
        ),
        "nm_welcome_msg": PanelNode(
            key="nm_welcome_msg",
            label="Welcome Messages",
            kind="option_select",
            description="Send a welcome message when a new member successfully joins.",
            options=_NM_TOGGLE_OPTIONS,
            get_values=NewMemberActions.get_welcome_enabled_as_list,
            set_values=NewMemberActions.set_welcome_enabled_from_list,
            is_customized=_value_diverges(NewMemberActions.get_welcome_enabled_as_list, "true"),
            min_values=1,
            max_values=1,
        ),
        "nm_whitelist_system": PanelNode(
            key="nm_whitelist_system",
            label="Whitelist System",
            kind="option_select",
            description="Enable the whitelist role assignment system for new members.",
            options=_NM_TOGGLE_OPTIONS,
            get_values=NewMemberActions.get_whitelist_system_as_list,
            set_values=NewMemberActions.set_whitelist_system_from_list,
            is_customized=_value_diverges(NewMemberActions.get_whitelist_system_as_list, "true"),
            min_values=1,
            max_values=1,
        ),
    },
)

NM_WHITELIST_ROLE_CONFIG = PanelNode(
    key="nm_whitelist_role",
    label="Whitelist Role",
    kind="role_select",
    description="Role assigned to new members added to the whitelist.",
    get_values=NewMemberActions.get_whitelist_role_as_list,
    set_values=NewMemberActions.set_whitelist_role_from_list,
    clear_values=NewMemberActions.clear_whitelist_role,
    min_values=1,
    max_values=1,
)


# ── Announcements ────────────────────────────────────────────────────────────

_ANN_TOGGLE_OPTIONS = [("true", "Enabled"), ("false", "Disabled")]

_ANN_ARCHIVE_OPTIONS = [
    ("60", "1 Hour"),
    ("1440", "1 Day"),
    ("4320", "3 Days"),
    ("10080", "1 Week"),
]

ANN_CHANNEL_CONFIG = PanelNode(
    key="ann_channel",
    label="Announcement Channel",
    kind="channel_select",
    description="Select the channel where announcements are posted. Threads will be auto-created on new messages in this channel.",
    get_values=AnnouncementActions.get_announcement_channel_as_list,
    set_values=lambda guild_id, ids: AnnouncementActions.set_announcement_channel(guild_id, int(ids[0])),
    clear_values=AnnouncementActions.clear_announcement_channel,
    min_values=1,
    max_values=1,
)

ANN_SETTINGS_CONFIG = PanelNode(
    key="ann_settings",
    label="Thread Settings",
    kind="menu",
    description="Configure how discussion threads are created on announcements.",
    default_summary="Using defaults",
    children={
        "ann_thread_auto_create": PanelNode(
            key="ann_thread_auto_create",
            label="Thread Auto-Create",
            kind="option_select",
            description="Automatically create a discussion thread for each new announcement.",
            options=_ANN_TOGGLE_OPTIONS,
            get_values=AnnouncementActions.get_thread_auto_create_as_list,
            set_values=AnnouncementActions.set_thread_auto_create_from_list,
            is_customized=_value_diverges(AnnouncementActions.get_thread_auto_create_as_list, "true"),
            min_values=1,
            max_values=1,
        ),
        "ann_thread_name_format": PanelNode(
            key="ann_thread_name_format",
            label="Thread Name Format",
            kind="modal_input",
            description=(
                "Format string for auto-created thread names.\n"
                "**Placeholders:** `{message_content}` · `{author_name}` · `{channel_name}`"
            ),
            modal_title="Thread Name Format",
            modal_label="Name Format",
            modal_placeholder="e.g., 💬 {message_content}",
            modal_min_length=1,
            modal_max_length=100,
            get_values=AnnouncementActions.get_thread_name_format_as_list,
            set_values=AnnouncementActions.set_thread_name_format,
            is_customized=_value_diverges(
                AnnouncementActions.get_thread_name_format_as_list,
                "💬 {message_content}",
            ),
        ),
        "ann_thread_archive": PanelNode(
            key="ann_thread_archive",
            label="Auto-Archive Duration",
            kind="option_select",
            description="How long before discussion threads auto-archive.",
            options=_ANN_ARCHIVE_OPTIONS,
            get_values=AnnouncementActions.get_thread_auto_archive_as_list,
            set_values=AnnouncementActions.set_thread_auto_archive_from_list,
            is_customized=_value_diverges(AnnouncementActions.get_thread_auto_archive_as_list, "1440"),
            min_values=1,
            max_values=1,
        ),
        "ann_thread_welcome": PanelNode(
            key="ann_thread_welcome",
            label="Thread Welcome Message",
            kind="modal_input",
            description="Message posted as the first message in each auto-created thread.",
            modal_title="Thread Welcome Message",
            modal_label="Welcome Message",
            modal_placeholder="e.g., 💬 **Discussion Thread**\n\nDiscuss this announcement here!",
            modal_min_length=1,
            modal_max_length=500,
            modal_paragraph=True,
            get_values=AnnouncementActions.get_thread_welcome_message_as_list,
            set_values=AnnouncementActions.set_thread_welcome_message,
            is_customized=_value_diverges(
                AnnouncementActions.get_thread_welcome_message_as_list,
                "💬 **Discussion Thread**\n\nDiscuss this announcement here!",
            ),
        ),
        "ann_auto_delete": PanelNode(
            key="ann_auto_delete",
            label="Auto-Delete Threads",
            kind="option_select",
            description="Automatically delete discussion threads when the announcement is deleted.",
            options=_ANN_TOGGLE_OPTIONS,
            get_values=AnnouncementActions.get_auto_delete_threads_as_list,
            set_values=AnnouncementActions.set_auto_delete_threads_from_list,
            is_customized=_value_diverges(AnnouncementActions.get_auto_delete_threads_as_list, "true"),
            min_values=1,
            max_values=1,
        ),
    },
)


# ── Suggestions ──────────────────────────────────────────────────────────────

SUG_CHANNEL_CONFIG = PanelNode(
    key="sug_channel",
    label="Suggestion Channel",
    kind="channel_select",
    description="Select the channel where user suggestions will be posted.",
    get_values=SuggestionActions.get_suggestion_channel_as_list,
    set_values=lambda guild_id, ids: SuggestionActions.set_suggestion_channel(guild_id, int(ids[0])),
    clear_values=SuggestionActions.clear_suggestion_channel,
    min_values=1,
    max_values=1,
)


# ── Guide ────────────────────────────────────────────────────────────────────

_GUIDE_TOGGLE_OPTIONS = [("true", "Enabled"), ("false", "Disabled")]

GUIDE_CHANNEL_CONFIG = PanelNode(
    key="guide_channel",
    label="Guide Channel",
    kind="channel_select",
    description="Optional: restrict the guide to a specific channel. Leave empty to allow guide anywhere.",
    get_values=GuideActions.get_guide_channel_as_list,
    set_values=lambda guild_id, ids: GuideActions.set_guide_channel(guild_id, int(ids[0])),
    clear_values=GuideActions.clear_guide_channel,
    min_values=1,
    max_values=1,
)

GUIDE_UPLOAD_CONFIG = PanelNode(
    key="guide_upload",
    label="Guide JSON Builder",
    kind="file_upload",
    description=(
        "Upload a JSON file to define a custom guide with pages, navigation, and rich content.\n\n"
        "**To upload:** Click **Upload JSON** below and attach a `.json` file.\n"
        "**To get the template:** Click **Download Template** for a ready-to-edit example.\n\n"
        "Use **Clear** below to remove the custom guide and revert to the default template."
    ),
    get_values=GuideActions.get_guide_json_raw,
    set_values=GuideActions.set_guide_json_from_list,
    clear_values=GuideActions.clear_guide_json,
    schema_validator=validate_guide_schema,
    template_data=_guide_template_data,
)

GUIDE_ENABLED_CONFIG = PanelNode(
    key="guide_enabled",
    label="Guide Enabled",
    kind="option_select",
    description="Master toggle — enable or disable the guide system.",
    options=_GUIDE_TOGGLE_OPTIONS,
    get_values=GuideActions.get_enabled_as_list,
    set_values=GuideActions.set_enabled_from_list,
    is_customized=_value_diverges(GuideActions.get_enabled_as_list, "true"),
    min_values=1,
    max_values=1,
)


# ── Panel Access (admin/mod role) get_values for dashboard summary ───────────

async def _get_panel_role(guild_id: int, role_field: str) -> list:
    cm = await get_config_manager()
    cfg = await cm.get_config(guild_id)
    return [int(r) for r in (cfg.roles.get(role_field) or [])]


async def _set_panel_role(guild_id: int, ids: list, role_field: str) -> bool:
    cm = await get_config_manager()
    cfg = await cm.get_config(guild_id)
    cfg.roles[role_field] = [int(r) for r in ids]
    return await cm.save_config(cfg)


async def _clear_panel_role(guild_id: int, role_field: str) -> bool:
    cm = await get_config_manager()
    cfg = await cm.get_config(guild_id)
    cfg.roles[role_field] = []
    return await cm.save_config(cfg)


ADMIN_ROLES_CONFIG = PanelNode(
    key="admin_roles",
    label="Panel Access Roles",
    kind="role_select",
    description=(
        "Grants full admin panel access (same as Manage Server). "
        "Members holding any of these roles can open `/admin panel`."
    ),
    get_values=lambda gid: _get_panel_role(gid, "admin_role_ids"),
    set_values=lambda gid, ids: _set_panel_role(gid, ids, "admin_role_ids"),
    clear_values=lambda gid: _clear_panel_role(gid, "admin_role_ids"),
    min_values=0,
    max_values=10,
)

MOD_ROLES_CONFIG = PanelNode(
    key="mod_roles",
    label="Mod Access Roles",
    kind="role_select",
    description=(
        "Optional — grants limited (mod-tier) panel access to sections opted in "
        "by your admins. Leave blank to disable the Mod tier."
    ),
    get_values=lambda gid: _get_panel_role(gid, "mod_role_ids"),
    set_values=lambda gid, ids: _set_panel_role(gid, ids, "mod_role_ids"),
    clear_values=lambda gid: _clear_panel_role(gid, "mod_role_ids"),
    min_values=0,
    max_values=10,
)


# ── Status / bespoke stubs (handler-driven; dashboard summary only) ──────────
#
# These subcategories dispatch to bespoke `_show_*` handlers in admin_cog
# rather than the engine's _navigate_to. They appear here so the dashboard
# tree can list them with a label, description, and lock state. Kind="menu"
# with no children → dashboard renders "Not configured".

def _stub(key: str, label: str, description: str = "") -> PanelNode:
    return PanelNode(key=key, label=label, kind="menu", description=description)


def _view_stub(key: str, label: str, description: str = "") -> PanelNode:
    """Read-only "View Status" entry — surfaces as 'View only' in parent menus
    so it never reports a misleading 'Not configured'."""
    return PanelNode(
        key=key, label=label, kind="menu", description=description, view_only=True,
    )



async def _color_tiers_summary_values(guild_id: int) -> list:
    """Return a non-empty marker list when Color Tiers is configured.

    Considered configured if a server default color is set OR any color sets exist.
    """
    out: list = []
    try:
        default_color = await ColorSetActions.get_default_color(guild_id)
        if default_color is not None:
            out.append("default_color")
    except Exception:
        pass
    try:
        sets = await ColorSetActions.list_color_sets(guild_id)
        if sets:
            out.append(f"sets:{len(sets)}")
    except Exception:
        pass
    return out


EMBED_STATUS_STUB = _view_stub("status", "View Status", "View embed configuration summary.")
COLOR_TIERS_STUB = PanelNode(
    key="color_tiers",
    label="Color Tiers",
    kind="menu",
    description="Manage per-guild color palettes.",
    get_values=_color_tiers_summary_values,
)
WYR_STATUS_STUB = _view_stub("wyr_status", "WYR Status", "View WYR configuration summary.")
NM_STATUS_STUB = _view_stub("nm_status", "View Status", "View new members system status.")
TAG_TRACKER_STUB = _stub("tag_tracker", "Tag Tracker", "Configure server tag tracking.")
BOOST_TRACKER_STUB = _stub("boost_tracker", "Boost Tracker", "Configure boost log channel.")
TRACKER_STATUS_STUB = _view_stub("tracker_status", "View Status", "View tracker configuration summary.")
DROPS_CHANNEL_STUB = _stub("drops_channel", "Drops Channel", "Channel for daily Prime Gaming drops.")
DROPS_TRACKER_STUB = _stub("drops_tracker", "Tracked Channels", "Channels tracked for stats.")
DROPS_MANAGER_STUB = _stub("drops_manager_role", "Manager Role", "Role allowed to manage drops via /drop.")
DROPS_STATUS_STUB = _view_stub("drops_status", "View Status", "View drops configuration and stats.")
ANN_STATUS_STUB = _view_stub("ann_status", "View Status", "View announcement configuration summary.")
SUG_UPDATE_STUB = _stub("sug_update_status", "Update Status", "Update a suggestion's review status.")
SUG_EXPORT_STUB = _stub("sug_export", "Export", "Export suggestions as CSV or JSON.")
SUG_STATUS_STUB = _view_stub("sug_status", "View Status", "View suggestion system stats.")
GUIDE_STATUS_STUB = _view_stub("guide_status", "View Status", "View guide system configuration.")


# ── MAIN_PANEL tree (Message 1 dashboard) ────────────────────────────────────
#
# Two-level tree per ADMIN_PANEL_STANDARD.md §1/§7:
#   MAIN_PANEL.children = group menus (panel_access, embed_settings, ...)
#   group.children      = subcategory entries (handler dispatch via admin_cog)
#
# `category_group="main"` renders above the "── Feature Configurations ──"
# divider in the dashboard Select; "feature" renders below.

_PANEL_ACCESS_GROUP = PanelNode(
    key="panel_access",
    label="Role Configuration",
    kind="menu",
    description="Delegate admin panel access to server roles.",
    category_group="main",
    children={
        "admin_roles": ADMIN_ROLES_CONFIG,
        "mod_roles": MOD_ROLES_CONFIG,
    },
)

_EMBED_SETTINGS_GROUP = PanelNode(
    key="embed_settings",
    label="Embed Settings",
    kind="menu",
    description="Configure embed colors, tiers, limits, and features.",
    category_group="feature",
    children={
        "role_tiers": ROLE_TIER_CONFIG,
        "description_limits": DESCRIPTION_LIMITS_CONFIG,
        "color_tiers": COLOR_TIERS_STUB,
        "feature_access": FEATURE_ACCESS_CONFIG,
        "status": EMBED_STATUS_STUB,
    },
)

_WYR_SETTINGS_GROUP = PanelNode(
    key="wyr_settings",
    label="WYR Settings",
    kind="menu",
    description="Configure Would You Rather scheduling and behavior.",
    category_group="feature",
    children={
        "wyr_channel": WYR_CHANNEL_CONFIG,
        "wyr_ping_role": WYR_PING_ROLE_CONFIG,
        "wyr_schedule": WYR_SCHEDULE_CONFIG,
        "wyr_category": WYR_CATEGORY_CONFIG,
        "wyr_thread": WYR_THREAD_CONFIG,
        "wyr_cleanup": WYR_CLEANUP_CONFIG,
        "wyr_status": WYR_STATUS_STUB,
    },
)

_NEW_MEMBERS_GROUP = PanelNode(
    key="new_members",
    label="New Members",
    kind="menu",
    description="Configure welcome messages, account age, and whitelist.",
    category_group="feature",
    children={
        "nm_welcome_channel": NM_WELCOME_CHANNEL_CONFIG,
        "nm_welcome_builder": NM_WELCOME_TEXT_CONFIG,
        "nm_settings": NM_SETTINGS_CONFIG,
        "nm_whitelist_role": NM_WHITELIST_ROLE_CONFIG,
        "nm_status": NM_STATUS_STUB,
    },
)

_TRACKERS_GROUP = PanelNode(
    key="trackers",
    label="Trackers",
    kind="menu",
    description="Configure boost tracker and tag tracker.",
    category_group="feature",
    children={
        "tag_tracker": TAG_TRACKER_STUB,
        "boost_tracker": BOOST_TRACKER_STUB,
        "tracker_status": TRACKER_STATUS_STUB,
    },
)

_UPDATES_DROPS_GROUP = PanelNode(
    key="updates_drops",
    label="Updates & Drops",
    kind="menu",
    description="Configure drops channel and tracked channels.",
    category_group="feature",
    children={
        "drops_channel": DROPS_CHANNEL_STUB,
        "drops_schedule": DROPS_SCHEDULE_CONFIG,
        "drops_tracker": DROPS_TRACKER_STUB,
        "drops_manager_role": DROPS_MANAGER_STUB,
        "drops_status": DROPS_STATUS_STUB,
    },
)

_ANNOUNCEMENTS_GROUP = PanelNode(
    key="announcements",
    label="Announcements",
    kind="menu",
    description="Configure announcement thread auto-creation.",
    category_group="feature",
    children={
        "ann_channel": ANN_CHANNEL_CONFIG,
        "ann_settings": ANN_SETTINGS_CONFIG,
        "ann_status": ANN_STATUS_STUB,
    },
)

_SUGGESTIONS_GROUP = PanelNode(
    key="suggestions",
    label="Suggestions",
    kind="menu",
    description="Configure suggestion channel and view stats.",
    category_group="feature",
    children={
        "sug_channel": SUG_CHANNEL_CONFIG,
        "sug_update_status": SUG_UPDATE_STUB,
        "sug_export": SUG_EXPORT_STUB,
        "sug_status": SUG_STATUS_STUB,
    },
)

_GUIDE_SETTINGS_GROUP = PanelNode(
    key="guide_settings",
    label="Guide",
    kind="menu",
    description="Configure the server guide system.",
    category_group="feature",
    children={
        "guide_channel": GUIDE_CHANNEL_CONFIG,
        "guide_upload": GUIDE_UPLOAD_CONFIG,
        "guide_enabled": GUIDE_ENABLED_CONFIG,
        "guide_status": GUIDE_STATUS_STUB,
    },
)


MAIN_PANEL = PanelNode(
    key="main",
    label=PANEL_TITLE,
    kind="menu",
    description=PANEL_DESCRIPTION,
    children={
        # Main Configurations (per §7 hierarchy)
        "panel_access": _PANEL_ACCESS_GROUP,
        # Feature Configurations
        "embed_settings": _EMBED_SETTINGS_GROUP,
        "wyr_settings": _WYR_SETTINGS_GROUP,
        "new_members": _NEW_MEMBERS_GROUP,
        "trackers": _TRACKERS_GROUP,
        "updates_drops": _UPDATES_DROPS_GROUP,
        "announcements": _ANNOUNCEMENTS_GROUP,
        "suggestions": _SUGGESTIONS_GROUP,
        "guide_settings": _GUIDE_SETTINGS_GROUP,
    },
)
