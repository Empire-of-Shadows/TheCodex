"""
Admin Commands Cog - Embed Configuration Panel

Main cog with /admin panel command using Discord Components v2 LayoutViews.
Provides admin management for embed configuration (color tiers, role mappings,
description limits, feature access).
"""

import json
import time
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import get_logger

from .actions import EmbedConfigActions, WYRConfigActions, NewMemberActions, TrackerActions, DropsActions, ColorSetActions, AnnouncementActions, SuggestionActions
from .actions.guide_actions import GuideActions
from .permission_checks import check_channel_permissions, check_role_permissions
from .role_auth import get_panel_role, MOD_ALLOWED_SECTIONS
from storage.audit_log import get_audit_logger
from storage.config_manager import get_config_manager
from .views.panel_engine import _child_summary
from .views import (
    attach_timeout_expiry,
    attach_timeout_expiry_msg,
    PanelSession,
    cid,
    build_notice_layout,
    build_premium_layout,
    build_overview_view,
    DASHBOARD_FEATURE_SEPARATOR_VALUE,
    build_embed_status_view,
    TIER_NAMES,
    TIER_LABELS,
    create_empty_layout,
    build_default_color_setup_view,
    build_color_sets_menu,
    build_color_set_detail,
    build_role_assign_view,
    build_tier_assign_view,
    build_delete_confirm_view,
    DefaultColorModal,
    ColorSetCreateModal,
    ColorAddModal,
    build_wyr_status_view,
    build_wyr_ping_role_view,
    WyrCreateRoleModal,
    build_new_member_status_view,
    build_nm_whitelist_role_view,
    NmCreateRoleModal,
    build_nm_welcome_channel_view,
    NmCreateChannelModal,
    build_tag_tracker_settings_view,
    TagTrackerServerTagModal,
    build_boost_tracker_settings_view,
    build_tracker_status_view,
    build_drops_channel_view,
    build_drops_tracker_view,
    build_drops_status_view,
    build_announcement_status_view,
    build_suggestion_status_view,
    SuggestionStatusUpdateModal,
    build_suggestion_export_view,
    PanelNode,
    build_menu_view,
    build_select_view,
    build_modal_trigger_view,
    build_dual_modal_trigger_view,
    build_file_upload_status_view,
    PanelInputModal,
    PanelFileUploadModal,
)
from Features.ce_utilities.color_normalizer import normalize_color, parse_named_colors_string, color_int_to_hex
from Features.ce_utilities.conflict_detector import check_color_uniqueness, check_tier_exclusivity
from .panel_configs import (
    ROLE_TIER_CONFIG, FEATURE_ACCESS_CONFIG, DESCRIPTION_LIMITS_CONFIG,
    WYR_CHANNEL_CONFIG, WYR_SCHEDULE_CONFIG,
    WYR_CATEGORY_CONFIG, WYR_THREAD_CONFIG, WYR_CLEANUP_CONFIG,
    NM_SETTINGS_CONFIG, NM_WELCOME_CHANNEL_CONFIG, NM_WHITELIST_ROLE_CONFIG,
    NM_WELCOME_TEXT_CONFIG,
    ANN_CHANNEL_CONFIG, ANN_SETTINGS_CONFIG, SUG_CHANNEL_CONFIG,
    GUIDE_CHANNEL_CONFIG, GUIDE_UPLOAD_CONFIG, GUIDE_ENABLED_CONFIG,
    DROPS_SCHEDULE_CONFIG,
    ADMIN_ROLES_CONFIG, MOD_ROLES_CONFIG, _PANEL_ACCESS_GROUP,
    MAIN_PANEL,
    _auto_enable_feature_if_ready,
)
from .panel_branding import SETUP_GUIDE_TEXT, OVERVIEW_FOOTER
from storage.setup_gatekeeper import setup_gatekeeper

logger = get_logger("AdminCog")

