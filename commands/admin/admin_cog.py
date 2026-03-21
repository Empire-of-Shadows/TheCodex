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
from .views import (
    build_main_panel,
    build_subcategory_panel,
    attach_timeout_expiry,
    attach_timeout_expiry_msg,
    PANEL_GROUPS,
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
    _auto_enable_feature_if_ready,
)
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
        default_permissions=discord.Permissions(manage_guild=True)
    )

    # ==================== Master Admin Panel ====================

    @admin_group.command(name="panel", description="Open the admin configuration panel")
    async def admin_panel(self, interaction: discord.Interaction):
        """Open the admin configuration panel with two-level navigation."""
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True
            )
            return

        logger.info(f"Admin panel opened by {interaction.user} in guild {interaction.guild.id}")

        # Lookup for group keys -> display labels
        group_labels = {key: label for key, label, _ in PANEL_GROUPS}

        # Embed Settings subcategories that require Role Tier Mapping to be configured first
        _EMBED_GATED_KEYS = {"description_limits", "color_tiers", "feature_access", "status"}

        # WYR Settings subcategories that require the WYR channel to be configured first
        _WYR_GATED_KEYS = {"wyr_ping_role", "wyr_schedule", "wyr_category", "wyr_thread", "wyr_cleanup"}

        # New Members subcategories that require the welcome channel to be configured first
        _NM_GATED_KEYS = {"nm_welcome_builder", "nm_settings", "nm_whitelist_role"}

        # Shared mutable container so subcategory_callback can reach group_callback's refresh fn
        _refresh_subcategory: list = [None]
        # Shared state for in-place unlock: current subcategory panel context and lock state
        _subcategory_panel_ctx: list = [None]           # Holds (group, label, back_callback)
        _current_locked_keys_shared: list[set] = [set()]  # Tracks lock state of current subcategory panel

        # Subcategory routing - dispatches to existing _show_* methods
        async def subcategory_callback(sub_interaction: discord.Interaction, subcategory: str):
            guild_id = sub_interaction.guild.id

            if subcategory in _EMBED_GATED_KEYS:
                if not await setup_gatekeeper.is_embed_setup_complete(guild_id):
                    await setup_gatekeeper.check_embed_or_notify(sub_interaction)
                    return
                # Requirements met — unlock panel if it was still showing a lock for this key
                if subcategory in _current_locked_keys_shared[0]:
                    ctx = _subcategory_panel_ctx[0]
                    if ctx:
                        grp, lbl, back_cb = ctx
                        unlocked_layout = build_subcategory_panel(
                            grp, lbl, interaction.user,
                            subcategory_callback, back_cb,
                            locked_keys=set(),
                        )
                        await sub_interaction.response.edit_message(view=unlocked_layout)
                        _current_locked_keys_shared[0] = set()
                        setup_gatekeeper.invalidate_embed(guild_id)

            elif subcategory in _WYR_GATED_KEYS:
                if not await setup_gatekeeper.is_wyr_setup_complete(guild_id):
                    await setup_gatekeeper.check_wyr_or_notify(sub_interaction)
                    return
                # Requirements met — unlock panel if it was still showing a lock for this key
                if subcategory in _current_locked_keys_shared[0]:
                    ctx = _subcategory_panel_ctx[0]
                    if ctx:
                        grp, lbl, back_cb = ctx
                        unlocked_layout = build_subcategory_panel(
                            grp, lbl, interaction.user,
                            subcategory_callback, back_cb,
                            locked_keys=set(),
                        )
                        await sub_interaction.response.edit_message(view=unlocked_layout)
                        _current_locked_keys_shared[0] = set()
                        setup_gatekeeper.invalidate_wyr(guild_id)

            elif subcategory in _NM_GATED_KEYS:
                if not await setup_gatekeeper.is_new_members_setup_complete(guild_id):
                    await setup_gatekeeper.check_new_members_or_notify(sub_interaction)
                    return
                # Requirements met — unlock panel if it was still showing a lock for this key
                if subcategory in _current_locked_keys_shared[0]:
                    ctx = _subcategory_panel_ctx[0]
                    if ctx:
                        grp, lbl, back_cb = ctx
                        unlocked_layout = build_subcategory_panel(
                            grp, lbl, interaction.user,
                            subcategory_callback, back_cb,
                            locked_keys=set(),
                        )
                        await sub_interaction.response.edit_message(view=unlocked_layout)
                        _current_locked_keys_shared[0] = set()
                        setup_gatekeeper.invalidate_new_members(guild_id)

            refresh = _refresh_subcategory[0]
            handlers = {
                "role_tiers": self._show_role_tiers_menu,
                "description_limits": self._show_description_limits_menu,
                "color_tiers": self._show_color_sets_menu,
                "feature_access": self._show_feature_access_menu,
                "status": self._show_status,
                "wyr_channel": self._show_wyr_channel_menu,
                "wyr_ping_role": self._show_wyr_ping_role_menu,
                "wyr_schedule": self._show_wyr_schedule_menu,
                "wyr_category": self._show_wyr_category_menu,
                "wyr_thread": self._show_wyr_thread_menu,
                "wyr_cleanup": self._show_wyr_cleanup_menu,
                "wyr_status": self._show_wyr_status,
                "nm_settings": self._show_nm_settings_menu,
                "nm_welcome_channel": self._show_nm_welcome_channel_menu,
                "nm_whitelist_role": self._show_nm_whitelist_role_menu,
                "nm_welcome_builder": self._show_nm_welcome_text_menu,
                "nm_status": self._show_nm_status,
                "tag_tracker": self._show_tag_tracker_menu,
                "boost_tracker": self._show_boost_tracker_menu,
                "tracker_status": self._show_tracker_status,
                "drops_channel": self._show_drops_channel_menu,
                "drops_tracker": self._show_drops_tracker_menu,
                "drops_manager_role": self._show_drops_manager_role_menu,
                "drops_status": self._show_drops_status,
                "ann_channel": self._show_ann_channel_menu,
                "ann_settings": self._show_ann_settings_menu,
                "ann_status": self._show_ann_status,
                "sug_channel": self._show_sug_channel_menu,
                "sug_status": self._show_sug_status,
                "guide_channel": self._show_guide_channel_menu,
                "guide_upload": self._show_guide_upload_menu,
                "guide_enabled": self._show_guide_enabled_menu,
                "guide_status": self._show_guide_status,
            }
            handler = handlers.get(subcategory)
            if handler:
                if subcategory in ("role_tiers", "wyr_channel") and refresh:
                    await handler(sub_interaction, refresh_parent=refresh)
                else:
                    await handler(sub_interaction)

        # Group selection callback - shows subcategory panel for selected group
        async def group_callback(group_interaction: discord.Interaction, group: str):
            label = group_labels.get(group, group)

            async def back_callback(back_interaction: discord.Interaction):
                layout = attach_timeout_expiry(build_main_panel(interaction.user, group_callback), interaction)
                await back_interaction.response.edit_message(view=layout)

            locked_keys: set[str] = set()
            if group == "embed_settings":
                if not await setup_gatekeeper.is_embed_setup_complete(group_interaction.guild.id):
                    locked_keys = _EMBED_GATED_KEYS
            elif group == "wyr_settings":
                if not await setup_gatekeeper.is_wyr_setup_complete(group_interaction.guild.id):
                    locked_keys = _WYR_GATED_KEYS
            elif group == "new_members":
                if not await setup_gatekeeper.is_new_members_setup_complete(group_interaction.guild.id):
                    locked_keys = _NM_GATED_KEYS

            layout = attach_timeout_expiry(
                build_subcategory_panel(
                    group, label, interaction.user, subcategory_callback, back_callback,
                    locked_keys=locked_keys,
                ),
                interaction,
            )
            await group_interaction.response.edit_message(view=layout)

            _subcategory_panel_ctx[0] = (group, label, back_callback)
            _current_locked_keys_shared[0] = locked_keys

            # Track what's currently shown so we only edit when lock state changes
            _current_locked_keys: list[set] = [locked_keys]

            async def refresh_subcategory() -> None:
                new_locked_keys: set[str] = set()
                if group == "embed_settings":
                    if not await setup_gatekeeper.is_embed_setup_complete(group_interaction.guild.id):
                        new_locked_keys = _EMBED_GATED_KEYS
                elif group == "wyr_settings":
                    if not await setup_gatekeeper.is_wyr_setup_complete(group_interaction.guild.id):
                        new_locked_keys = _WYR_GATED_KEYS
                elif group == "new_members":
                    if not await setup_gatekeeper.is_new_members_setup_complete(group_interaction.guild.id):
                        new_locked_keys = _NM_GATED_KEYS

                if new_locked_keys == _current_locked_keys[0]:
                    return  # No visual change needed

                new_layout = attach_timeout_expiry(
                    build_subcategory_panel(
                        group, label, interaction.user, subcategory_callback, back_callback,
                        locked_keys=new_locked_keys,
                    ),
                    interaction,
                )
                try:
                    await group_interaction.edit_original_response(view=new_layout)
                    _current_locked_keys[0] = new_locked_keys
                    _current_locked_keys_shared[0] = new_locked_keys
                    logger.info(
                        f"Guild {group_interaction.guild.id}: subcategory panel lock state updated "
                        f"({'locked' if new_locked_keys else 'unlocked'})"
                    )
                except Exception as e:
                    logger.debug(f"Could not refresh subcategory panel after lock state change: {e}")

            _refresh_subcategory[0] = refresh_subcategory

        layout = attach_timeout_expiry(build_main_panel(interaction.user, group_callback), interaction)
        await interaction.response.send_message(view=layout, ephemeral=True)

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
                if child.get_values:
                    try:
                        summary_map[key] = list(await child.get_values(guild.id))
                    except Exception:
                        summary_map[key] = []
                else:
                    summary_map[key] = []

            async def on_select(sel_interaction: discord.Interaction, child_key: str):
                child = node.children.get(child_key)
                if not child:
                    return

                # Per-setting pre-check gate (e.g. tier-readiness for description limits).
                # pre_check returns an Embed (blocked) or None (allowed).
                # edit_message fires first to reset the dropdown, then followup for the notice.
                if child.pre_check:
                    denied_embed = await child.pre_check(sel_interaction, guild.id)
                    if denied_embed is not None:
                        refreshed = build_menu_view(node, summary_map, on_select, on_cancel)
                        await sel_interaction.response.edit_message(view=refreshed)
                        await sel_interaction.followup.send(embed=denied_embed, ephemeral=True)
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
                                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                                            "Too many attempts — please wait a moment.", ephemeral=True
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
                                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                                if c.get_values:
                                    try:
                                        new_summary_map[key] = list(await c.get_values(guild.id))
                                    except Exception:
                                        new_summary_map[key] = []
                                else:
                                    new_summary_map[key] = []
                            new_menu_layout = build_menu_view(node, new_summary_map, on_select, on_cancel)
                            await sel_interaction.edit_original_response(view=new_menu_layout)
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
                    await self._navigate_to(
                        sel_interaction, child, guild,
                        parent_node=node, edit=True,
                        refresh_parent=refresh_parent,
                    )

            async def on_cancel(cancel_interaction: discord.Interaction):
                await cancel_interaction.response.edit_message(
                    view=create_empty_layout(f"{node.label} configuration closed.")
                )

            layout = build_menu_view(node, summary_map, on_select, on_cancel)
            if interaction.response.is_done():
                if edit:
                    await interaction.edit_original_response(view=layout)
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
                    await save_interaction.edit_original_response(view=new_layout)
                    if node.post_save_hook:
                        await node.post_save_hook(save_interaction, guild.id, values)
                    if refresh_parent:
                        await refresh_parent()
                else:
                    await save_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back(back_interaction: discord.Interaction):
                if parent_node:
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
                        await clear_interaction.edit_original_response(view=new_layout)
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
                    await interaction.edit_original_response(view=layout)
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
                    await button_interaction.edit_original_response(view=new_layout)
                else:
                    await modal_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back_modal(back_interaction: discord.Interaction):
                if parent_node:
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
                        await clear_interaction.edit_original_response(view=new_layout)
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
                    await interaction.edit_original_response(view=layout)
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
                    await button_interaction.edit_original_response(view=new_layout)
                else:
                    await modal_interaction.followup.send(
                        view=create_empty_layout(f"Failed to save **{node.label}**."), ephemeral=True
                    )

            async def on_back_dual(back_interaction: discord.Interaction):
                if parent_node:
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
                    await interaction.edit_original_response(view=layout)
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
                if parent_node:
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
                        await clear_interaction.edit_original_response(view=new_layout)
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
                        await modal_interaction.followup.send("Please upload a `.json` file.", ephemeral=True)
                        return
                    if attachment.size > 50_000:
                        await modal_interaction.followup.send("File too large (max 50 KB).", ephemeral=True)
                        return
                    try:
                        raw = (await attachment.read()).decode("utf-8")
                    except Exception as exc:
                        await modal_interaction.followup.send(f"Could not read file: {exc}", ephemeral=True)
                        return
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        await modal_interaction.followup.send(f"Invalid JSON: {exc}", ephemeral=True)
                        return
                    if node.schema_validator:
                        ok, err_msg = node.schema_validator(data)
                        if not ok:
                            await modal_interaction.followup.send(f"Schema error: {err_msg}", ephemeral=True)
                            return
                    rl_key = (button_interaction.user.id, node.key)
                    now = time.monotonic()
                    if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                        await modal_interaction.followup.send("Saving too quickly — wait a moment.", ephemeral=True)
                        return
                    self._autosave_cooldowns[rl_key] = now
                    success = await node.set_values(guild.id, [raw])
                    if success:
                        logger.info(f"Admin {button_interaction.user} uploaded {node.key} in guild {guild.id}")
                        new_layout = build_file_upload_status_view(
                            node, [raw], guild, on_back_fu, on_clear_fu, back_label, on_upload_fu
                        )
                        await button_interaction.edit_original_response(view=new_layout)
                        if refresh_parent:
                            await refresh_parent()
                    else:
                        await modal_interaction.followup.send("❌ Failed to save config.", ephemeral=True)

            layout = build_file_upload_status_view(node, current_values, guild, on_back_fu, on_clear_fu, back_label, on_upload_fu)
            if interaction.response.is_done():
                if edit:
                    await interaction.edit_original_response(view=layout)
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

    # ==================== Role Tier Mapping ====================

    async def _show_role_tiers_menu(self, interaction: discord.Interaction, *, refresh_parent=None):
        """Show role tier mapping management (engine-driven)."""
        await self._navigate_to(interaction, ROLE_TIER_CONFIG, interaction.guild, refresh_parent=refresh_parent)

    # ==================== Description Limits ====================

    async def _show_description_limits_menu(self, interaction: discord.Interaction):
        """Show description limits management (engine-driven)."""
        await self._navigate_to(interaction, DESCRIPTION_LIMITS_CONFIG, interaction.guild)

    # ==================== Color Sets ====================

    async def _show_color_sets_menu(self, interaction: discord.Interaction) -> None:
        """Show the Color Sets management panel (replaces legacy Color Tiers)."""
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
                await nav_interaction.edit_original_response(view=view)
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
                await done_inter.response.edit_message(
                    view=create_empty_layout("Color Sets configuration closed.")
                )

            view = build_color_sets_menu(
                sets, assignment_counts, default_color, tier_per_set,
                on_create, on_select_set, on_change_default, on_done,
            )
            await modal_inter.edit_original_response(view=view)

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
                    await rm_inter.response.send_message("Color not found.", ephemeral=True)
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
                            "Saving too quickly — please wait a moment.", ephemeral=True
                        )
                        return
                    self._autosave_cooldowns[rl_key] = now

                    # Block assignment if the target tier has no roles configured.
                    # edit_message fires first to reset the select, then followup for the notice.
                    denied_embed = await setup_gatekeeper.get_tier_gate_embed(guild_id, tier_name)
                    if denied_embed is not None:
                        await sel_inter.response.edit_message(
                            view=build_tier_assign_view(color_set["name"], on_tier_selected, on_tier_back)
                        )
                        await sel_inter.followup.send(embed=denied_embed, ephemeral=True)
                        return

                    # Check tier exclusivity — one set can only be assigned to one tier
                    conflict = await check_tier_exclusivity(guild_id, set_id, tier_name)
                    if conflict.status == "breaking":
                        await sel_inter.response.send_message(
                            conflict.message, ephemeral=True
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
                await nav_interaction.edit_original_response(view=view)
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

            view = build_default_color_setup_view(on_set_default)
            if edit == "followup":
                msg = await nav_inter.followup.send(view=view, ephemeral=True)
                attach_timeout_expiry_msg(view, msg)
            elif edit == "original":
                await nav_inter.edit_original_response(view=view)
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
        default_color = await ColorSetActions.get_default_color(guild_id)
        initial_edit = "followup" if interaction.response.is_done() else False
        if default_color is None:
            await _show_default_setup(interaction, edit=initial_edit)
        else:
            await _render_menu(interaction, edit=initial_edit)

    # ==================== Feature Access ====================

    async def _show_feature_access_menu(self, interaction: discord.Interaction):
        """Show feature access management (engine-driven)."""
        await self._navigate_to(interaction, FEATURE_ACCESS_CONFIG, interaction.guild)

    # ==================== Status ====================

    async def _show_status(self, interaction: discord.Interaction):
        """Show the embed configuration status."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        stats = await EmbedConfigActions.get_overview(interaction.guild.id)
        layout = build_embed_status_view(stats, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)

    # ==================== WYR Channel ====================

    async def _show_wyr_channel_menu(self, interaction: discord.Interaction, *, refresh_parent=None):
        """Show WYR channel configuration."""
        await self._navigate_to(interaction, WYR_CHANNEL_CONFIG, interaction.guild, refresh_parent=refresh_parent)

    # ==================== WYR Ping Role ====================

    async def _show_wyr_ping_role_menu(self, interaction: discord.Interaction):
        """Show WYR ping role configuration with Create Role support."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return

        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            return build_wyr_ping_role_view(
                current_values=current,
                guild=guild,
                on_save=_on_role_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_role=_on_create_role,
            )

        async def _on_role_save(save_inter: discord.Interaction, role_ids: list) -> None:
            rl_key = (save_inter.user.id, "wyr_ping_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await save_inter.edit_original_response(view=_rebuild(new_values))
            else:
                await save_inter.followup.send("Failed to save WYR ping role.", ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            await back_inter.response.edit_message(
                view=create_empty_layout("WYR Ping Role configuration closed.")
            )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "wyr_ping_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await clear_inter.edit_original_response(view=_rebuild([]))
            else:
                await clear_inter.followup.send("Failed to clear WYR ping role.", ephemeral=True)

        async def _on_create_role(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, role_name: str) -> None:
                try:
                    new_role = await guild.create_role(
                        name=role_name,
                        reason=f"Created via WYR admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        "❌ Missing permissions to create roles. Grant the bot **Manage Roles**.",
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        f"❌ Failed to create role: {e}", ephemeral=True
                    )
                    return

                await WYRConfigActions.set_ping_role(guild.id, [str(new_role.id)])
                logger.info(
                    f"Admin {btn_inter.user} created WYR ping role '{new_role.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_role.id)]))
                await modal_inter.followup.send(
                    f"✅ **{new_role.name}** created and set as the WYR ping role.\n"
                    "-# Head to **Server Settings → Roles** to set its color, icon, and position.",
                    ephemeral=True,
                )

            await btn_inter.response.send_modal(WyrCreateRoleModal(on_submit_callback=_on_modal_submit))

        current_values = list(await WYRConfigActions.get_ping_role(guild.id))
        await interaction.response.send_message(view=_rebuild(current_values), ephemeral=True)

    # ==================== WYR Schedule ====================

    async def _show_wyr_schedule_menu(self, interaction: discord.Interaction):
        """Show WYR schedule configuration."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return
        await self._navigate_to(interaction, WYR_SCHEDULE_CONFIG, interaction.guild)

    # ==================== WYR Category ====================

    async def _show_wyr_category_menu(self, interaction: discord.Interaction):
        """Show WYR category configuration."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return
        await self._navigate_to(interaction, WYR_CATEGORY_CONFIG, interaction.guild)

    # ==================== WYR Thread Settings ====================

    async def _show_wyr_thread_menu(self, interaction: discord.Interaction):
        """Show WYR thread settings configuration."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return
        await self._navigate_to(interaction, WYR_THREAD_CONFIG, interaction.guild)

    # ==================== WYR Cleanup ====================

    async def _show_wyr_cleanup_menu(self, interaction: discord.Interaction):
        """Show WYR cleanup configuration."""
        if not await setup_gatekeeper.check_wyr_or_notify(interaction):
            return
        await self._navigate_to(interaction, WYR_CLEANUP_CONFIG, interaction.guild)

    # ==================== WYR Status ====================

    async def _show_wyr_status(self, interaction: discord.Interaction):
        """Show the WYR configuration status."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        stats = await WYRConfigActions.get_overview(interaction.guild.id)
        layout = build_wyr_status_view(stats, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)


    # ==================== New Members Settings ====================

    async def _show_nm_settings_menu(self, interaction: discord.Interaction):
        if not await setup_gatekeeper.check_new_members_or_notify(interaction):
            return
        await self._navigate_to(interaction, NM_SETTINGS_CONFIG, interaction.guild)

    async def _show_nm_welcome_channel_menu(self, interaction: discord.Interaction):
        """Show NM welcome channel configuration with Create Channel support."""
        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            return build_nm_welcome_channel_view(
                current_values=current,
                guild=guild,
                on_save=_on_channel_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_channel=_on_create_channel,
            )

        async def _on_channel_save(save_inter: discord.Interaction, channel_ids: list) -> None:
            rl_key = (save_inter.user.id, "nm_welcome_channel")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await save_inter.edit_original_response(view=_rebuild(new_values))
                await _auto_enable_feature_if_ready(save_inter, guild.id, [], feature_key="new_members")
            else:
                await save_inter.followup.send("Failed to save welcome channel.", ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            await back_inter.response.edit_message(
                view=create_empty_layout("Welcome Channel configuration closed.")
            )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "nm_welcome_channel")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await clear_inter.edit_original_response(view=_rebuild([]))
            else:
                await clear_inter.followup.send("Failed to clear welcome channel.", ephemeral=True)

        async def _on_create_channel(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, channel_name: str) -> None:
                try:
                    new_channel = await guild.create_text_channel(
                        name=channel_name,
                        reason=f"Created via NM admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        "❌ Missing permissions to create channels. Grant the bot **Manage Channels**.",
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        f"❌ Failed to create channel: {e}", ephemeral=True
                    )
                    return

                await NewMemberActions.set_welcome_channel_from_list(guild.id, [str(new_channel.id)])
                logger.info(
                    f"Admin {btn_inter.user} created NM welcome channel '{new_channel.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_channel.id)]))
                await modal_inter.followup.send(
                    f"✅ **#{new_channel.name}** created and set as the welcome channel.\n"
                    "-# Head to **Server Settings → Channels** to set its category and permissions.",
                    ephemeral=True,
                )
                await _auto_enable_feature_if_ready(modal_inter, guild.id, [], feature_key="new_members")

            await btn_inter.response.send_modal(NmCreateChannelModal(on_submit_callback=_on_modal_submit))

        current_values = list(await NewMemberActions.get_welcome_channel_as_list(guild.id))
        await interaction.response.send_message(view=_rebuild(current_values), ephemeral=True)

    async def _show_nm_whitelist_role_menu(self, interaction: discord.Interaction):
        """Show NM whitelist role configuration with Create Role support."""
        if not await setup_gatekeeper.check_new_members_or_notify(interaction):
            return
        guild = interaction.guild

        def _rebuild(current: list) -> discord.ui.LayoutView:
            return build_nm_whitelist_role_view(
                current_values=current,
                guild=guild,
                on_save=_on_role_save,
                on_back=_on_back,
                on_clear=_on_clear,
                on_create_role=_on_create_role,
            )

        async def _on_role_save(save_inter: discord.Interaction, role_ids: list) -> None:
            rl_key = (save_inter.user.id, "nm_whitelist_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await save_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await save_inter.edit_original_response(view=_rebuild(new_values))
            else:
                await save_inter.followup.send("Failed to save whitelist role.", ephemeral=True)

        async def _on_back(back_inter: discord.Interaction) -> None:
            await back_inter.response.edit_message(
                view=create_empty_layout("Whitelist Role configuration closed.")
            )

        async def _on_clear(clear_inter: discord.Interaction) -> None:
            rl_key = (clear_inter.user.id, "nm_whitelist_role")
            now = time.monotonic()
            if now - self._autosave_cooldowns.get(rl_key, 0.0) < self.AUTOSAVE_COOLDOWN:
                await clear_inter.response.send_message(
                    "Saving too quickly — please wait a moment.", ephemeral=True
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
                await clear_inter.edit_original_response(view=_rebuild([]))
            else:
                await clear_inter.followup.send("Failed to clear whitelist role.", ephemeral=True)

        async def _on_create_role(btn_inter: discord.Interaction) -> None:
            async def _on_modal_submit(modal_inter: discord.Interaction, role_name: str) -> None:
                try:
                    new_role = await guild.create_role(
                        name=role_name,
                        reason=f"Created via NM admin panel by {btn_inter.user}",
                    )
                except discord.Forbidden:
                    await modal_inter.response.send_message(
                        "❌ Missing permissions to create roles. Grant the bot **Manage Roles**.",
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await modal_inter.response.send_message(
                        f"❌ Failed to create role: {e}", ephemeral=True
                    )
                    return

                await NewMemberActions.set_whitelist_role_from_list(guild.id, [str(new_role.id)])
                logger.info(
                    f"Admin {btn_inter.user} created NM whitelist role '{new_role.name}' in guild {guild.id}"
                )
                await modal_inter.response.edit_message(view=_rebuild([str(new_role.id)]))
                await modal_inter.followup.send(
                    f"✅ **{new_role.name}** created and set as the whitelist role.\n"
                    "-# Head to **Server Settings → Roles** to set its color, icon, and position.",
                    ephemeral=True,
                )

            await btn_inter.response.send_modal(NmCreateRoleModal(on_submit_callback=_on_modal_submit))

        current_values = list(await NewMemberActions.get_whitelist_role_as_list(guild.id))
        await interaction.response.send_message(view=_rebuild(current_values), ephemeral=True)

    async def _show_nm_welcome_text_menu(self, interaction: discord.Interaction):
        if not await setup_gatekeeper.check_new_members_or_notify(interaction):
            return
        await self._navigate_to(interaction, NM_WELCOME_TEXT_CONFIG, interaction.guild)

    # ==================== New Members Status ====================

    async def _show_nm_status(self, interaction: discord.Interaction):
        """Show the New Members configuration status."""
        await interaction.response.defer(ephemeral=True)

        overview = await NewMemberActions.get_overview(interaction.guild.id)
        layout = build_new_member_status_view(overview, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)


    # ==================== Tag Tracker Settings ====================

    async def _show_tag_tracker_menu(self, interaction: discord.Interaction):
        """Show Tag Tracker settings."""
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
                await interaction.edit_original_response(view=new_layout)
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
            layout = create_empty_layout("Tag Tracker settings closed.")
            await cancel_interaction.response.edit_message(view=layout)

        layout = build_tag_tracker_settings_view(
            settings, interaction.guild, on_toggle, on_role_select, on_edit_tag, on_detect_tag, on_cancel
        )
        await interaction.response.send_message(view=layout, ephemeral=True)
        msg = await interaction.original_response()
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Boost Tracker Settings ====================

    async def _show_boost_tracker_menu(self, interaction: discord.Interaction):
        """Show Boost Tracker settings."""
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
                await interaction.edit_original_response(view=new_layout)
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
            layout = create_empty_layout("Boost Tracker settings closed.")
            await cancel_interaction.response.edit_message(view=layout)

        layout = build_boost_tracker_settings_view(
            settings, interaction.guild, on_toggle, on_channel_select, on_cancel
        )
        await interaction.response.send_message(view=layout, ephemeral=True)
        msg = await interaction.original_response()
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Tracker Status ====================

    async def _show_tracker_status(self, interaction: discord.Interaction):
        """Show the tracker configuration status."""
        await interaction.response.defer(ephemeral=True)

        overview = await TrackerActions.get_overview(interaction.guild.id)
        layout = build_tracker_status_view(overview, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)


    # ==================== Drops Channel ====================

    async def _show_drops_channel_menu(self, interaction: discord.Interaction):
        """Show Drops posting channel configuration."""
        guild = interaction.guild

        async def _rebuild() -> discord.ui.LayoutView:
            fresh = await DropsActions.get_drops_settings(guild.id)
            return build_drops_channel_view(fresh, guild, on_channel_select, on_cancel)

        async def on_channel_select(channel_interaction: discord.Interaction, channel_id: int):
            await channel_interaction.response.defer(ephemeral=True)
            ok, err = check_channel_permissions(guild, channel_id, "drops_channel")
            if not ok:
                await channel_interaction.followup.send(err, ephemeral=True)
                return
            success = await DropsActions.set_drops_channel(guild.id, channel_id)
            if success:
                channel = guild.get_channel(channel_id)
                channel_name = channel.name if channel else str(channel_id)
                logger.info(f"Admin {channel_interaction.user} set drops channel to {channel_name}")
                await channel_interaction.edit_original_response(view=await _rebuild())
            else:
                await channel_interaction.followup.send(
                    view=create_empty_layout("Failed to save drops channel."), ephemeral=True
                )

        async def on_cancel(cancel_interaction: discord.Interaction):
            layout = create_empty_layout("Drops channel configuration closed.")
            await cancel_interaction.response.edit_message(view=layout)

        layout = build_drops_channel_view(
            await DropsActions.get_drops_settings(guild.id), guild, on_channel_select, on_cancel
        )
        await interaction.response.send_message(view=layout, ephemeral=True)
        msg = await interaction.original_response()
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Drops Tracked Channels ====================

    async def _show_drops_tracker_menu(self, interaction: discord.Interaction):
        """Show Drops tracked channels configuration."""
        guild = interaction.guild

        async def _rebuild() -> discord.ui.LayoutView:
            fresh = await DropsActions.get_drops_settings(guild.id)
            return build_drops_tracker_view(fresh, guild, on_channel_select, on_remove, on_cancel)

        async def on_channel_select(channel_interaction: discord.Interaction, category: str, channel_id: int):
            await channel_interaction.response.defer(ephemeral=True)
            ok, err = check_channel_permissions(guild, channel_id, "drops_tracker")
            if not ok:
                await channel_interaction.followup.send(err, ephemeral=True)
                return
            success = await DropsActions.set_tracker_channel(guild.id, category, channel_id)
            if success:
                channel = guild.get_channel(channel_id)
                channel_name = channel.name if channel else str(channel_id)
                logger.info(f"Admin {channel_interaction.user} set {category} tracker to {channel_name}")
                await channel_interaction.edit_original_response(view=await _rebuild())
            else:
                await channel_interaction.followup.send(
                    view=create_empty_layout(f"Failed to save {category} tracking channel."), ephemeral=True
                )

        async def on_remove(remove_interaction: discord.Interaction, category: str):
            await remove_interaction.response.defer(ephemeral=True)
            success = await DropsActions.remove_tracker_channel(guild.id, category)
            if success:
                logger.info(f"Admin {remove_interaction.user} cleared {category} tracker channel")
                await remove_interaction.edit_original_response(view=await _rebuild())
            else:
                await remove_interaction.followup.send(
                    view=create_empty_layout(f"Failed to clear {category} tracking channel."), ephemeral=True
                )

        async def on_cancel(cancel_interaction: discord.Interaction):
            layout = create_empty_layout("Tracked channels configuration closed.")
            await cancel_interaction.response.edit_message(view=layout)

        layout = build_drops_tracker_view(
            await DropsActions.get_drops_settings(guild.id), guild, on_channel_select, on_remove, on_cancel
        )
        await interaction.response.send_message(view=layout, ephemeral=True)
        msg = await interaction.original_response()
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Drops Manager Role ====================

    async def _show_drops_manager_role_menu(self, interaction: discord.Interaction):
        """Show Drops manager role configuration."""
        from .views.base import create_unique_id, AdminLayoutBuilder

        guild = interaction.guild

        def _build_panel(current_role_id: int | None) -> discord.ui.LayoutView:
            unique_id = create_unique_id()

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
                custom_id=f"drops_mgr_role_{unique_id}",
            )
            role_select.callback = role_callback

            select_row = discord.ui.ActionRow()
            select_row.add_item(role_select)
            builder.add_item(select_row)

            done_btn = discord.ui.Button(
                label="Done",
                style=discord.ButtonStyle.secondary,
                custom_id=f"drops_mgr_done_{unique_id}",
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
                await role_interaction.edit_original_response(view=_build_panel(selected_role_id))
            else:
                await role_interaction.followup.send(
                    view=create_empty_layout("Failed to save drops manager role."), ephemeral=True
                )

        async def done_callback(done_interaction: discord.Interaction):
            layout = create_empty_layout("Manager role configuration closed.")
            await done_interaction.response.edit_message(view=layout)

        current_role_id = await DropsActions.get_manager_role(guild.id)
        layout = _build_panel(current_role_id)
        await interaction.response.send_message(view=layout, ephemeral=True)
        msg = await interaction.original_response()
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Drops Status ====================

    async def _show_drops_status(self, interaction: discord.Interaction):
        """Show the Updates & Drops configuration status."""
        await interaction.response.defer(ephemeral=True)

        overview = await DropsActions.get_overview(interaction.guild.id)
        layout = build_drops_status_view(overview, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Announcements ====================

    async def _show_ann_channel_menu(self, interaction: discord.Interaction):
        """Show announcement channel configuration."""
        await self._navigate_to(interaction, ANN_CHANNEL_CONFIG, interaction.guild)

    async def _show_ann_settings_menu(self, interaction: discord.Interaction):
        """Show announcement thread settings configuration."""
        await self._navigate_to(interaction, ANN_SETTINGS_CONFIG, interaction.guild)

    async def _show_ann_status(self, interaction: discord.Interaction):
        """Show the announcement configuration status."""
        await interaction.response.defer(ephemeral=True)

        overview = await AnnouncementActions.get_overview(interaction.guild.id)
        layout = build_announcement_status_view(overview, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Suggestions ====================

    async def _show_sug_channel_menu(self, interaction: discord.Interaction):
        """Show suggestion channel configuration."""
        await self._navigate_to(interaction, SUG_CHANNEL_CONFIG, interaction.guild)

    async def _show_sug_status(self, interaction: discord.Interaction):
        """Show the suggestion system status."""
        await interaction.response.defer(ephemeral=True)

        overview = await SuggestionActions.get_overview(interaction.guild.id)
        layout = build_suggestion_status_view(overview, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)

    # ==================== Guide Panel Handlers ====================

    async def _show_guide_channel_menu(self, interaction: discord.Interaction):
        await self._navigate_to(interaction, GUIDE_CHANNEL_CONFIG, interaction.guild)

    async def _show_guide_upload_menu(self, interaction: discord.Interaction):
        await self._navigate_to(interaction, GUIDE_UPLOAD_CONFIG, interaction.guild)

    async def _show_guide_enabled_menu(self, interaction: discord.Interaction):
        await self._navigate_to(interaction, GUIDE_ENABLED_CONFIG, interaction.guild)

    async def _show_guide_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = await GuideActions.get_guide_status(interaction.guild.id)
        layout = self._build_guide_status_view(status, interaction.guild)
        msg = await interaction.followup.send(view=layout, ephemeral=True)
        attach_timeout_expiry_msg(layout, msg)

    @staticmethod
    def _build_guide_status_view(status: dict, guild: discord.Guild) -> discord.ui.LayoutView:
        layout = discord.ui.LayoutView(timeout=300.0)
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
