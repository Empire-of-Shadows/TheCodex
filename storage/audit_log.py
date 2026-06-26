"""Admin Audit Log writer.

Persists every successful admin-driven mutation of GuildConfig so admins can
review who changed what, when, and from where (Discord panel or dashboard).
Read path lives in `dashboard/routers/audit_log.py`.

Document shape (collection: Settings.AuditLog):
    {
        guild_id: int,
        actor_id: int,
        actor_name: str,
        source: "discord" | "dashboard",
        section: str,
        key: str,
        old_value: Any,
        new_value: Any,
        action: "set" | "clear" | "toggle" | "create" | "remove",
        created_at: datetime,   # UTC; TTL 365d
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from storage.logging import get_logger

logger = get_logger("AuditLog")


def _to_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, dict):
        return {str(k): _to_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_safe(v) for v in value]
    return str(value)


class AuditLogger:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._collection = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            self._collection = self.db_manager.get_collection_manager('settings_audit_log')
            self._initialized = True
            logger.info("AuditLogger initialized")
        except Exception as e:
            logger.error(f"Failed to initialize AuditLogger: {e}", exc_info=True)
            raise

    async def log(
        self,
        *,
        guild_id: int,
        actor_id: int,
        actor_name: str,
        source: str,
        section: str,
        key: str,
        old_value: Any,
        new_value: Any,
        action: str,
    ) -> bool:
        if not self._initialized:
            await self.initialize()
        try:
            doc = {
                "guild_id": int(guild_id),
                "actor_id": int(actor_id),
                "actor_name": str(actor_name)[:128],
                "source": source,
                "section": section,
                "key": key,
                "old_value": _to_safe(old_value),
                "new_value": _to_safe(new_value),
                "action": action,
                "created_at": datetime.now(timezone.utc),
            }
            await self._collection.create_one(doc)
            return True
        except Exception as e:
            logger.error(
                f"Failed to write audit entry guild={guild_id} key={key}: {e}",
                exc_info=True,
            )
            return False


_audit_logger: Optional[AuditLogger] = None


async def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        from storage.manager import db_manager
        _audit_logger = AuditLogger(db_manager)
        await _audit_logger.initialize()
    return _audit_logger


def get_audit_logger_sync() -> Optional[AuditLogger]:
    return _audit_logger
