# TheCodex Step C — session kickoff prompt

Paste the block below into a fresh Claude Code session (started in this repo) to continue the
storage-engine migration with Step C, the seam consolidation.

---

Continue the TheCodex storage-engine migration — Step C, the seam consolidation.
This is a follow-on to earlier work; drift is already closed. Start by reading:
- Plan file: C:\Users\eosoc\.claude\plans\agile-growing-wombat.md (Step C section)
- The project memory "storage-engine-loguru-migration" (in MEMORY.md)

Where things stand: Steps 0/A/B and D are done. TheCodex is on the migrated
loguru engine (commit 8e0cdc4) and `python EmpireSystems/tools/sync_storage_engine.py
--check --bot codex` reports a genuine OK. Do NOT touch logging or the vendored
engine files — that's finished. Step C is a separate, elective refactor.

Step C goal: move TheCodex's hand-written storage seam into storage/settings/ and
consolidate the collection registry into one collections.py.

Target layout:
  storage/settings/
    __init__.py        docstring ONLY — no re-exports (see hazard below)
    bindings.py        moved from storage/bindings.py
    collections.py     the 27 CollectionConfigs from define_collections.py as a
                       COLLECTIONS dict, then db_manager = DatabaseManagerBase(
                       primary_uri=..., cache=..., watched_collections=...,
                       collection_configs=COLLECTIONS) — construct the BASE directly,
                       no concrete subclass. This replaces define_collections.py +
                       manager.py.
    config_manager.py  moved from storage/config_manager.py

Then repoint import sites across the bot:
  from storage.manager import db_manager   (~20) -> storage.settings.collections
  from storage.config_manager import ...   (~29) -> storage.settings.config_manager
  from storage import bindings             (1)   -> storage.settings

Hazards (all verified last session):
- bindings.py uses `from .cache.backend import CacheBackend` / `.cache.local`.
  Inside settings/ that must become `..cache.backend` / `..cache.local`, or it
  ImportErrors. (relay's storage/settings/bindings.py already does this — good reference.)
- settings/__init__.py MUST stay docstring-only. config_manager.py takes db_manager
  as a parameter (no module-level import today), so `from storage.config_manager
  import ...` does NOT construct db_manager. If __init__.py eagerly does
  `from .collections import db_manager`, all ~29 config_manager sites gain import-time
  construction -> ValueError: Primary MongoDB URI not provided for any script
  importing without Mongo env. relay's settings/__init__.py (383 bytes, docstring
  only) is the model.
- relay is the layout reference (storage/settings/) BUT relay kept the trio inside
  settings/. Codex should consolidate to a single collections.py instead — it's the
  first fleet adopter of that shape.
- Nobody imports the DatabaseManager class outside storage/; all 20 storage.manager
  sites import db_manager only — so constructing the base directly is safe.

Do it as its own commit in the TheCodex repo (its own git repo, branch main).
No CHANGELOG entry — internal plumbing, no player-facing change.

Verify with a dummy MONGO_URI set:
- python -c "import storage"
- python -c "from storage.settings.collections import db_manager; print(len(db_manager._accessor_map))" -> 27
- python -c "from storage.settings.config_manager import <something>" WITHOUT Mongo env -> must not raise (proves __init__ stayed lazy)
- grep for any leftover `from storage.manager`, `from storage.config_manager`,
  `from storage import bindings` -> zero
- live boot against a test token + scratch Mongo: on_ready completes through
  Database Attachment.

---

## Notes for you (not part of the paste)

- The two non-obvious traps (the `..cache` relative-import fix and the docstring-only
  `__init__.py`) are stated inline, so the fresh session won't fall into them even if it skips
  the plan file. The plan file has the fuller reasoning.
- The `~20 / ~29` counts are guidance; let the new session re-derive the exact import-site
  counts, since they may have shifted.
