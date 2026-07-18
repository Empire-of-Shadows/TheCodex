# ───────────────────────────────────────────────────────────────────────────
# VENDORED from admin_engine/ — DO NOT EDIT HERE.
# Edit the master at <repo-root>/admin_engine/ and run:
#     python tools/sync_admin_engine.py
# Drift is enforced by:  python tools/sync_admin_engine.py --check
# ───────────────────────────────────────────────────────────────────────────
"""Bot-specific admin-panel code, namespaced by bot.

Master-owned and vendored into ONLY the bot it is named for. Such code still builds on the
generic engine (``PanelNode`` factories, the ``views/`` layout builders, the reusable
``actions/`` library), so every bot's panel is assembled the same way; it just wires in a
feature that lives in one bot alone.

It lives here, rather than loose in the engine's ``actions/`` and ``views/`` trees, so every
feature in the ecosystem is visible in one place and never masquerades as engine code. Group
each bot's code by FEATURE (``<bot>/<feature>/``): when a feature directory name turns up under
a second bot, that is the signal to evaluate promoting it into the generic engine. Promote only
if the feature can genuinely be combined to work for both bots -- a shared name alone is not
enough. Plumbing stays a flat file, never a directory, so it cannot fire that signal falsely.

This mirrors ``storage_engine/bot_specific/`` exactly; the same sync tool machinery vendors it
(``python tools/sync_admin_engine.py --scope bot-specific --bot <bot>``).
"""
