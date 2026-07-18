"""TheCodex's storage seam (bot-owned, NEVER vendored).

The only storage code TheCodex writes by hand: ``bindings`` (URIs, cache choice, watched
collections), ``collections`` (the collection registry AND the shared ``db_manager``
singleton the rest of the bot imports), and ``config_manager`` (the guild-config layer).

This module is intentionally a docstring only. Do NOT re-export from ``.collections`` here:
``config_manager`` takes ``db_manager`` as a parameter and never constructs it at import
time, so importing ``storage.settings.config_manager`` must stay side-effect-free (no Mongo
URI required). Eagerly importing ``.collections`` in this ``__init__`` would build
``db_manager`` for every ``config_manager`` importer and raise when no Mongo env is set.
"""