class AdminCog(commands.Cog):
    """
    Administrative commands for managing embed configuration.
    Uses Discord Components v2 LayoutViews for all UI.
    """

    AUTOSAVE_COOLDOWN = 2.0  # seconds between autosaves per (user, node_key)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._autosave_cooldowns: dict[tuple, float] = {}
        logger.info("AdminCog initialized with embed config panel")

    # ==================== Command Groups ====================

    admin_group = app_commands.Group(
        name="admin",
        description="Admin commands for managing embed configuration",
    )

    # ==================== Master Admin Panel ====================

    # Subcategory keys that require prerequisite setup before unlocking.
    _EMBED_GATED_KEYS = {"description_limits", "color_tiers", "feature_access", "status"}
    _WYR_GATED_KEYS = {"wyr_ping_role", "wyr_schedule", "wyr_category", "wyr_thread", "wyr_cleanup"}
    _NM_GATED_KEYS = {"nm_welcome_builder", "nm_settings", "nm_whitelist_role"}

    # Engine-driven subcategories: sub_key → PanelNode. Dispatched directly via
    # _navigate_to(parent_node=group_node, edit=True) so msg2 is edited in
    # place and the engine's built-in Back button returns to the group menu
    # (per ADMIN_PANEL_STANDARD.md §1). Bespoke handlers (custom views with
    # Create Role / Create Channel buttons, status views, color sets,
    # trackers, drops, suggestion update/export) stay in the handlers dict
    # and are converted to edit msg2 separately.
    _ENGINE_SUBCATEGORIES: dict[str, PanelNode] = {
        "admin_roles": ADMIN_ROLES_CONFIG,
        "mod_roles": MOD_ROLES_CONFIG,
        "role_tiers": ROLE_TIER_CONFIG,
        "description_limits": DESCRIPTION_LIMITS_CONFIG,
        "feature_access": FEATURE_ACCESS_CONFIG,
        "wyr_channel": WYR_CHANNEL_CONFIG,
        "wyr_schedule": WYR_SCHEDULE_CONFIG,
        "wyr_category": WYR_CATEGORY_CONFIG,
        "wyr_thread": WYR_THREAD_CONFIG,
        "wyr_cleanup": WYR_CLEANUP_CONFIG,
        "nm_settings": NM_SETTINGS_CONFIG,
        "nm_welcome_builder": NM_WELCOME_TEXT_CONFIG,
        "ann_channel": ANN_CHANNEL_CONFIG,
        "ann_settings": ANN_SETTINGS_CONFIG,
        "sug_channel": SUG_CHANNEL_CONFIG,
        "guide_channel": GUIDE_CHANNEL_CONFIG,
        "guide_upload": GUIDE_UPLOAD_CONFIG,
        "guide_enabled": GUIDE_ENABLED_CONFIG,
        "drops_schedule": DROPS_SCHEDULE_CONFIG,
    }

    @admin_group.command(name="panel", description="Open the admin configuration panel")
    async def admin_panel(self, interaction: discord.Interaction):
        """Open the admin configuration panel (three-message flow).

        Message 1 is the persistent overview built from MAIN_PANEL with two
        toggle buttons (Setup Guide, Config Details). Selecting a category
        spawns Message 2 as an ephemeral followup listing the subcategories
        of that group; selecting a subcategory dispatches to the bespoke
        `_show_*` handlers via `_SUBCATEGORY_HANDLERS`.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True,
            )
            return

        guild = interaction.guild
        admin_user = interaction.user
        admin_id = admin_user.id

        cm = await get_config_manager()
        cfg = await cm.get_config(guild.id)
        panel_role = get_panel_role(admin_user, cfg)
        if panel_role == "none":
            await interaction.response.send_message(
                "You do not have permission to use the admin panel. "
                "Requires **Manage Server**, the configured Admin role, "
                "or the configured Mod role.",
                ephemeral=True,
            )
            return

        logger.info(
            f"Admin panel opened by {admin_user} in guild {guild.id} (role={panel_role})"
        )

        # Persisted across sessions; details is session-local.
        guide_hidden = bool(await cm.get_setting("hide_setup_guide", guild.id, default=False))
        guide_state = {"hidden": guide_hidden}
        details_state = {"expanded": False}

        session = PanelSession(interaction)

        async def on_toggle_guide(toggle_interaction: discord.Interaction):
            if toggle_interaction.user.id != admin_id:
                await toggle_interaction.response.send_message(
                    view=build_notice_layout(
                        "Access Denied",
                        "Only the admin who opened this panel can interact with it.",
                    ),
                    ephemeral=True,
                )
                return
            if not self._check_cooldown(admin_id, "setup_guide_toggle"):
                await toggle_interaction.response.send_message(
                    view=build_notice_layout("Slow Down", "Please wait a moment before toggling again."),
                    ephemeral=True,
                )
                return
            guide_state["hidden"] = not guide_state["hidden"]
            try:
                await cm.set_setting("hide_setup_guide", guide_state["hidden"], guild.id)
            except Exception as e:
                logger.debug(f"Could not persist hide_setup_guide: {e}")
            layout = await _build_overview()
            await toggle_interaction.response.edit_message(view=layout)

        async def on_toggle_details(toggle_interaction: discord.Interaction):
            if toggle_interaction.user.id != admin_id:
                await toggle_interaction.response.send_message(
                    view=build_notice_layout(
                        "Access Denied",
                        "Only the admin who opened this panel can interact with it.",
                    ),
                    ephemeral=True,
                )
                return
            if not self._check_cooldown(admin_id, "details_toggle"):
                await toggle_interaction.response.send_message(
                    view=build_notice_layout("Slow Down", "Please wait a moment before toggling again."),
                    ephemeral=True,
                )
                return
            details_state["expanded"] = not details_state["expanded"]
            layout = await _build_overview()
            await toggle_interaction.response.edit_message(view=layout)

        async def on_main_select(sel_interaction: discord.Interaction, group_key: str):
            if sel_interaction.user.id != admin_id:
                await sel_interaction.response.send_message(
                    view=build_notice_layout(
                        "Access Denied",
                        "Only the admin who opened this panel can interact with it.",
                    ),
                    ephemeral=True,
                )
                return
            group_node = MAIN_PANEL.children.get(group_key)
            if not group_node:
                return

            # Mod-tier groups are accessible only if at least one of their
            # subcategories is in MOD_ALLOWED_SECTIONS.
            if panel_role == "mod":
                allowed = {k for k in group_node.children if k in MOD_ALLOWED_SECTIONS}
                if not allowed:
                    refreshed = await _build_overview()
                    await sel_interaction.response.edit_message(view=refreshed)
                    await sel_interaction.followup.send(
                        view=build_notice_layout(
                            "Admin Only",
                            "This section is restricted to server admins.",
                        ),
                        ephemeral=True,
                    )
                    return

            # Close any prior msg2, then refresh msg1 (resets the Select) and
            # send the new group menu as Message 2.
            if session.msg2_message is not None:
                try:
                    await session.msg2_message.edit(
                        view=create_empty_layout(
                            "Setting closed. Use the overview above to continue."
                        )
                    )
                except Exception:
                    pass
                session.clear_msg2()

            try:
                refreshed = await _build_overview()
                await self._safe_edit_original(interaction,view=refreshed)
            except Exception as e:
                logger.debug(f"Could not refresh overview select state: {e}")

            await self._show_group_on_msg2(
                sel_interaction, group_node, guild, panel_role,
                _build_overview, session,
            )

        async def _build_overview() -> discord.ui.LayoutView:
            deep_summary = await self._gather_dashboard_summaries(MAIN_PANEL, guild.id)
            toggle_states = await self._gather_dashboard_toggles(MAIN_PANEL, guild.id)
            locked = await self._compute_dashboard_locks(MAIN_PANEL, guild.id, panel_role)

            preamble = None
            if not guide_state["hidden"]:
                preamble = [discord.ui.TextDisplay(SETUP_GUIDE_TEXT)]

            guide_btn = discord.ui.Button(
                label="Hide Setup Guide" if not guide_state["hidden"] else "Show Setup Guide",
                style=discord.ButtonStyle.secondary,
                custom_id=cid("dash", "toggle_guide"),
            )
            guide_btn.callback = on_toggle_guide

            details_btn = discord.ui.Button(
                label="Hide Config Details" if details_state["expanded"] else "Show Config Details",
                style=discord.ButtonStyle.secondary,
                custom_id=cid("dash", "toggle_details"),
            )
            details_btn.callback = on_toggle_details

            layout = build_overview_view(
                MAIN_PANEL, deep_summary, toggle_states, locked,
                on_main_select,
                preamble_items=preamble,
                extra_buttons=[guide_btn, details_btn],
                compact=not details_state["expanded"],
                footer_text=OVERVIEW_FOOTER or None,
            )
            session.register_view(layout)
            return layout

        layout = await _build_overview()
        await interaction.response.send_message(view=layout, ephemeral=True)
        session.touch()

    # ==================== Dashboard helpers ====================

    # Per-(admin_id, action_key) cooldown applied to UX-spammy actions
    # (e.g. dashboard toggle buttons). Distinct from AUTOSAVE_COOLDOWN.
    DASHBOARD_COOLDOWN = 1.0

    def _check_cooldown(self, admin_id: int, action: str) -> bool:
        """Return True if the cooldown for (admin_id, action) has elapsed."""
        key = (admin_id, action)
        now = time.monotonic()
        last = self._autosave_cooldowns.get(key, 0.0)
        if now - last < self.DASHBOARD_COOLDOWN:
            return False
        self._autosave_cooldowns[key] = now
        return True

    # Subcategory key → bound handler method on self.
    # Populated lazily on first access via `_get_subcategory_handlers`.
    _subcategory_handlers_cache: dict = None  # type: ignore[assignment]

    def _get_subcategory_handlers(self) -> dict:
        """Return bespoke subcategory handlers (engine routes go via _ENGINE_SUBCATEGORIES).

        Each handler is called with signature
        ``(interaction, *, parent_node, rebuild_group_view)`` so it can edit
        msg2 in place and provide a Back button that re-renders the group
        menu via ``rebuild_group_view()``.
        """
        if not getattr(self, "_subcategory_handlers_cache", None):
            self._subcategory_handlers_cache = {
                "color_tiers": self._show_color_sets_menu,
                "status": self._show_status,
                "wyr_ping_role": self._show_wyr_ping_role_menu,
                "wyr_status": self._show_wyr_status,
                "nm_welcome_channel": self._show_nm_welcome_channel_menu,
                "nm_whitelist_role": self._show_nm_whitelist_role_menu,
                "nm_status": self._show_nm_status,
                "tag_tracker": self._show_tag_tracker_menu,
                "boost_tracker": self._show_boost_tracker_menu,
                "tracker_status": self._show_tracker_status,
                "drops_channel": self._show_drops_channel_menu,
                "drops_tracker": self._show_drops_tracker_menu,
                "drops_manager_role": self._show_drops_manager_role_menu,
                "drops_status": self._show_drops_status,
                "ann_status": self._show_ann_status,
                "sug_update_status": self._show_sug_update_status,
                "sug_export": self._show_sug_export,
                "sug_status": self._show_sug_status,
                "guide_status": self._show_guide_status,
            }
        return self._subcategory_handlers_cache

    @staticmethod
    def _format_node_value(node: PanelNode, values: list) -> str:
        """Render the actual configured value of a leaf PanelNode for the
        dashboard's expanded **Show Config Details** view.

        Returns canonical empty strings ("Not set", "Not assigned",
        "Not configured") when no value is set, so
        `_compact_category_summary` keeps counting configured-vs-not correctly.
        """
        kind = node.kind
        if not values:
            if kind == "role_select":
                return "Not assigned"
            if kind == "channel_select":
                return "Not set"
            if kind == "file_upload":
                return "Default"
            return "Not set"

        if kind == "role_select":
            return ", ".join(f"<@&{int(r)}>" for r in values)
        if kind == "channel_select":
            return ", ".join(f"<#{int(c)}>" for c in values)
        if kind == "option_select":
            label_map: dict[str, str] = {}
            for opt in (node.options or []):
                label_map[str(opt[0])] = opt[1]
            names = [label_map.get(str(v), str(v)) for v in values]
            return ", ".join(names)
        if kind == "modal_input":
            return str(values[0])
        if kind == "dual_modal_input":
            return str(values[0]) if values[0] else "Not set"
        if kind == "file_upload":
            return "Custom JSON"
        return _child_summary(kind, values)

    async def _gather_node_summary_values(
        self, node: PanelNode, guild_id: int
    ) -> list:
        """Return a values list for a PanelNode usable by _child_summary.

        Status / view-only nodes always return [] so the parent menu can
        render a neutral "View only" label.

        Leaf nodes: prefer is_customized when supplied (so defaults-backed
        fields don't count as "configured"); otherwise fall back to
        get_values output.

        Menu nodes with grandchildren: returns one marker per "customized"
        grandchild so the parent menu can report "N of M customized" (when
        the menu declares default_summary) or "N of M configured".
        """
        if node.view_only:
            return []
        if node.is_customized is not None:
            try:
                return ["customized"] if await node.is_customized(guild_id) else []
            except Exception:
                return []
        if node.get_values:
            try:
                return list(await node.get_values(guild_id))
            except Exception:
                return []
        if node.kind == "menu" and node.children:
            configured: list = []
            for grand_key, grand in node.children.items():
                if grand.view_only:
                    continue
                if grand.is_customized is not None:
                    try:
                        if await grand.is_customized(guild_id):
                            configured.append(grand_key)
                    except Exception:
                        pass
                    continue
                if not grand.get_values:
                    continue
                try:
                    gv = list(await grand.get_values(guild_id))
                except Exception:
                    gv = []
                if gv:
                    configured.append(grand_key)
            return configured
        return []

    async def _gather_dashboard_summaries(
        self, root: PanelNode, guild_id: int
    ) -> dict[str, dict[str, str | dict[str, str]]]:
        """Return {group_key: {subcategory_key: summary | {grand_key: summary}}}.

        Leaf subcategories produce a formatted value string via
        `_format_node_value`. Subcategories that are themselves menus with
        children (e.g. WYR Schedule, Description Limits) produce a nested
        dict — `build_overview_view`'s expanded branch already iterates the
        nested form to render per-child bullet lines.
        """
        out: dict[str, dict[str, str | dict[str, str]]] = {}
        for group_key, group in root.children.items():
            inner: dict[str, str | dict[str, str]] = {}
            for sub_key, sub in group.children.items():
                if sub.view_only:
                    inner[sub_key] = "View only"
                    continue
                if sub.kind == "menu" and sub.children:
                    nested: dict[str, str] = {}
                    for grand_key, grand in sub.children.items():
                        if grand.view_only:
                            nested[grand_key] = "View only"
                            continue
                        if grand.is_customized is not None:
                            try:
                                if not await grand.is_customized(guild_id):
                                    nested[grand_key] = "Default"
                                    continue
                            except Exception as e:
                                logger.debug(f"is_customized failed for {grand_key}: {e}")
                        gvals: list = []
                        if grand.get_values:
                            try:
                                gvals = list(await grand.get_values(guild_id))
                            except Exception as e:
                                logger.debug(f"get_values failed for {grand_key}: {e}")
                        nested[grand_key] = self._format_node_value(grand, gvals)
                    inner[sub_key] = nested
                    continue
                if sub.is_customized is not None:
                    try:
                        if not await sub.is_customized(guild_id):
                            inner[sub_key] = "Default"
                            continue
                    except Exception as e:
                        logger.debug(f"is_customized failed for {sub_key}: {e}")
                values: list = []
                if sub.get_values:
                    try:
                        values = list(await sub.get_values(guild_id))
                    except Exception as e:
                        logger.debug(f"get_values failed for {sub_key}: {e}")
                inner[sub_key] = self._format_node_value(sub, values)
            out[group_key] = inner
        return out

    async def _gather_dashboard_toggles(
        self, root: PanelNode, guild_id: int
    ) -> dict[str, bool | None]:
        """Return {group_key: bool|None} for groups with a feature master toggle."""
        out: dict[str, bool | None] = {}
        for group_key in root.children:
            out[group_key] = None
        try:
            out["embed_settings"] = bool(await EmbedConfigActions.get_enabled(guild_id))
        except Exception:
            pass
        try:
            out["wyr_settings"] = bool(await WYRConfigActions.get_enabled(guild_id))
        except Exception:
            pass
        try:
            out["new_members"] = bool(await NewMemberActions.get_enabled(guild_id))
        except Exception:
            pass
        try:
            out["guide_settings"] = bool(await GuideActions.get_enabled(guild_id))
        except Exception:
            pass
        return out

    async def _compute_dashboard_locks(
        self, root: PanelNode, guild_id: int, panel_role: str,
    ) -> set[str]:
        """Return the set of group keys to mark locked at the dashboard level."""
        locked: set[str] = set()
        if panel_role == "mod":
            for group_key, group in root.children.items():
                if not any(k in MOD_ALLOWED_SECTIONS for k in group.children):
                    locked.add(group_key)
        return locked

    async def _compute_subcategory_locks(self, group_key: str, guild_id: int) -> set[str]:
        """Return the set of subcategory keys to mark locked inside a group menu."""
        if group_key == "embed_settings":
            if not await setup_gatekeeper.is_embed_setup_complete(guild_id):
                return set(self._EMBED_GATED_KEYS)
        elif group_key == "wyr_settings":
            if not await setup_gatekeeper.is_wyr_setup_complete(guild_id):
                return set(self._WYR_GATED_KEYS)
        elif group_key == "new_members":
            if not await setup_gatekeeper.is_new_members_setup_complete(guild_id):
                return set(self._NM_GATED_KEYS)
        return set()

    async def _show_group_on_msg2(
        self,
        sel_interaction: discord.Interaction,
        group_node: PanelNode,
        guild: discord.Guild,
        panel_role: str,
        build_overview: Callable[[], Awaitable[discord.ui.LayoutView]],
        session: PanelSession,
    ) -> None:
        """Send a new Message 2 (followup) listing the subcategories of a group.

        Subcategory selection dispatches to the bot's bespoke `_show_*`
        handlers via _SUBCATEGORY_HANDLERS, preserving the existing per-
        subcategory render logic (color sets, status views, modal flows).
        """
        admin_id = sel_interaction.user.id

        async def _gather_subcategory_summary() -> dict[str, list]:
            summary: dict[str, list] = {}
            for sub_key, sub in group_node.children.items():
                summary[sub_key] = await self._gather_node_summary_values(sub, guild.id)
            return summary

        summary_map = await _gather_subcategory_summary()
        locked_keys = await self._compute_subcategory_locks(group_node.key, guild.id)
        current_locked = [locked_keys]

        async def refresh_nav() -> None:
            """Update Message 1 dashboard after an inner save."""
            try:
                refreshed = await build_overview()
                await session.original_interaction.edit_original_response(view=refreshed)
            except Exception as e:
                logger.debug(f"Could not refresh dashboard after save: {e}")

        async def _build_current_view() -> discord.ui.LayoutView:
            new_summary = await _gather_subcategory_summary()
            new_locked = await self._compute_subcategory_locks(group_node.key, guild.id)
            current_locked[0] = new_locked
            layout = build_menu_view(
                group_node, new_summary, on_sub_select, on_back,
            )
            # Register so the shared session timer resets on every group-menu
            # interaction (after a bespoke handler has navigated away and back).
            session.register_view(layout)
            return layout

        async def on_sub_select(child_interaction: discord.Interaction, sub_key: str):
            if child_interaction.user.id != admin_id:
                await child_interaction.response.send_message(
                    view=build_notice_layout(
                        "Access Denied",
                        "Only the admin who opened this panel can interact with it.",
                    ),
                    ephemeral=True,
                )
                return

            # Mod-tier restriction.
            if panel_role == "mod" and sub_key not in MOD_ALLOWED_SECTIONS:
                refreshed = await _build_current_view()
                await child_interaction.response.edit_message(view=refreshed)
                await child_interaction.followup.send(
                    view=build_notice_layout(
                        "Admin Only",
                        "This section is restricted to server admins. "
                        "Mods can only adjust the sections opted in by your admins.",
                    ),
                    ephemeral=True,
                )
                return

            # Lock check: if still locked, show the gatekeeper notice and abort.
            if sub_key in current_locked[0]:
                new_locked = await self._compute_subcategory_locks(group_node.key, guild.id)
                if sub_key in new_locked:
                    if group_node.key == "embed_settings":
                        await setup_gatekeeper.check_embed_or_notify(child_interaction)
                    elif group_node.key == "wyr_settings":
                        await setup_gatekeeper.check_wyr_or_notify(child_interaction)
                    elif group_node.key == "new_members":
                        await setup_gatekeeper.check_new_members_or_notify(child_interaction)
                    return
                # Unlocked — refresh the menu so the lock icon clears.
                current_locked[0] = new_locked
                refreshed = await _build_current_view()
                await child_interaction.response.edit_message(view=refreshed)
                # Fall through to dispatch.

            # Engine-driven subcategories: dispatch through _navigate_to with
            # edit=True so msg2 is replaced in place. back_callback rebuilds
            # the dashboard's group menu (with session + lock + bespoke
            # dispatch closures intact) when the user clicks Back at the
            # top of this navigation level.
            engine_node = self._ENGINE_SUBCATEGORIES.get(sub_key)
            if engine_node is not None:
                async def _back_to_group(bi: discord.Interaction) -> None:
                    layout = await _build_current_view()
                    await bi.response.edit_message(view=layout)

                try:
                    await self._navigate_to(
                        child_interaction, engine_node, guild,
                        parent_node=group_node, edit=True,
                        refresh_parent=refresh_nav,
                        back_callback=_back_to_group,
                    )
                except Exception as e:
                    logger.exception(f"Engine dispatch failed for {sub_key}: {e}")
                    try:
                        await child_interaction.followup.send(
                            view=build_notice_layout(
                                "Something went wrong",
                                f"Could not open **{sub_key}**.",
                            ),
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                return

            handler = self._get_subcategory_handlers().get(sub_key)
            if not handler:
                logger.warning(f"No handler registered for subcategory {sub_key!r}")
                return
            try:
                await handler(
                    child_interaction,
                    parent_node=group_node,
                    rebuild_group_view=_build_current_view,
                    session=session,
                )
            except Exception as e:
                logger.exception(f"Subcategory handler {sub_key} failed: {e}")
                try:
                    await child_interaction.followup.send(
                        view=build_notice_layout(
                            "Something went wrong",
                            f"Could not open **{sub_key}**.",
                        ),
                        ephemeral=True,
                    )
                except Exception:
                    pass

        async def on_back(back_interaction: discord.Interaction):
            if back_interaction.user.id != admin_id:
                await back_interaction.response.send_message(
                    view=build_notice_layout(
                        "Access Denied",
                        "Only the admin who opened this panel can interact with it.",
                    ),
                    ephemeral=True,
                )
                return
            session.clear_msg2()
            await back_interaction.response.edit_message(
                view=create_empty_layout(
                    "Setting closed. Use the overview above to continue."
                )
            )
            # Refresh dashboard so any changes show up.
            await refresh_nav()

        layout = build_menu_view(group_node, summary_map, on_sub_select, on_back)
        session.register_view(layout)
        await sel_interaction.response.send_message(view=layout, ephemeral=True)
        try:
            msg = await sel_interaction.original_response()
            session.set_msg2(layout, msg)
        except Exception as e:
            logger.debug(f"Could not capture msg2 reference: {e}")

    # ==================== Bespoke handler helpers ==============================

    def _build_back_to_group_button(
        self,
        parent_node: PanelNode | None,
        *,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None,
    ) -> discord.ui.Button:
        """Return a navigation button for a bespoke view.

        Per ADMIN_PANEL_STANDARD.md §1, every leaf / view-only panel has an
        escape. Inside the dashboard flow returns a secondary `Back` wired
        to the parent group menu; outside the dashboard flow (legacy or
        slash-command callers) returns a danger `Close` that replaces the
        message with a "Configuration Closed" notice.
        """
        if parent_node is not None and rebuild_group_view is not None:
            btn = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id=cid("editor", "back", parent_node.key),
            )

            async def _back_cb(back_interaction: discord.Interaction) -> None:
                layout = await rebuild_group_view()
                try:
                    await back_interaction.response.edit_message(view=layout)
                except discord.HTTPException as exc:
                    logger.warning("admin panel back-to-group edit failed: %s", exc)

            btn.callback = _back_cb
            return btn

        btn = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            custom_id=cid("editor", "close"),
        )

        async def _close_cb(close_interaction: discord.Interaction) -> None:
            try:
                await close_interaction.response.edit_message(
                    view=build_notice_layout(
                        "Configuration Closed",
                        "Use `/admin panel` to open a new session.",
                    ),
                )
            except discord.HTTPException as exc:
                logger.warning("admin panel close edit failed: %s", exc)

        btn.callback = _close_cb
        return btn

    def _attach_back_to_group(
        self,
        layout: discord.ui.LayoutView,
        parent_node: PanelNode | None,
        *,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None,
    ) -> discord.ui.LayoutView:
        """Append a Back/Close navigation ActionRow to a bespoke LayoutView."""
        btn = self._build_back_to_group_button(
            parent_node, rebuild_group_view=rebuild_group_view,
        )
        row = discord.ui.ActionRow()
        row.add_item(btn)
        layout.add_item(row)
        return layout

    async def _safe_edit_original(
        self,
        interaction: discord.Interaction,
        **kwargs,
    ) -> bool:
        """Edit the original interaction response with HTTPException handling per §9.

        On failure, logs and surfaces a Message-3 notice via followup so the
        user is never left staring at a stale UI.
        """
        try:
            await self._safe_edit_original(interaction,**kwargs)
            return True
        except discord.HTTPException as exc:
            logger.warning("admin panel edit_original_response failed: %s", exc)
            try:
                await interaction.followup.send(
                    view=build_notice_layout(
                        "UI Update Failed",
                        "The panel could not be refreshed. Please reopen with `/admin panel`.",
                    ),
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass
            return False

    # ==================== Panel Engine ====================

    async def _navigate_to(
        self,
        interaction: discord.Interaction,
        node: PanelNode,
        guild: discord.Guild,
        *,
        parent_node: PanelNode | None = None,
        edit: bool = False,
        refresh_parent: Callable[[], Awaitable[None]] | None = None,
        back_callback: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    ) -> None:
        """Generic navigation for panel engine nodes.

        For menu nodes: gathers child summaries, builds and shows the menu.
        For select nodes: fetches current values, builds and shows the select view
        with autosave and optional clear support.
        """
        back_label = "Close" if parent_node is None else "Back"
        if node.kind == "menu":
            # Gather current summaries for all children
            summary_map: dict[str, list] = {}
            for key, child in node.children.items():
                summary_map[key] = await self._gather_node_summary_values(child, guild.id)

            async def on_select(sel_interaction: discord.Interaction, child_key: str):
                child = node.children.get(child_key)
                if not child:
                    return

                # Per-setting pre-check gate (e.g. tier-readiness for description limits).
                # pre_check returns a LayoutView (blocked) or None (allowed) per §1.
                # edit_message fires first to reset the dropdown, then followup for the notice.
                if child.pre_check:
                    denied_view = await child.pre_check(sel_interaction, guild.id)
                    if denied_view is not None:
                        _pre_back_label = "Back" if (back_callback is not None or parent_node is not None) else "Done"
                        refreshed = build_menu_view(
                            node, summary_map, on_select, on_cancel,
                            back_label=_pre_back_label,
                        )
                        await sel_interaction.response.edit_message(view=refreshed)
                        await sel_interaction.followup.send(view=denied_view, ephemeral=True)
                        return

                if child.kind == "modal_input":
                    # Fetch current value to pre-fill the modal
                    current_str = ""
                    if child.get_values:
                        try:
                            vals = list(await child.get_values(guild.id))
                            current_str = str(vals[0]) if vals else ""
                        except Exception:
                            pass

                    async def on_modal_submit(modal_interaction: discord.Interaction, raw_value: str):
                        # Empty string → clear (if clear_values exists)
                        if not raw_value and child.clear_values:
                            rl_key = (sel_interaction.user.id, child.key)
                            now = time.monotonic()
                            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                                await modal_interaction.response.send_message(
                                    view=build_notice_layout(
                                        "Slow Down",
                                        "Saving too quickly — please wait a moment.",
                                    ),
                                    ephemeral=True,
                                )
                                return
                            self._autosave_cooldowns[rl_key] = now
                            await modal_interaction.response.defer(ephemeral=True)
                            success = await child.clear_values(guild.id)
                            action = "cleared"
                            verb = "clear"
                        else:
                            # Validate
                            if child.modal_validator:
                                ok, value, error = child.modal_validator(raw_value)
                                if not ok:
                                    rl_key = (sel_interaction.user.id, child.key)
                                    now = time.monotonic()
                                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                                        await modal_interaction.response.send_message(
                                            view=build_notice_layout(
                                                "Slow Down",
                                                "Too many attempts — please wait a moment.",
                                            ),
                                            ephemeral=True,
                                        )
                                        return
                                    self._autosave_cooldowns[rl_key] = now
                                    retry_modal = PanelInputModal(
                                        title=error if len(error) <= 45 else error[:42] + "...",
                                        label=child.modal_label or child.label,
                                        placeholder=child.modal_placeholder or "",
                                        min_length=child.modal_min_length,
                                        max_length=child.modal_max_length,
                                        default=raw_value,
                                        on_submit_callback=on_modal_submit,
                                        paragraph=child.modal_paragraph,
                                        required=child.modal_required,
                                    )
                                    await modal_interaction.response.send_modal(retry_modal)
                                    return
                            else:
                                value = raw_value

                            rl_key = (sel_interaction.user.id, child.key)
                            now = time.monotonic()
                            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                                await modal_interaction.response.send_message(
                                    view=build_notice_layout(
                                        "Slow Down",
                                        "Saving too quickly — please wait a moment.",
                                    ),
                                    ephemeral=True,
                                )
                                return
                            self._autosave_cooldowns[rl_key] = now
                            await modal_interaction.response.defer(ephemeral=True)
                            success = await child.set_values(guild.id, [value])
                            action = "updated"
                            verb = "update"

                        # Prune stale cooldown entries
                        cutoff = time.monotonic() - 60.0
                        self._autosave_cooldowns = {
                            k: v for k, v in self._autosave_cooldowns.items() if v > cutoff
                        }

                        if success:
                            logger.info(
                                f"Admin {sel_interaction.user} {action} {child.key} in guild {guild.id}"
                            )
                            # Rebuild parent menu with fresh summaries
                            new_summary_map: dict[str, list] = {}
                            for key, c in node.children.items():
                                new_summary_map[key] = await self._gather_node_summary_values(c, guild.id)
                            new_menu_layout = build_menu_view(node, new_summary_map, on_select, on_cancel)
                            try:
                                await self._safe_edit_original(sel_interaction,view=new_menu_layout)
                            except discord.HTTPException as http_exc:
                                logger.warning("Could not refresh menu after inline modal: %s", http_exc)
                        else:
                            await modal_interaction.followup.send(
                                view=create_empty_layout(f"Failed to {verb} **{child.label}**."),
                                ephemeral=True,
                            )

                    modal = PanelInputModal(
                        title=child.modal_title or f"Set {child.label}",
                        label=child.modal_label or child.label,
                        placeholder=child.modal_placeholder or "",
                        min_length=child.modal_min_length,
                        max_length=child.modal_max_length,
                        default=current_str,
                        on_submit_callback=on_modal_submit,
                        paragraph=child.modal_paragraph,
                        required=child.modal_required,
                    )
                    await sel_interaction.response.send_modal(modal)
                else:
                    # Child's Back should return to THIS menu re-rendered with
                    # the same back_callback intact (so multi-level Back chains
                    # keep working all the way back to the dashboard group).
                    async def _re_render_self(bi: discord.Interaction) -> None:
                        await self._navigate_to(
                            bi, node, guild,
                            parent_node=parent_node, edit=True,
                            refresh_parent=refresh_parent,
                            back_callback=back_callback,
                        )

                    await self._navigate_to(
                        sel_interaction, child, guild,
                        parent_node=node, edit=True,
                        refresh_parent=refresh_parent,
                        back_callback=_re_render_self,
                    )

            async def on_cancel(cancel_interaction: discord.Interaction):
                if back_callback is not None:
                    await back_callback(cancel_interaction)
                elif parent_node is not None:
                    await self._navigate_to(
                        cancel_interaction, parent_node, guild, edit=True,
                        refresh_parent=refresh_parent,
                    )
                else:
                    await cancel_interaction.response.edit_message(
                        view=create_empty_layout(f"{node.label} configuration closed.")
                    )

            menu_back_label = "Back" if (back_callback is not None or parent_node is not None) else "Done"
            layout = build_menu_view(node, summary_map, on_select, on_cancel, back_label=menu_back_label)
            if interaction.response.is_done():
                if edit:
                    await self._safe_edit_original(interaction,view=layout)
                else:
                    msg = await interaction.followup.send(view=layout, ephemeral=True)
                    attach_timeout_expiry_msg(layout, msg)
            elif edit:
                await interaction.response.edit_message(view=layout)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
                try:
                    msg = await interaction.original_response()
                    attach_timeout_expiry_msg(layout, msg)
                except Exception:
                    pass

        elif node.kind in ("role_select", "channel_select", "option_select"):
            current_values = list(await node.get_values(guild.id)) if node.get_values else []

            async def on_save(save_interaction: discord.Interaction, values: list):
                # Per-user, per-node rate limit
                rl_key = (save_interaction.user.id, node.key)
                now = time.monotonic()
                if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                    await save_interaction.response.send_message(
                        "Saving too quickly — please wait a moment.", ephemeral=True
                    )
                    return
                self._autosave_cooldowns[rl_key] = now
                # Prune stale entries (older than 60 s) to prevent unbounded growth
                cutoff = now - 60.0
                self._autosave_cooldowns = {
                    k: v for k, v in self._autosave_cooldowns.items() if v > cutoff
                }

                await save_interaction.response.defer(ephemeral=True)

                # Permission pre-check before saving
                if node.kind == "channel_select" and values:
                    ok, err = check_channel_permissions(guild, int(values[0]), node.key)
                    if not ok:
                        await save_interaction.followup.send(err, ephemeral=True)
                        return
                elif node.kind == "role_select" and values:
                    for rid in values:
                        ok, err = check_role_permissions(guild, int(rid), node.key)
                        if not ok:
                            await save_interaction.followup.send(err, ephemeral=True)
                            return

                success = await node.set_values(guild.id, values)
                if success:
                    setup_gatekeeper.invalidate_embed(guild.id)
                    if parent_node and parent_node.key == "role_tiers":
                        setup_gatekeeper.invalidate_all_tiers(guild.id)
                    logger.info(f"Admin {save_interaction.user} updated {node.key} in guild {guild.id}")
                    new_layout = build_select_view(node, values, guild, on_save, on_back, on_clear_fn, back_label)
                    try:
                        await self._safe_edit_original(save_interaction,view=new_layout)
                    except discord.HTTPException as http_exc:
                        logger.warning("Could not refresh select view after save: %s", http_exc)
                    if node.post_save_hook:
                        await node.post_save_hook(save_interaction, guild.id, values)
                    if refresh_parent:
                        await refresh_parent()
                else:
                    await save_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back(back_interaction: discord.Interaction):
                if back_callback is not None:
                    await back_callback(back_interaction)
                elif parent_node:
                    await self._navigate_to(back_interaction, parent_node, guild, edit=True)
                else:
                    await back_interaction.response.edit_message(
                        view=create_empty_layout(f"{node.label} configuration closed.")
                    )

            on_clear_fn = None
            if node.clear_values:
                async def on_clear(clear_interaction: discord.Interaction):
                    rl_key = (clear_interaction.user.id, node.key)
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await clear_interaction.response.send_message(
                            "Saving too quickly — please wait a moment.", ephemeral=True
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now
                    cutoff = now - 60.0
                    self._autosave_cooldowns = {
                        k: v for k, v in self._autosave_cooldowns.items() if v > cutoff
                    }
                    await clear_interaction.response.defer(ephemeral=True)
                    success = await node.clear_values(guild.id)
                    if success:
                        if parent_node and parent_node.key == "role_tiers":
                            setup_gatekeeper.invalidate_all_tiers(guild.id)
                        logger.info(f"Admin {clear_interaction.user} cleared {node.key} in guild {guild.id}")
                        new_layout = build_select_view(node, [], guild, on_save, on_back, on_clear_fn, back_label)
                        try:
                            await self._safe_edit_original(clear_interaction,view=new_layout)
                        except discord.HTTPException as http_exc:
                            logger.warning("Could not refresh select view after clear: %s", http_exc)
                        if refresh_parent:
                            await refresh_parent()
                    else:
                        await clear_interaction.followup.send(
                            view=create_empty_layout(f"Failed to clear **{node.label}**."), ephemeral=True
                        )

                on_clear_fn = on_clear

            layout = build_select_view(node, current_values, guild, on_save, on_back, on_clear_fn, back_label)
            if interaction.response.is_done():
                if edit:
                    await self._safe_edit_original(interaction,view=layout)
                else:
                    msg = await interaction.followup.send(view=layout, ephemeral=True)
                    attach_timeout_expiry_msg(layout, msg)
            elif edit:
                await interaction.response.edit_message(view=layout)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
                try:
                    msg = await interaction.original_response()
                    attach_timeout_expiry_msg(layout, msg)
                except Exception:
                    pass

        elif node.kind == "modal_input":
            current_values = list(await node.get_values(guild.id)) if node.get_values else []

            async def on_save_modal(
                button_interaction: discord.Interaction,
                modal_interaction: discord.Interaction,
                raw_value: str,
            ):
                # Validate before rate-limit check so bad input is rejected cheaply
                if node.modal_validator:
                    ok, value, error = node.modal_validator(raw_value)
                    if not ok:
                        rl_key_fail = (button_interaction.user.id, node.key)
                        now_fail = time.monotonic()
                        if now_fail - self._autosave_cooldowns.get(rl_key_fail, 0.0) < self.AUTOSAVE_COOLDOWN:
                            await modal_interaction.response.send_message(
                                "Too many attempts — please wait a moment.", ephemeral=True
                            )
                            return
                        self._autosave_cooldowns[rl_key_fail] = now_fail
                        async def _retry_submit(mi: discord.Interaction, raw: str):
                            await on_save_modal(button_interaction, mi, raw)
                        retry_modal = PanelInputModal(
                            title=error if len(error) <= 45 else error[:42] + "...",
                            label=node.modal_label or "Value",
                            placeholder=node.modal_placeholder or "",
                            min_length=node.modal_min_length,
                            max_length=node.modal_max_length,
                            default=raw_value,
                            on_submit_callback=_retry_submit,
                            paragraph=node.modal_paragraph,
                            required=node.modal_required,
                        )
                        await modal_interaction.response.send_modal(retry_modal)
                        return
                else:
                    value = raw_value

                rl_key = (button_interaction.user.id, node.key)
                now = time.monotonic()
                if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                    await modal_interaction.response.send_message(
                        "Saving too quickly — please wait a moment.", ephemeral=True
                    )
                    return
                self._autosave_cooldowns[rl_key] = now
                cutoff = now - 60.0
                self._autosave_cooldowns = {
                    k: v for k, v in self._autosave_cooldowns.items() if v > cutoff
                }

                await modal_interaction.response.defer(ephemeral=True)
                success = await node.set_values(guild.id, [value])
                if success:
                    logger.info(f"Admin {button_interaction.user} updated {node.key} in guild {guild.id}")
                    new_layout = build_modal_trigger_view(
                        node, [str(value)], guild, on_save_modal, on_back_modal, on_clear_modal_fn, back_label
                    )
                    try:
                        await self._safe_edit_original(button_interaction,view=new_layout)
                    except discord.HTTPException as http_exc:
                        logger.warning("Could not refresh modal trigger view after save: %s", http_exc)
                else:
                    await modal_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back_modal(back_interaction: discord.Interaction):
                if back_callback is not None:
                    await back_callback(back_interaction)
                elif parent_node:
                    await self._navigate_to(back_interaction, parent_node, guild, edit=True)
                else:
                    await back_interaction.response.edit_message(
                        view=create_empty_layout(f"{node.label} configuration closed.")
                    )

            on_clear_modal_fn = None
            if node.clear_values:
                async def on_clear_modal(clear_interaction: discord.Interaction):
                    rl_key = (clear_interaction.user.id, node.key)
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await clear_interaction.response.send_message(
                            "Saving too quickly — please wait a moment.", ephemeral=True
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now
                    await clear_interaction.response.defer(ephemeral=True)
                    success = await node.clear_values(guild.id)
                    if success:
                        logger.info(f"Admin {clear_interaction.user} cleared {node.key} in guild {guild.id}")
                        new_layout = build_modal_trigger_view(
                            node, [], guild, on_save_modal, on_back_modal, on_clear_modal_fn, back_label
                        )
                        try:
                            await self._safe_edit_original(clear_interaction,view=new_layout)
                        except discord.HTTPException as http_exc:
                            logger.warning("Could not refresh modal trigger view after clear: %s", http_exc)
                    else:
                        await clear_interaction.followup.send(
                            view=create_empty_layout(f"Failed to clear **{node.label}**."), ephemeral=True
                        )

                on_clear_modal_fn = on_clear_modal

            layout = build_modal_trigger_view(
                node, current_values, guild, on_save_modal, on_back_modal, on_clear_modal_fn, back_label
            )
            if interaction.response.is_done():
                if edit:
                    await self._safe_edit_original(interaction,view=layout)
                else:
                    msg = await interaction.followup.send(view=layout, ephemeral=True)
                    attach_timeout_expiry_msg(layout, msg)
            elif edit:
                await interaction.response.edit_message(view=layout)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
                try:
                    msg = await interaction.original_response()
                    attach_timeout_expiry_msg(layout, msg)
                except Exception:
                    pass

        elif node.kind == "dual_modal_input":
            current_values = list(await node.get_values(guild.id)) if node.get_values else []

            async def on_save_dual(
                button_interaction: discord.Interaction,
                modal_interaction: discord.Interaction,
                val1: str,
                val2: str,
            ):
                rl_key = (button_interaction.user.id, node.key)
                now = time.monotonic()
                if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                    await modal_interaction.response.send_message(
                        "Saving too quickly — please wait a moment.", ephemeral=True
                    )
                    return
                self._autosave_cooldowns[rl_key] = now
                cutoff = now - 60.0
                self._autosave_cooldowns = {
                    k: v for k, v in self._autosave_cooldowns.items() if v > cutoff
                }

                await modal_interaction.response.defer(ephemeral=True)
                success = await node.set_values(guild.id, [val1, val2])
                if success:
                    logger.info(f"Admin {button_interaction.user} updated {node.key} in guild {guild.id}")
                    new_layout = build_dual_modal_trigger_view(
                        node, [val1, val2], guild, on_save_dual, on_back_dual, back_label
                    )
                    try:
                        await self._safe_edit_original(button_interaction,view=new_layout)
                    except discord.HTTPException as http_exc:
                        logger.warning("Could not refresh dual modal view after save: %s", http_exc)
                else:
                    await modal_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back_dual(back_interaction: discord.Interaction):
                if back_callback is not None:
                    await back_callback(back_interaction)
                elif parent_node:
                    await self._navigate_to(back_interaction, parent_node, guild, edit=True)
                else:
                    await back_interaction.response.edit_message(
                        view=create_empty_layout(f"{node.label} configuration closed.")
                    )

            layout = build_dual_modal_trigger_view(
                node, current_values, guild, on_save_dual, on_back_dual, back_label
            )
            if interaction.response.is_done():
                if edit:
                    await self._safe_edit_original(interaction,view=layout)
                else:
                    msg = await interaction.followup.send(view=layout, ephemeral=True)
                    attach_timeout_expiry_msg(layout, msg)
            elif edit:
                await interaction.response.edit_message(view=layout)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
                try:
                    msg = await interaction.original_response()
                    attach_timeout_expiry_msg(layout, msg)
                except Exception:
                    pass

        elif node.kind == "file_upload":
            current_values = list(await node.get_values(guild.id)) if node.get_values else []

            async def on_back_fu(back_interaction: discord.Interaction):
                if back_callback is not None:
                    await back_callback(back_interaction)
                elif parent_node:
                    await self._navigate_to(back_interaction, parent_node, guild, edit=True)
                else:
                    await back_interaction.response.edit_message(
                        view=create_empty_layout(f"{node.label} configuration closed.")
                    )

            on_clear_fu = None
            if node.clear_values:
                async def on_clear_fu(clear_interaction: discord.Interaction):
                    rl_key = (clear_interaction.user.id, node.key)
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await clear_interaction.response.send_message(
                            "Saving too quickly — please wait a moment.", ephemeral=True
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now
                    await clear_interaction.response.defer(ephemeral=True)
                    success = await node.clear_values(guild.id)
                    if success:
                        logger.info(f"Admin {clear_interaction.user} cleared {node.key} in guild {guild.id}")
                        new_layout = build_file_upload_status_view(node, [], guild, on_back_fu, on_clear_fu, back_label, on_upload_fu)
                        try:
                            await self._safe_edit_original(clear_interaction,view=new_layout)
                        except discord.HTTPException as http_exc:
                            logger.warning("Could not refresh file upload view after clear: %s", http_exc)
                        if refresh_parent:
                            await refresh_parent()
                    else:
                        await clear_interaction.followup.send(
                            view=create_empty_layout(f"Failed to clear **{node.label}**."), ephemeral=True
                        )

            on_upload_fu = None
            if node.set_values:
                async def on_upload_fu(
                    button_interaction: discord.Interaction,
                    modal_interaction: discord.Interaction,
                    attachment: discord.Attachment,
                ):
                    await modal_interaction.response.defer(ephemeral=True)
                    if not attachment.filename.endswith(".json"):
                        await modal_interaction.followup.send(view=build_notice_layout("Invalid File", "Please upload a `.json` file."), ephemeral=True)
                        return
                    if attachment.size > 50_000:
                        await modal_interaction.followup.send(view=build_notice_layout("File Too Large", "Maximum file size is 50 KB."), ephemeral=True)
                        return
                    try:
                        raw = (await attachment.read()).decode("utf-8")
                    except Exception as exc:
                        await modal_interaction.followup.send(
                            view=build_notice_layout("File Error", f"Could not read file: {exc}"),
                            ephemeral=True,
                        )
                        return
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        await modal_interaction.followup.send(
                            view=build_notice_layout("Invalid JSON", str(exc)),
                            ephemeral=True,
                        )
                        return
                    if node.schema_validator:
                        ok, err_msg = node.schema_validator(data)
                        if not ok:
                            await modal_interaction.followup.send(
                                view=build_notice_layout("Schema Error", err_msg),
                                ephemeral=True,
                            )
                            return
                    rl_key = (button_interaction.user.id, node.key)
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await modal_interaction.followup.send(view=build_notice_layout("Slow Down", "Saving too quickly — wait a moment."), ephemeral=True)
                        return
                    self._autosave_cooldowns[rl_key] = now
                    success = await node.set_values(guild.id, [raw])
                    if success:
                        logger.info(f"Admin {button_interaction.user} uploaded {node.key} in guild {guild.id}")
                        new_layout = build_file_upload_status_view(
                            node, [raw], guild, on_back_fu, on_clear_fu, back_label, on_upload_fu
                        )
                        try:
                            await self._safe_edit_original(button_interaction,view=new_layout)
                        except discord.HTTPException as http_exc:
                            logger.warning("Could not refresh file upload view after upload: %s", http_exc)
                        if refresh_parent:
                            await refresh_parent()
                    else:
                        await modal_interaction.followup.send(view=build_notice_layout("Failed to save", "Could not save config."), ephemeral=True)

            layout = build_file_upload_status_view(node, current_values, guild, on_back_fu, on_clear_fu, back_label, on_upload_fu)
            if interaction.response.is_done():
                if edit:
                    await self._safe_edit_original(interaction,view=layout)
                else:
                    msg = await interaction.followup.send(view=layout, ephemeral=True)
                    attach_timeout_expiry_msg(layout, msg)
            elif edit:
                await interaction.response.edit_message(view=layout)
            else:
                await interaction.response.send_message(view=layout, ephemeral=True)
                try:
                    msg = await interaction.original_response()
                    attach_timeout_expiry_msg(layout, msg)
                except Exception:
                    pass

    # ==================== Color Sets ====================

    async def _show_color_sets_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ) -> None:
        """Show the Color Sets management panel (edits msg2 in place).

        Internal navigation (set list → detail → assign role/tier) already
        edits in place via edit_original_response. The root Done callback
        now returns to the Embed Settings group menu when invoked from the
        panel flow.
        """
        guild = interaction.guild
        guild_id = guild.id

        # ── Helper: build and display the top-level menu ──────────────────────

        async def _ensure_seeded(default_color: int) -> None:
            """One-time seed: create 5 default tier sets if guild has never had any."""
            from storage.config_manager import get_guild_config_manager
            gcm = await get_guild_config_manager()
            if await gcm.get_setting("color_tiers_seeded", guild_id, False):
                return
            existing = await ColorSetActions.list_color_sets(guild_id)
            if not existing:
                await ColorSetActions.seed_default_sets(guild_id, default_color)
            await gcm.set_setting("color_tiers_seeded", True, guild_id)

        async def _render_menu(nav_interaction: discord.Interaction, *, edit) -> None:
            """Fetch fresh data and render the color sets menu."""
            default_color = await ColorSetActions.get_default_color(guild_id)
            await _ensure_seeded(default_color)
            sets = await ColorSetActions.list_color_sets(guild_id)
            all_assignments = await ColorSetActions.list_assignments(guild_id)

            assignment_counts: dict[str, int] = {}
            tier_per_set: dict[str, str | None] = {}
            for a in all_assignments:
                sid = a["color_set_id"]
                assignment_counts[sid] = assignment_counts.get(sid, 0) + 1
                if a.get("target_type") == "tier":
                    tier_per_set[sid] = a["target_id"]

            async def on_create(create_inter: discord.Interaction) -> None:
                async def _on_modal(modal_inter: discord.Interaction, name: str, colors_raw: str) -> None:
                    colors, failed = parse_named_colors_string(colors_raw)
                    # Block the server default color from being added to any set
                    excluded_default = False
                    if default_color is not None:
                        before = len(colors)
                        colors = [c for c in colors if c["value"] != default_color]
                        excluded_default = len(colors) < before
                    if not colors:
                        bad = f" Unrecognized: {', '.join(failed[:3])}" if failed else ""
                        note = (
                            f" `{color_int_to_hex(default_color)}` is the server default "
                            "and cannot be part of a color set."
                            if excluded_default else ""
                        )
                        await modal_inter.response.send_message(
                            f"No valid colors found.{bad}{note}", ephemeral=True
                        )
                        return

                    # Check color uniqueness before creating
                    conflict = await check_color_uniqueness(guild_id, colors)
                    if conflict.status == "breaking":
                        await modal_inter.response.send_message(
                            conflict.message, ephemeral=True
                        )
                        return

                    set_id = await ColorSetActions.create_color_set(guild_id, name, "", colors)
                    if set_id:
                        logger.info(
                            f"Admin {modal_inter.user} created color set '{name}' "
                            f"with {len(colors)} colors in guild {guild_id}"
                        )
                        await modal_inter.response.defer()
                        await _render_menu_from_modal(modal_inter)
                    else:
                        await modal_inter.response.send_message(
                            f"Failed to create **{name}**. The name may already be in use.",
                            ephemeral=True,
                        )

                await create_inter.response.send_modal(ColorSetCreateModal(_on_modal))

            async def on_select_set(sel_inter: discord.Interaction, set_id: str) -> None:
                color_set = await ColorSetActions.get_color_set(guild_id, set_id)
                if color_set:
                    await _render_detail(sel_inter, color_set, edit=True)
                else:
                    await sel_inter.response.send_message(
                        "Color set not found.", ephemeral=True
                    )

            async def on_change_default(btn_inter: discord.Interaction) -> None:
                async def _on_modal(modal_inter: discord.Interaction, color_raw: str) -> None:
                    color_val = normalize_color(color_raw.strip())
                    if color_val is None:
                        await modal_inter.response.send_message(
                            "No valid color found. Please enter a hex code (#RRGGBB) or rgb(r, g, b).",
                            ephemeral=True,
                        )
                        return
                    await ColorSetActions.set_default_color(guild_id, color_val)
                    logger.info(
                        f"Admin {modal_inter.user} changed default color to "
                        f"{color_int_to_hex(color_val)} in guild {guild_id}"
                    )
                    await modal_inter.response.defer()
                    await _render_menu_from_modal(modal_inter)

                await btn_inter.response.send_modal(
                    DefaultColorModal(
                        _on_modal,
                        title="Change Default Color",
                        current_hex=color_int_to_hex(default_color) if default_color is not None else "",
                    )
                )

            async def on_done(done_inter: discord.Interaction) -> None:
                if rebuild_group_view is not None:
                    group_layout = await rebuild_group_view()
                    await done_inter.response.edit_message(view=group_layout)
                else:
                    await done_inter.response.edit_message(
                        view=create_empty_layout("Color Sets configuration closed.")
                    )

            view = build_color_sets_menu(
                sets, assignment_counts, default_color, tier_per_set,
                on_create, on_select_set, on_change_default, on_done,
            )
            if edit == "followup":
                msg = await nav_interaction.followup.send(view=view, ephemeral=True)
                attach_timeout_expiry_msg(view, msg)
            elif edit == "original":
                await self._safe_edit_original(nav_interaction,view=view)
            elif edit:
                await nav_interaction.response.edit_message(view=view)
            else:
                await nav_interaction.response.send_message(view=view, ephemeral=True)
                try:
                    msg = await nav_interaction.original_response()
                    attach_timeout_expiry_msg(view, msg)
                except Exception:
                    pass

        async def _render_menu_from_modal(modal_inter: discord.Interaction) -> None:
            """Re-render the menu from a modal interaction (edits original message)."""
            default_color = await ColorSetActions.get_default_color(guild_id)
            await _ensure_seeded(default_color)
            sets = await ColorSetActions.list_color_sets(guild_id)
            all_assignments = await ColorSetActions.list_assignments(guild_id)
            assignment_counts: dict[str, int] = {}
            tier_per_set: dict[str, str | None] = {}
            for a in all_assignments:
                sid = a["color_set_id"]
                assignment_counts[sid] = assignment_counts.get(sid, 0) + 1
                if a.get("target_type") == "tier":
                    tier_per_set[sid] = a["target_id"]

            async def on_create(create_inter: discord.Interaction) -> None:
                async def _on_modal(mi: discord.Interaction, name: str, colors_raw: str) -> None:
                    colors, failed = parse_named_colors_string(colors_raw)
                    excluded_default = False
                    if default_color is not None:
                        before = len(colors)
                        colors = [c for c in colors if c["value"] != default_color]
                        excluded_default = len(colors) < before
                    if not colors:
                        bad = f" Unrecognized: {', '.join(failed[:3])}" if failed else ""
                        note = (
                            f" `{color_int_to_hex(default_color)}` is the server default "
                            "and cannot be part of a color set."
                            if excluded_default else ""
                        )
                        await mi.response.send_message(
                            f"No valid colors found.{bad}{note}", ephemeral=True
                        )
                        return

                    # Check color uniqueness before creating
                    conflict = await check_color_uniqueness(guild_id, colors)
                    if conflict.status == "breaking":
                        await mi.response.send_message(conflict.message, ephemeral=True)
                        return

                    set_id = await ColorSetActions.create_color_set(guild_id, name, "", colors)
                    if set_id:
                        logger.info(
                            f"Admin {mi.user} created color set '{name}' in guild {guild_id}"
                        )
                        await mi.response.defer()
                        await _render_menu_from_modal(mi)
                    else:
                        await mi.response.send_message(
                            f"Failed to create **{name}**. The name may already be in use.",
                            ephemeral=True,
                        )
                await create_inter.response.send_modal(ColorSetCreateModal(_on_modal))

            async def on_select_set(sel_inter: discord.Interaction, set_id: str) -> None:
                color_set = await ColorSetActions.get_color_set(guild_id, set_id)
                if color_set:
                    await _render_detail(sel_inter, color_set, edit=True)
                else:
                    await sel_inter.response.send_message(
                        "Color set not found.", ephemeral=True
                    )

            async def on_change_default(btn_inter: discord.Interaction) -> None:
                async def _on_modal(mi: discord.Interaction, color_raw: str) -> None:
                    color_val = normalize_color(color_raw.strip())
                    if color_val is None:
                        await mi.response.send_message(
                            "No valid color found. Please enter a hex code (#RRGGBB) or rgb(r, g, b).",
                            ephemeral=True,
                        )
                        return
                    await ColorSetActions.set_default_color(guild_id, color_val)
                    logger.info(
                        f"Admin {mi.user} changed default color to "
                        f"{color_int_to_hex(color_val)} in guild {guild_id}"
                    )
                    await mi.response.defer()
                    await _render_menu_from_modal(mi)

                await btn_inter.response.send_modal(
                    DefaultColorModal(
                        _on_modal,
                        title="Change Default Color",
                        current_hex=color_int_to_hex(default_color) if default_color is not None else "",
                    )
                )

            async def on_done(done_inter: discord.Interaction) -> None:
                if rebuild_group_view is not None:
                    group_layout = await rebuild_group_view()
                    await done_inter.response.edit_message(view=group_layout)
                else:
                    await done_inter.response.edit_message(
                        view=create_empty_layout("Color Sets configuration closed.")
                    )

            view = build_color_sets_menu(
                sets, assignment_counts, default_color, tier_per_set,
                on_create, on_select_set, on_change_default, on_done,
            )
            await self._safe_edit_original(modal_inter,view=view)

        # ── Helper: build and display a set's detail view ─────────────────────

        async def _render_detail(
            nav_interaction: discord.Interaction,
            color_set: dict,
            *,
            edit,  # True | False | "original"
        ) -> None:
            """Fetch fresh assignment data and render the color set detail view."""
            set_id = color_set["set_id"]
            assignments = await ColorSetActions.list_assignments(guild_id, set_id=set_id)

            # -- "Add Colors" -------------------------------------------------
            async def on_add_colors(add_inter: discord.Interaction) -> None:
                async def _on_modal(modal_inter: discord.Interaction, colors_raw: str) -> None:
                    new_colors, failed = parse_named_colors_string(colors_raw)
                    # Block the server default color from being added to any set
                    server_default = await ColorSetActions.get_default_color(guild_id)
                    excluded_default = False
                    if server_default is not None:
                        before = len(new_colors)
                        new_colors = [c for c in new_colors if c["value"] != server_default]
                        excluded_default = len(new_colors) < before
                    if not new_colors:
                        bad = f" Unrecognized: {', '.join(failed[:3])}" if failed else ""
                        note = (
                            f" `{color_int_to_hex(server_default)}` is the server default "
                            "and cannot be part of a color set."
                            if excluded_default else ""
                        )
                        await modal_inter.response.send_message(
                            f"No valid colors found.{bad}{note}", ephemeral=True
                        )
                        return

                    # Merge with existing (deduplicate by color value)
                    existing = color_set.get("colors", [])
                    existing_values = {c["value"] for c in existing}
                    merged = existing + [c for c in new_colors if c["value"] not in existing_values]

                    # Check cross-set color uniqueness (new colors only, exclude this set)
                    added = [c for c in new_colors if c["value"] not in existing_values]
                    if added:
                        conflict = await check_color_uniqueness(guild_id, added, exclude_set_id=set_id)
                        if conflict.status == "breaking":
                            await modal_inter.response.send_message(
                                conflict.message, ephemeral=True
                            )
                            return

                    # Save immediately
                    await modal_inter.response.defer()
                    await ColorSetActions.update_color_set_colors(guild_id, set_id, merged)
                    color_set["colors"] = merged
                    logger.info(
                        f"Admin {modal_inter.user} added {len(new_colors)} colors "
                        f"to set '{color_set['name']}' in guild {guild_id}"
                    )
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(modal_inter, fresh, edit="original")

                await add_inter.response.send_modal(ColorAddModal(_on_modal))

            # -- "Remove Color" -----------------------------------------------
            async def on_remove_color(rm_inter: discord.Interaction, idx: int) -> None:
                existing = color_set.get("colors", [])
                if idx < 0 or idx >= len(existing):
                    await rm_inter.response.send_message(view=build_notice_layout("Color not found", "That color is not in this set."), ephemeral=True)
                    return
                removed = existing[idx]
                updated = [c for i, c in enumerate(existing) if i != idx]

                # Save directly — removing a color cannot create uniqueness violations
                await rm_inter.response.defer()
                await ColorSetActions.update_color_set_colors(guild_id, set_id, updated)
                color_set["colors"] = updated
                logger.info(
                    f"Admin {rm_inter.user} removed color {color_int_to_hex(removed['value'])} "
                    f"from set '{color_set['name']}' in guild {guild_id}"
                )
                fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                if fresh:
                    await _render_detail(rm_inter, fresh, edit="original")

            # -- "Assign to Role" ---------------------------------------------
            async def on_assign_role(role_inter: discord.Interaction) -> None:
                async def on_role_selected(
                    sel_inter: discord.Interaction, role_id: int
                ) -> None:
                    role = guild.get_role(role_id)
                    role_label = f"@{role.name}" if role else str(role_id)

                    # Rate-limit check
                    rl_key = (sel_inter.user.id, f"color_sets_{set_id}")
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await sel_inter.response.send_message(
                            "Saving too quickly — please wait a moment.", ephemeral=True
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now

                    # Save immediately — no exclusivity constraint for role assignments
                    await sel_inter.response.defer()
                    await ColorSetActions.upsert_assignment(
                        guild_id, set_id, "role", str(role_id)
                    )
                    logger.info(
                        f"Admin {sel_inter.user} assigned set '{color_set['name']}' "
                        f"to role {role_label} in guild {guild_id}"
                    )
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(sel_inter, fresh, edit="original")

                async def on_role_back(back_inter: discord.Interaction) -> None:
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(back_inter, fresh, edit=True)

                await role_inter.response.edit_message(
                    view=build_role_assign_view(
                        color_set["name"], on_role_selected, on_role_back
                    )
                )

            # -- "Remove Assignment" ------------------------------------------
            async def on_remove_assignment(
                rm_inter: discord.Interaction, assignment_id: str
            ) -> None:
                target = next(
                    (a for a in assignments if a["assignment_id"] == assignment_id), None
                )
                if not target:
                    await rm_inter.response.send_message(
                        "Assignment not found.", ephemeral=True
                    )
                    return

                # Save directly — removing an assignment cannot create constraint violations
                await rm_inter.response.defer()
                await ColorSetActions.delete_assignment(
                    guild_id,
                    target["color_set_id"],
                    target["target_type"],
                    str(target["target_id"]),
                )
                logger.info(
                    f"Admin {rm_inter.user} removed assignment "
                    f"({target['target_type']}:{target['target_id']}) "
                    f"from set '{color_set['name']}' in guild {guild_id}"
                )
                fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                if fresh:
                    await _render_detail(rm_inter, fresh, edit="original")

            # -- "Assign to Tier" ---------------------------------------------
            async def on_assign_tier(tier_inter: discord.Interaction) -> None:
                async def on_tier_selected(
                    sel_inter: discord.Interaction, tier_name: str
                ) -> None:
                    # Rate-limit check
                    rl_key = (sel_inter.user.id, f"color_sets_{set_id}")
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await sel_inter.response.send_message(
                            view=build_notice_layout(
                                "Slow Down", "Saving too quickly, please wait a moment.",
                            ),
                            ephemeral=True,
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now

                    # Block assignment if the target tier has no roles configured.
                    # edit_message fires first to reset the select, then followup for the notice.
                    denied_view = await setup_gatekeeper.get_tier_gate_layout(guild_id, tier_name)
                    if denied_view is not None:
                        await sel_inter.response.edit_message(
                            view=build_tier_assign_view(color_set["name"], on_tier_selected, on_tier_back)
                        )
                        await sel_inter.followup.send(view=denied_view, ephemeral=True)
                        return

                    # Check tier exclusivity — one set can only be assigned to one tier
                    conflict = await check_tier_exclusivity(guild_id, set_id, tier_name)
                    if conflict.status == "breaking":
                        await sel_inter.response.send_message(
                            view=build_notice_layout("Tier Conflict", conflict.message),
                            ephemeral=True,
                        )
                        return

                    # Save immediately
                    await sel_inter.response.defer()
                    await ColorSetActions.upsert_assignment(
                        guild_id, set_id, "tier", tier_name
                    )
                    logger.info(
                        f"Admin {sel_inter.user} assigned set '{color_set['name']}' "
                        f"to {tier_name} in guild {guild_id}"
                    )
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(sel_inter, fresh, edit="original")

                async def on_tier_back(back_inter: discord.Interaction) -> None:
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(back_inter, fresh, edit=True)

                await tier_inter.response.edit_message(
                    view=build_tier_assign_view(color_set["name"], on_tier_selected, on_tier_back)
                )

            # -- "Delete Set" -------------------------------------------------
            async def on_delete_set(del_inter: discord.Interaction) -> None:
                async def confirm_and_return(conf_inter: discord.Interaction) -> None:
                    await conf_inter.response.defer()
                    await ColorSetActions.delete_color_set(guild_id, set_id)
                    logger.info(
                        f"Admin {conf_inter.user} deleted color set "
                        f"'{color_set['name']}' in guild {guild_id}"
                    )
                    await _render_menu(conf_inter, edit="original")

                async def cancel_delete(cancel_inter: discord.Interaction) -> None:
                    fresh = await ColorSetActions.get_color_set(guild_id, set_id)
                    if fresh:
                        await _render_detail(cancel_inter, fresh, edit=True)

                await del_inter.response.edit_message(
                    view=build_delete_confirm_view(
                        color_set["name"], confirm_and_return, cancel_delete
                    )
                )

            # -- "Back" -------------------------------------------------------
            async def on_back(back_inter: discord.Interaction) -> None:
                await _render_menu(back_inter, edit=True)

            view = build_color_set_detail(
                color_set, assignments, guild,
                on_add_colors, on_remove_color, on_remove_assignment,
                on_assign_role, on_assign_tier,
                on_delete_set, on_back,
            )
            if edit == "original":
                # Called after a deferred interaction — edit the message via webhook
                await self._safe_edit_original(nav_interaction,view=view)
            elif edit:
                await nav_interaction.response.edit_message(view=view)
            else:
                await nav_interaction.response.send_message(view=view, ephemeral=True)

        # ── First-time setup (forced if no default color is set) ──────────────

        async def _show_default_setup(nav_inter: discord.Interaction, *, edit) -> None:
            """Show the forced setup screen to collect the server default color."""
            async def on_set_default(btn_inter: discord.Interaction) -> None:
                async def _on_modal(modal_inter: discord.Interaction, color_raw: str) -> None:
                    color_val = normalize_color(color_raw.strip())
                    if color_val is None:
                        await modal_inter.response.send_message(
                            "No valid color found. Please enter a hex code (#RRGGBB) or rgb(r, g, b).",
                            ephemeral=True,
                        )
                        return
                    ok = await ColorSetActions.set_default_color(guild_id, color_val)
                    if ok:
                        logger.info(
                            f"Admin {modal_inter.user} set default color to "
                            f"{color_int_to_hex(color_val)} in guild {guild_id}"
                        )
                        await modal_inter.response.defer()
                        await _render_menu_from_modal(modal_inter)
                    else:
                        await modal_inter.response.send_message(
                            "Failed to save default color.", ephemeral=True
                        )

                await btn_inter.response.send_modal(DefaultColorModal(_on_modal))

            async def _setup_on_back(bi: discord.Interaction) -> None:
                if rebuild_group_view is not None:
                    group_layout = await rebuild_group_view()
                    await bi.response.edit_message(view=group_layout)
                else:
                    await bi.response.edit_message(
                        view=create_empty_layout("Color Tiers setup closed.")
                    )

            view = build_default_color_setup_view(
                on_set_default,
                on_back=_setup_on_back if rebuild_group_view is not None else None,
            )
            if edit == "followup":
                msg = await nav_inter.followup.send(view=view, ephemeral=True)
                attach_timeout_expiry_msg(view, msg)
            elif edit == "original":
                await self._safe_edit_original(nav_inter,view=view)
            elif edit:
                await nav_inter.response.edit_message(view=view)
            else:
                await nav_inter.response.send_message(view=view, ephemeral=True)
                try:
                    msg = await nav_inter.original_response()
                    attach_timeout_expiry_msg(view, msg)
                except Exception:
                    pass

        # ── Entry point ───────────────────────────────────────────────────────
        # When invoked from the admin panel, edit msg2 in place instead of
        # spawning a new ephemeral. `edit=True` triggers
        # `response.edit_message` inside _render_menu / _show_default_setup.
        default_color = await ColorSetActions.get_default_color(guild_id)
        if interaction.response.is_done():
            initial_edit = "original"  # already deferred — edit msg2 via edit_original_response
        else:
            initial_edit = True  # consume Select response to edit msg2
        if default_color is None:
            await _show_default_setup(interaction, edit=initial_edit)
        else:
            await _render_menu(interaction, edit=initial_edit)

    # ==================== Status ====================

    async def _show_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the embed configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        stats = await EmbedConfigActions.get_overview(interaction.guild.id)
        layout = build_embed_status_view(stats, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    # ==================== WYR Ping Role ====================

    async def _show_wyr_ping_role_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show WYR ping role configuration with Create Role support (edits msg2)."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return

        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            view = build_wyr_ping_role_view(
                current_values=current,
                guild=guild,
                on_save=_on_role_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_role=_on_create_role,
            )
            if session:
                session.register_view(view)
            return view

        async def _on_role_save(save_inter: discord.Interaction, role_ids: list) -> None:
            rl_key = (save_inter.user.id, "wyr_ping_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await save_inter.response.defer(ephemeral=True)
            ok = await WYRConfigActions.set_ping_role(guild.id, [str(r) for r in role_ids])
            if ok:
                logger.info(f"Admin {save_inter.user} set WYR ping role in guild {guild.id}")
                new_values = list(await WYRConfigActions.get_ping_role(guild.id))
                await self._safe_edit_original(save_inter,view=_rebuild(new_values))
            else:
                await save_inter.followup.send(view=build_notice_layout("Failed to save", "Could not save WYR ping role."), ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            if rebuild_group_view is not None:
                layout = await rebuild_group_view()
                await back_inter.response.edit_message(view=layout)
            else:
                await back_inter.response.edit_message(
                    view=create_empty_layout("WYR Ping Role configuration closed.")
                )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "wyr_ping_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await clear_inter.response.defer(ephemeral=True)
            ok = await WYRConfigActions.clear_ping_role(guild.id)
            if ok:
                logger.info(f"Admin {clear_inter.user} cleared WYR ping role in guild {guild.id}")
                await self._safe_edit_original(clear_inter,view=_rebuild([]))
            else:
                await clear_inter.followup.send(view=build_notice_layout("Failed to clear", "Could not clear WYR ping role."), ephemeral=True)

        async def _on_create_role(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, role_name: str) -> None:
                try:
                    new_role = await guild.create_role(
                        name=role_name,
                        reason=f"Created via WYR admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Missing Permissions",
                            "Missing permissions to create roles. Grant the bot **Manage Roles**.",
                        ),
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Failed to Create Role",
                            f"Could not create the role: {e}",
                        ),
                        ephemeral=True,
                    )
                    return

                await WYRConfigActions.set_ping_role(guild.id, [str(new_role.id)])
                logger.info(
                    f"Admin {btn_inter.user} created WYR ping role '{new_role.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_role.id)]))

            await btn_inter.response.send_modal(WyrCreateRoleModal(on_submit_callback=_on_modal_submit))

        current_values = list(await WYRConfigActions.get_ping_role(guild.id))
        layout = _rebuild(current_values)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== WYR Status ====================

    async def _show_wyr_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the WYR configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        stats = await WYRConfigActions.get_overview(interaction.guild.id)
        layout = build_wyr_status_view(stats, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)


    # ==================== New Members Settings ====================

    async def _show_nm_welcome_channel_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show NM welcome channel configuration with Create Channel support (edits msg2)."""
        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            view = build_nm_welcome_channel_view(
                current_values=current,
                guild=guild,
                on_save=_on_channel_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_channel=_on_create_channel,
            )
            if session:
                session.register_view(view)
            return view

        async def _on_channel_save(save_inter: discord.Interaction, channel_ids: list) -> None:
            rl_key = (save_inter.user.id, "nm_welcome_channel")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await save_inter.response.defer(ephemeral=True)
            ok = await NewMemberActions.set_welcome_channel_from_list(guild.id, [str(c) for c in channel_ids])
            if ok:
                logger.info(f"Admin {save_inter.user} set NM welcome channel in guild {guild.id}")
                new_values = list(await NewMemberActions.get_welcome_channel_as_list(guild.id))
                await self._safe_edit_original(save_inter,view=_rebuild(new_values))
                await _auto_enable_feature_if_ready(save_inter, guild.id, [], feature_key="new_members")
            else:
                await save_inter.followup.send(view=build_notice_layout("Failed to save", "Could not save welcome channel."), ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            if rebuild_group_view is not None:
                layout = await rebuild_group_view()
                await back_inter.response.edit_message(view=layout)
            else:
                await back_inter.response.edit_message(
                    view=create_empty_layout("Welcome Channel configuration closed.")
                )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "nm_welcome_channel")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await clear_inter.response.defer(ephemeral=True)
            ok = await NewMemberActions.clear_welcome_channel(guild.id)
            if ok:
                logger.info(f"Admin {clear_inter.user} cleared NM welcome channel in guild {guild.id}")
                await self._safe_edit_original(clear_inter,view=_rebuild([]))
            else:
                await clear_inter.followup.send(view=build_notice_layout("Failed to clear", "Could not clear welcome channel."), ephemeral=True)

        async def _on_create_channel(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, channel_name: str) -> None:
                try:
                    new_channel = await guild.create_text_channel(
                        name=channel_name,
                        reason=f"Created via NM admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Missing Permissions",
                            "Missing permissions to create channels. Grant the bot **Manage Channels**.",
                        ),
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Failed to Create Channel",
                            f"Could not create the channel: {e}",
                        ),
                        ephemeral=True,
                    )
                    return

                await NewMemberActions.set_welcome_channel_from_list(guild.id, [str(new_channel.id)])
                logger.info(
                    f"Admin {btn_inter.user} created NM welcome channel '{new_channel.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_channel.id)]))
                await _auto_enable_feature_if_ready(modal_inter, guild.id, [], feature_key="new_members")

            await btn_inter.response.send_modal(NmCreateChannelModal(on_submit_callback=_on_modal_submit))

        current_values = list(await NewMemberActions.get_welcome_channel_as_list(guild.id))
        layout = _rebuild(current_values)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    async def _show_nm_whitelist_role_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show NM whitelist role configuration with Create Role support (edits msg2)."""
        if not await setup_gatekeeper.check_new_members_or_notify(interaction):
            return
        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            view = build_nm_whitelist_role_view(
                current_values=current,
                guild=guild,
                on_save=_on_role_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_role=_on_create_role,
            )
            if session:
                session.register_view(view)
            return view

        async def _on_role_save(save_inter: discord.Interaction, role_ids: list) -> None:
            rl_key = (save_inter.user.id, "nm_whitelist_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await save_inter.response.defer(ephemeral=True)
            ok = await NewMemberActions.set_whitelist_role_from_list(guild.id, [str(r) for r in role_ids])
            if ok:
                logger.info(f"Admin {save_inter.user} set NM whitelist role in guild {guild.id}")
                new_values = list(await NewMemberActions.get_whitelist_role_as_list(guild.id))
                await self._safe_edit_original(save_inter,view=_rebuild(new_values))
            else:
                await save_inter.followup.send(view=build_notice_layout("Failed to save", "Could not save whitelist role."), ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            if rebuild_group_view is not None:
                layout = await rebuild_group_view()
                await back_inter.response.edit_message(view=layout)
            else:
                await back_inter.response.edit_message(
                    view=create_empty_layout("Whitelist Role configuration closed.")
                )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "nm_whitelist_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    view=build_notice_layout(
                        "Slow Down",
                        "Saving too quickly — please wait a moment.",
                    ),
                    ephemeral=True,
                )
                return
            self._autosave_cooldowns[rl_key] = now
            self._autosave_cooldowns = {
                k: v for k, v in self._autosave_cooldowns.items()
                if v > now - 60.0
            }
            await clear_inter.response.defer(ephemeral=True)
            ok = await NewMemberActions.clear_whitelist_role(guild.id)
            if ok:
                logger.info(f"Admin {clear_inter.user} cleared NM whitelist role in guild {guild.id}")
                await self._safe_edit_original(clear_inter,view=_rebuild([]))
            else:
                await clear_inter.followup.send(view=build_notice_layout("Failed to clear", "Could not clear whitelist role."), ephemeral=True)

        async def _on_create_role(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, role_name: str) -> None:
                try:
                    new_role = await guild.create_role(
                        name=role_name,
                        reason=f"Created via NM admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Missing Permissions",
                            "Missing permissions to create roles. Grant the bot **Manage Roles**.",
                        ),
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        view=build_notice_layout(
                            "Failed to Create Role",
                            f"Could not create the role: {e}",
                        ),
                        ephemeral=True,
                    )
                    return

                await NewMemberActions.set_whitelist_role_from_list(guild.id, [str(new_role.id)])
                logger.info(
                    f"Admin {btn_inter.user} created NM whitelist role '{new_role.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_role.id)]))

            await btn_inter.response.send_modal(NmCreateRoleModal(on_submit_callback=_on_modal_submit))

        current_values = list(await NewMemberActions.get_whitelist_role_as_list(guild.id))
        layout = _rebuild(current_values)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== New Members Status ====================

    async def _show_nm_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the New Members configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        overview = await NewMemberActions.get_overview(interaction.guild.id)
        layout = build_new_member_status_view(overview, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)


    # ==================== Tag Tracker Settings ====================

    async def _show_tag_tracker_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show Tag Tracker settings (edits msg2 in place)."""
        import time
        last_refresh = [0.0]
        REFRESH_COOLDOWN = 2.0  # seconds between panel rebuilds

        async def rebuild_panel(src_interaction: discord.Interaction):
            """Rebuild the tag tracker panel in-place with fresh settings."""
            now = time.monotonic()
            if now - last_refresh[0] < REFRESH_COOLDOWN:
                return
            last_refresh[0] = now

            fresh_settings = await TrackerActions.get_tag_tracker_settings(interaction.guild.id)
            new_layout = build_tag_tracker_settings_view(
                fresh_settings, interaction.guild, on_toggle, on_role_select, on_edit_tag, on_detect_tag, on_cancel
            )
            try:
                await self._safe_edit_original(interaction,view=new_layout)
                attach_timeout_expiry_msg(new_layout, await interaction.original_response())
            except Exception as e:
                logger.debug(f"Could not refresh tag tracker panel: {e}")

        settings = await TrackerActions.get_tag_tracker_settings(interaction.guild.id)

        async def on_toggle(toggle_interaction: discord.Interaction, enabled: bool):
            await toggle_interaction.response.defer(ephemeral=True)
            success = await TrackerActions.set_tag_tracker_enabled(interaction.guild.id, enabled)
            if success:
                state = "enabled" if enabled else "disabled"
                logger.info(f"Admin {toggle_interaction.user} {state} tag tracker")
                await rebuild_panel(toggle_interaction)
            else:
                result = create_empty_layout("Failed to save tag tracker setting.")
                await toggle_interaction.followup.send(view=result, ephemeral=True)

        async def on_role_select(role_interaction: discord.Interaction, role_id: int):
            await role_interaction.response.defer(ephemeral=True)
            ok, err = check_role_permissions(interaction.guild, role_id, "tag_tracker_role")
            if not ok:
                await role_interaction.followup.send(err, ephemeral=True)
                return
            success = await TrackerActions.set_tag_tracker_role(interaction.guild.id, role_id)
            if success:
                role = interaction.guild.get_role(role_id)
                role_name = role.name if role else str(role_id)
                logger.info(f"Admin {role_interaction.user} set tag tracker role to {role_name}")
                await rebuild_panel(role_interaction)
            else:
                result = create_empty_layout("Failed to save tag tracker role.")
                await role_interaction.followup.send(view=result, ephemeral=True)

        async def on_edit_tag(edit_interaction: discord.Interaction):
            fresh = await TrackerActions.get_tag_tracker_settings(interaction.guild.id)
            current_tag = fresh.get("tag_tracker_server_tag") or ""

            async def modal_callback(modal_interaction: discord.Interaction, tag: str):
                await modal_interaction.response.defer(ephemeral=True)
                success = await TrackerActions.set_tag_tracker_server_tag(interaction.guild.id, tag)
                if success:
                    logger.info(f"Admin {modal_interaction.user} set server tag to {tag}")
                    await rebuild_panel(modal_interaction)
                else:
                    result = create_empty_layout("Failed to save server tag.")
                    await modal_interaction.followup.send(view=result, ephemeral=True)

            modal = TagTrackerServerTagModal(modal_callback, current_tag=current_tag)
            await edit_interaction.response.send_modal(modal)

        async def on_detect_tag(detect_interaction: discord.Interaction):
            await detect_interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            tag = None

            try:
                # Try 1: Check the admin's own primary_guild tag
                pg = getattr(detect_interaction.user, 'primary_guild', None)
                if pg and pg.id == guild.id and pg.tag:
                    tag = pg.tag
                    logger.debug(f"Tag detected from admin's primary_guild: {tag}")

                # Try 2: Fetch guild owner's member data and check their primary_guild
                if not tag:
                    try:
                        owner_data = await self.bot.http.get_member(guild.id, guild.owner_id)
                        owner_pg = (owner_data.get("user") or {}).get("primary_guild")
                        if owner_pg and owner_pg.get("tag"):
                            owner_guild_id = owner_pg.get("identity_guild_id")
                            if owner_guild_id and int(owner_guild_id) == guild.id:
                                tag = owner_pg["tag"]
                                logger.debug(f"Tag detected from guild owner's primary_guild: {tag}")
                    except Exception as e:
                        logger.debug(f"Could not fetch guild owner for tag detection: {e}")

                # Try 3: Legacy — check guild API for clan field (older API versions)
                if not tag:
                    try:
                        data = await self.bot.http.get_guild(guild.id)
                        clan = data.get("clan")
                        if clan and clan.get("tag"):
                            tag = clan["tag"]
                            logger.debug(f"Tag detected from guild clan field: {tag}")
                    except Exception as e:
                        logger.debug(f"Could not fetch guild data for tag detection: {e}")

                if tag:
                    success = await TrackerActions.set_tag_tracker_server_tag(guild.id, tag)
                    if success:
                        logger.info(f"Admin {detect_interaction.user} auto-detected server tag: {tag}")
                        await rebuild_panel(detect_interaction)
                    else:
                        result = create_empty_layout("Detected tag but failed to save.")
                        await detect_interaction.followup.send(view=result, ephemeral=True)
                else:
                    result = create_empty_layout(
                        "Could not auto-detect the server tag.\n\n"
                        "**Possible reasons:**\n"
                        "- The server tag hasn't been set yet (check **Server Settings > Identity**)\n"
                        "- The guild owner hasn't enabled their server tag badge\n\n"
                        "Use **Edit Server Tag** to enter the tag manually."
                    )
                    await detect_interaction.followup.send(view=result, ephemeral=True)
            except Exception as e:
                logger.error(f"Failed to detect server tag: {e}", exc_info=True)
                result = create_empty_layout("Failed to detect server tag. Check bot logs for details.")
                await detect_interaction.followup.send(view=result, ephemeral=True)

        async def on_cancel(cancel_interaction: discord.Interaction):
            if rebuild_group_view is not None:
                group_layout = await rebuild_group_view()
                await cancel_interaction.response.edit_message(view=group_layout)
            else:
                layout = create_empty_layout("Tag Tracker settings closed.")
                await cancel_interaction.response.edit_message(view=layout)

        layout = build_tag_tracker_settings_view(
            settings, interaction.guild, on_toggle, on_role_select, on_edit_tag, on_detect_tag, on_cancel
        )
        if session:
            session.register_view(layout)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== Boost Tracker Settings ====================

    async def _show_boost_tracker_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show Boost Tracker settings (edits msg2 in place)."""
        import time
        last_refresh = [0.0]
        REFRESH_COOLDOWN = 2.0

        async def rebuild_panel(src_interaction: discord.Interaction):
            """Rebuild the boost tracker panel in-place with fresh settings."""
            now = time.monotonic()
            if now - last_refresh[0] < REFRESH_COOLDOWN:
                return
            last_refresh[0] = now

            fresh_settings = await TrackerActions.get_boost_tracker_settings(interaction.guild.id)
            new_layout = build_boost_tracker_settings_view(
                fresh_settings, interaction.guild, on_toggle, on_channel_select, on_cancel
            )
            try:
                await self._safe_edit_original(interaction,view=new_layout)
                attach_timeout_expiry_msg(new_layout, await interaction.original_response())
            except Exception as e:
                logger.debug(f"Could not refresh boost tracker panel: {e}")

        settings = await TrackerActions.get_boost_tracker_settings(interaction.guild.id)

        async def on_toggle(toggle_interaction: discord.Interaction, enabled: bool):
            await toggle_interaction.response.defer(ephemeral=True)
            success = await TrackerActions.set_boost_enabled(interaction.guild.id, enabled)
            if success:
                state = "enabled" if enabled else "disabled"
                logger.info(f"Admin {toggle_interaction.user} {state} boost tracker")
                await rebuild_panel(toggle_interaction)
            else:
                result = create_empty_layout("Failed to save boost tracker setting.")
                await toggle_interaction.followup.send(view=result, ephemeral=True)

        async def on_channel_select(channel_interaction: discord.Interaction, channel_id: int):
            await channel_interaction.response.defer(ephemeral=True)
            ok, err = check_channel_permissions(interaction.guild, channel_id, "boost_tracker_channel")
            if not ok:
                await channel_interaction.followup.send(err, ephemeral=True)
                return
            success = await TrackerActions.set_boost_log_channel(interaction.guild.id, channel_id)
            if success:
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else str(channel_id)
                logger.info(f"Admin {channel_interaction.user} set boost log channel to {channel_name}")
                await rebuild_panel(channel_interaction)
            else:
                result = create_empty_layout("Failed to save boost log channel.")
                await channel_interaction.followup.send(view=result, ephemeral=True)

        async def on_cancel(cancel_interaction: discord.Interaction):
            if rebuild_group_view is not None:
                group_layout = await rebuild_group_view()
                await cancel_interaction.response.edit_message(view=group_layout)
            else:
                layout = create_empty_layout("Boost Tracker settings closed.")
                await cancel_interaction.response.edit_message(view=layout)

        layout = build_boost_tracker_settings_view(
            settings, interaction.guild, on_toggle, on_channel_select, on_cancel
        )
        if session:
            session.register_view(layout)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== Tracker Status ====================

    async def _show_tracker_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the tracker configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        overview = await TrackerActions.get_overview(interaction.guild.id)
        layout = build_tracker_status_view(overview, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)


    # ==================== Drops Channel ====================

    async def _show_drops_channel_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show Drops posting channel configuration (edits msg2 in place)."""
        guild = interaction.guild

        async def _rebuild() -> discord.ui.LayoutView:
            fresh = await DropsActions.get_drops_settings(guild.id)
            return build_drops_channel_view(fresh, guild, on_channel_select, on_cancel, on_toggle)

        async def on_channel_select(channel_interaction: discord.Interaction, channel_id: int):
            await channel_interaction.response.defer(ephemeral=True)
            ok, err = check_channel_permissions(guild, channel_id, "drops_channel")
            if not ok:
                await channel_interaction.followup.send(
                    view=build_notice_layout("Channel Not Allowed", err),
                    ephemeral=True,
                )
                return
            success = await DropsActions.set_drops_channel(guild.id, channel_id)
            if success:
                channel = guild.get_channel(channel_id)
                channel_name = channel.name if channel else str(channel_id)
                logger.info(f"Admin {channel_interaction.user} set drops channel to {channel_name}")

                # Auto-enable on first channel set
                if not await DropsActions.get_enabled(guild.id):
                    await DropsActions.set_enabled(guild.id, True)
                    logger.info(f"Drops auto-enabled for guild {guild.id} after channel set")

                await self._safe_edit_original(channel_interaction,view=await _rebuild())
            else:
                await channel_interaction.followup.send(
                    view=build_notice_layout(
                        "Failed to Save",
                        "Could not save drops channel.",
                    ),
                    ephemeral=True,
                )

        async def on_toggle(toggle_interaction: discord.Interaction):
            await toggle_interaction.response.defer(ephemeral=True)
            current = await DropsActions.get_enabled(guild.id)
            success = await DropsActions.set_enabled(guild.id, not current)
            if success:
                new_state = "disabled" if current else "enabled"
                logger.info(f"Admin {toggle_interaction.user} {new_state} drops for guild {guild.id}")
                await self._safe_edit_original(toggle_interaction,view=await _rebuild())
            else:
                await toggle_interaction.followup.send(
                    view=build_notice_layout(
                        "Failed to Toggle",
                        "Could not toggle drops state.",
                    ),
                    ephemeral=True,
                )

        async def on_cancel(cancel_interaction: discord.Interaction):
            if rebuild_group_view is not None:
                group_layout = await rebuild_group_view()
                await cancel_interaction.response.edit_message(view=group_layout)
            else:
                layout = create_empty_layout("Drops channel configuration closed.")
                await cancel_interaction.response.edit_message(view=layout)

        layout = build_drops_channel_view(
            await DropsActions.get_drops_settings(guild.id),
            guild,
            on_channel_select,
            on_cancel,
            on_toggle,
        )
        if session:
            session.register_view(layout)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== Drops Tracked Channels ====================

    async def _show_drops_tracker_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show Drops tracked channels configuration (edits msg2 in place)."""
        guild = interaction.guild

        async def _rebuild() -> discord.ui.LayoutView:
            fresh = await DropsActions.get_drops_settings(guild.id)
            return build_drops_tracker_view(fresh, guild, on_channel_select, on_remove, on_cancel)

        async def on_channel_select(channel_interaction: discord.Interaction, category: str, channel_id: int):
            await channel_interaction.response.defer(ephemeral=True)
            ok, err = check_channel_permissions(guild, channel_id, "drops_tracker")
            if not ok:
                await channel_interaction.followup.send(
                    view=build_notice_layout("Channel Not Allowed", err),
                    ephemeral=True,
                )
                return
            success = await DropsActions.set_tracker_channel(guild.id, category, channel_id)
            if success:
                channel = guild.get_channel(channel_id)
                channel_name = channel.name if channel else str(channel_id)
                logger.info(f"Admin {channel_interaction.user} set {category} tracker to {channel_name}")
                await self._safe_edit_original(channel_interaction,view=await _rebuild())
            else:
                await channel_interaction.followup.send(
                    view=build_notice_layout(
                        "Failed to Save",
                        f"Could not save {category} tracking channel.",
                    ),
                    ephemeral=True,
                )

        async def on_remove(remove_interaction: discord.Interaction, category: str):
            await remove_interaction.response.defer(ephemeral=True)
            success = await DropsActions.remove_tracker_channel(guild.id, category)
            if success:
                logger.info(f"Admin {remove_interaction.user} cleared {category} tracker channel")
                await self._safe_edit_original(remove_interaction,view=await _rebuild())
            else:
                await remove_interaction.followup.send(
                    view=build_notice_layout(
                        "Failed to Clear",
                        f"Could not clear {category} tracking channel.",
                    ),
                    ephemeral=True,
                )

        async def on_cancel(cancel_interaction: discord.Interaction):
            if rebuild_group_view is not None:
                group_layout = await rebuild_group_view()
                await cancel_interaction.response.edit_message(view=group_layout)
            else:
                layout = create_empty_layout("Tracked channels configuration closed.")
                await cancel_interaction.response.edit_message(view=layout)

        layout = build_drops_tracker_view(
            await DropsActions.get_drops_settings(guild.id), guild, on_channel_select, on_remove, on_cancel
        )
        if session:
            session.register_view(layout)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== Drops Manager Role ====================

    async def _show_drops_manager_role_menu(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show Drops manager role configuration (edits msg2 in place)."""
        from .views.base import AdminLayoutBuilder, cid

        guild = interaction.guild

        def _build_panel(current_role_id: int | None) -> discord.ui.LayoutView:
            if current_role_id:
                role = guild.get_role(current_role_id)
                role_display = role.mention if role else f"Not found ({current_role_id})"
            else:
                role_display = "Not configured"

            builder = AdminLayoutBuilder()
            builder.add_header("## Drops Manager Role")
            builder.add_text(
                f"**Current Role:** {role_display}\n\n"
                "Select a role below. Members with this role can use management\n"
                "features in `/drop` (Test Drops, View Unsent)."
            )
            builder.add_separator()

            role_select = discord.ui.RoleSelect(
                placeholder="Select manager role...",
                custom_id=cid("editor", "select", "drops_manager_role"),
                default_values=(
                    [discord.Object(id=int(current_role_id))] if current_role_id else []
                ),
            )
            role_select.callback = role_callback

            select_row = discord.ui.ActionRow()
            select_row.add_item(role_select)
            builder.add_item(select_row)

            done_btn = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id=cid("editor", "back", "drops_manager_role"),
            )
            done_btn.callback = done_callback

            btn_row = discord.ui.ActionRow()
            btn_row.add_item(done_btn)
            builder.add_item(btn_row)

            return builder.build()

        async def role_callback(role_interaction: discord.Interaction):
            selected_role_id = int(role_interaction.data["values"][0])
            await role_interaction.response.defer(ephemeral=True)
            success = await DropsActions.set_manager_role(guild.id, selected_role_id)
            if success:
                role = guild.get_role(selected_role_id)
                role_name = role.name if role else str(selected_role_id)
                logger.info(f"Admin {role_interaction.user} set drops manager role to {role_name}")
                await self._safe_edit_original(role_interaction,view=_build_panel(selected_role_id))
            else:
                await role_interaction.followup.send(
                    view=build_notice_layout(
                        "Failed to Save",
                        "Could not save drops manager role.",
                    ),
                    ephemeral=True,
                )

        async def done_callback(done_interaction: discord.Interaction):
            if rebuild_group_view is not None:
                group_layout = await rebuild_group_view()
                await done_interaction.response.edit_message(view=group_layout)
            else:
                layout = create_empty_layout("Manager role configuration closed.")
                await done_interaction.response.edit_message(view=layout)

        current_role_id = await DropsActions.get_manager_role(guild.id)
        layout = _build_panel(current_role_id)
        if session:
            session.register_view(layout)
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=layout)
        else:
            await self._safe_edit_original(interaction, view=layout)

    # ==================== Drops Status ====================

    async def _show_drops_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the Updates & Drops configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        overview = await DropsActions.get_overview(interaction.guild.id)
        layout = build_drops_status_view(overview, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    # ==================== Announcements ====================

    async def _show_ann_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the announcement configuration status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        overview = await AnnouncementActions.get_overview(interaction.guild.id)
        layout = build_announcement_status_view(overview, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    # ==================== Suggestions ====================

    async def _show_sug_update_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Open the status-update modal for a suggestion.

        send_modal IS the interaction response, so msg2 stays on the group
        menu (no edit needed). Result notice is delivered as a followup.
        """
        async def on_modal_submit(
            modal_interaction: discord.Interaction,
            suggestion_id: str,
            status: str,
            reason: str,
        ):
            await modal_interaction.response.defer(ephemeral=True)
            result = await SuggestionActions.update_suggestion_status(
                guild_id=modal_interaction.guild.id,
                suggestion_id_prefix=suggestion_id,
                status=status,
                admin_id=modal_interaction.user.id,
                reason=reason,
                bot=self.bot,
            )
            if not result["success"]:
                await modal_interaction.followup.send(
                    view=build_notice_layout(
                        "Update Failed",
                        result["message"],
                    ),
                    ephemeral=True,
                )

        modal = SuggestionStatusUpdateModal(callback=on_modal_submit)
        await interaction.response.send_modal(modal)

    async def _show_sug_export(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the export format picker for suggestions (edits msg2 in place)."""
        async def on_export(export_interaction: discord.Interaction, format_type: str):
            await export_interaction.response.defer(ephemeral=True)
            result = await SuggestionActions.export_suggestions(
                guild_id=export_interaction.guild.id,
                format_type=format_type,
            )
            if result is None:
                await export_interaction.followup.send(
                    view=build_notice_layout(
                        "Nothing to Export",
                        "There are no suggestions to export yet.",
                    ),
                    ephemeral=True,
                )
                return
            file, count = result
            await export_interaction.followup.send(
                file=file,
                ephemeral=True,
            )

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        layout = build_suggestion_export_view(export_callback=on_export)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    async def _show_sug_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the suggestion system status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        overview = await SuggestionActions.get_overview(interaction.guild.id, bot=self.bot)
        layout = build_suggestion_status_view(overview, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    # ==================== Guide Panel Handlers ====================

    async def _show_guide_status(
        self,
        interaction: discord.Interaction,
        *,
        parent_node: PanelNode | None = None,
        rebuild_group_view: Callable[[], Awaitable[discord.ui.LayoutView]] | None = None,
        session: PanelSession | None = None,
    ):
        """Show the Guide system status (edits msg2 in place)."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        status = await GuideActions.get_guide_status(interaction.guild.id)
        layout = self._build_guide_status_view(status, interaction.guild)
        self._attach_back_to_group(layout, parent_node, rebuild_group_view=rebuild_group_view)
        if session:
            session.register_view(layout)
        await self._safe_edit_original(interaction, view=layout)

    @staticmethod
    def _build_guide_status_view(status: dict, guild: discord.Guild) -> discord.ui.LayoutView:
        layout = discord.ui.LayoutView(timeout=None)
        layout.add_item(discord.ui.TextDisplay("## 📖 Guide System Status"))
        layout.add_item(discord.ui.Separator())

        enabled = "✅ Enabled" if status["enabled"] else "❌ Disabled"
        channel = f"<#{status['channel_id']}>" if status["channel_id"] else "Any channel"
        has_custom = "✅ Custom guide uploaded" if status["has_custom_guide"] else "📄 Using default template"
        page_count = status.get("page_count", 0)

        lines = [
            f"**Status:** {enabled}",
            f"**Channel:** {channel}",
            f"**Guide:** {has_custom}",
            f"**Pages:** {page_count}",
        ]
        if status.get("updated_at"):
            lines.append(f"**Last updated:** <t:{int(status['updated_at'].timestamp())}:R>")

        layout.add_item(discord.ui.TextDisplay("\n".join(lines)))
        return layout


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    setup_gatekeeper.set_embed_checker(EmbedConfigActions.has_any_tier_configured)
    await bot.add_cog(AdminCog(bot))
    logger.info("AdminCog loaded with embed config panel")
