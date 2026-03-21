"""
Admin Panel Views using Discord Components v2.

UI views for the admin panel using LayoutView patterns.
"""

from .base import (
    create_unique_id,
    create_empty_layout,
    create_error_layout,
    create_success_layout,
    build_header,
    build_status_display,
    build_config_display,
    build_action_buttons,
    build_confirmation_buttons,
    build_back_button,
    build_select_row,
    AdminLayoutBuilder,
)

from .panel_views import (
    build_main_panel,
    build_subcategory_panel,
    attach_timeout_expiry,
    attach_timeout_expiry_msg,
    PANEL_GROUPS,
)

from .panel_engine import (
    PanelNode,
    build_menu_view,
    build_select_view,
    build_modal_trigger_view,
    build_dual_modal_trigger_view,
    build_file_upload_status_view,
    PanelInputModal,
    PanelFileUploadModal,
)

from .embed_views import (
    build_embed_status_view,
    TIER_NAMES,
    TIER_LABELS,
    FEATURE_OPTIONS,
)

from .color_views import (
    build_default_color_setup_view,
    build_color_sets_menu,
    build_color_set_detail,
    build_role_assign_view,
    build_tier_assign_view,
    build_delete_confirm_view,
    DefaultColorModal,
    ColorSetCreateModal,
    ColorAddModal,
)

from .wyr_views import (
    build_wyr_status_view,
    build_wyr_ping_role_view,
    WyrCreateRoleModal,
)

from .new_member_views import (
    build_new_member_status_view,
    build_nm_whitelist_role_view,
    NmCreateRoleModal,
    build_nm_welcome_channel_view,
    NmCreateChannelModal,
)

from .tracker_views import (
    build_tag_tracker_settings_view,
    TagTrackerServerTagModal,
    build_boost_tracker_settings_view,
    build_tracker_status_view,
)

from .drops_views import (
    build_drops_channel_view,
    build_drops_tracker_view,
    build_drops_status_view,
)

from .announcement_views import (
    build_announcement_status_view,
)

from .suggestion_views import (
    build_suggestion_status_view,
    SuggestionStatusUpdateModal,
    build_suggestion_export_view,
)

__all__ = [
    # Base utilities
    "create_unique_id",
    "create_empty_layout",
    "create_error_layout",
    "create_success_layout",
    "build_header",
    "build_status_display",
    "build_config_display",
    "build_action_buttons",
    "build_confirmation_buttons",
    "build_back_button",
    "build_select_row",
    "AdminLayoutBuilder",
    # Panel views
    "build_main_panel",
    "build_subcategory_panel",
    "attach_timeout_expiry",
    "attach_timeout_expiry_msg",
    "PANEL_GROUPS",
    # Panel engine
    "PanelNode",
    "build_menu_view",
    "build_select_view",
    "build_modal_trigger_view",
    "build_dual_modal_trigger_view",
    "build_file_upload_status_view",
    "PanelInputModal",
    "PanelFileUploadModal",
    # Embed config views
    "build_embed_status_view",
    "TIER_NAMES",
    "TIER_LABELS",
    "FEATURE_OPTIONS",
    # Color set views
    "build_default_color_setup_view",
    "build_color_sets_menu",
    "build_color_set_detail",
    "build_role_assign_view",
    "build_tier_assign_view",
    "build_delete_confirm_view",
    "DefaultColorModal",
    "ColorSetCreateModal",
    "ColorAddModal",
    # WYR config views
    "build_wyr_status_view",
    "build_wyr_ping_role_view",
    "WyrCreateRoleModal",
    # New member views
    "build_new_member_status_view",
    "build_nm_whitelist_role_view",
    "NmCreateRoleModal",
    "build_nm_welcome_channel_view",
    "NmCreateChannelModal",
    # Tracker views
    "build_tag_tracker_settings_view",
    "TagTrackerServerTagModal",
    "build_boost_tracker_settings_view",
    "build_tracker_status_view",
    # Drops views
    "build_drops_channel_view",
    "build_drops_tracker_view",
    "build_drops_status_view",
    # Announcement views
    "build_announcement_status_view",
    # Suggestion views
    "build_suggestion_status_view",
    "SuggestionStatusUpdateModal",
    "build_suggestion_export_view",
]
