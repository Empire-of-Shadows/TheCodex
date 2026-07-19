"""TheCodex's admin panel seam (bot-owned, NEVER vendored).

The vendored engine beside this package reaches every codex-specific backend through the
names defined here: ``bindings`` (config/audit/premium/cache/panel-role + the static branding
text) and ``panel_configs`` (the MAIN_PANEL tree). Engine files import them as
``from .settings.bindings import ...`` / ``from .settings.panel_configs import MAIN_PANEL``.
Panel-role tiering is not hand-rolled here: ``bindings.resolve_panel_role`` delegates to the
engine's shared ``auth.resolve_panel_role_from_config``.
"""
