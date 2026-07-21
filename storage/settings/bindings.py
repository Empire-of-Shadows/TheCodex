"""storage_engine bindings - TheCodex (bot-owned, NOT vendored).

The single integration point between the vendored storage engine and this bot's
environment. The engine (and this bot's own ``collections.py``) import these names. The
bot-owned (hand-written) storage seam lives in ``storage/settings/`` - ``bindings.py`` /
``collections.py`` (the registry + the shared ``db_manager``) / ``config_manager.py``;
everything else under ``storage/`` is vendored engine code - do not edit it here. (Audit
logging uses the engine ``AuditLog`` service; the admin-panel setup gate now lives in the
admin seam at ``admin/settings/setup_gatekeeper.py``.)

Template: ``EmpireSystems/storage_engine/bindings_reference.py``.
Layout reference: ``Informatinal/Stygian-Relay/storage/settings/``.

Env note: ``MONGO_URI`` is loaded by the entrypoint (``Codex.py`` loads ``docker/.env`` /
``.env.local`` before importing ``storage.settings.collections``), so reading it here at
import time is safe - same ordering the pre-migration ``db_manager = DatabaseManager()``
relied on.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Relative imports so this resolves against the vendored ``storage`` package. The engine sits
# one level up now that the seam lives in storage/settings/.
from ..cache.backend import CacheBackend
from ..cache.local import LocalCache


# ── Connections (ENGINE CONTRACT: MONGO_URIS) ──────────────────────────────────
# TheCodex uses a single primary connection (every collection in define_collections.py
# is connection='primary').
MONGO_URIS: Dict[str, Optional[str]] = {
    "primary": os.getenv("MONGO_URI"),
}


# ── Cache defaults (ENGINE CONTRACT: CACHE_DEFAULTS) ────────────────────────────
CACHE_DEFAULTS: Dict[str, Any] = {
    "max_size": 5000,
    "default_ttl": 300,
}


# ── Cache backend factory (ENGINE CONTRACT: build_cache) ────────────────────────
def build_cache() -> CacheBackend:
    """Return the cache backend this bot uses (in-process LocalCache)."""
    return LocalCache(**CACHE_DEFAULTS)


# ── Change-stream coherency (ENGINE CONTRACT: WATCHED_COLLECTIONS) ──────────────
# Empty = TTL-only coherency (no replica set required); matches the pre-migration behavior
# where db_manager was created with no watched list.
WATCHED_COLLECTIONS: List[str] = []


# ── Audit hook (ENGINE CONTRACT: audit_storage_event) - OPTIONAL ────────────────
async def audit_storage_event(
    *,
    collection: str,
    action: str,
    query: dict,
    actor_id: Optional[int] = None,
) -> None:
    """No-op: TheCodex audits admin mutations through the engine ``AuditLog`` service
    (wired in ``admin/settings/bindings.py``), not this generic collection doer."""
    return None
