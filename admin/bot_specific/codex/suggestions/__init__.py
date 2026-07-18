# ───────────────────────────────────────────────────────────────────────────
# VENDORED from admin_engine/ — DO NOT EDIT HERE.
# Edit the master at <repo-root>/admin_engine/ and run:
#     python tools/sync_admin_engine.py
# Drift is enforced by:  python tools/sync_admin_engine.py --check
# ───────────────────────────────────────────────────────────────────────────
"""Suggestions admin group for TheCodex (Update Status / Export / View Status).

A per-bot feature: it depends on the ``suggestions_*`` collections and the ``/suggest``
command, and reads its channel from the bot-owned ``storage.config_manager`` seam, so it is
active only in bots that reference these nodes from their ``panel_configs.py``. The public
surface below is what such a ``panel_configs.py`` imports:

    from ..bot_specific.codex.suggestions import (
        SuggestionActions,
        build_suggestion_update_status_node,
        build_suggestion_export_node,
        build_suggestion_status_node,
    )
"""

from .suggestion_actions import SuggestionActions
from .suggestion_nodes import (
    build_suggestion_update_status_node,
    build_suggestion_export_node,
    build_suggestion_status_node,
)

__all__ = [
    "SuggestionActions",
    "build_suggestion_update_status_node",
    "build_suggestion_export_node",
    "build_suggestion_status_node",
]
