"""
Board Store - DB CRUD for the board_content collection.

One document per guild per board. ``board_id`` is always "main" today; it exists
so a second board per guild is an additive change later rather than a storage
redo.

Document shape:
    {
      guild_id: "123", board_id: "main",
      channel_id: "456", message_id: "789",     # where it is currently posted
      board_data: {
        accent_color: "#4D0EB3",
        components: [ ... ],                    # the static message
        responses: [ { id, label, accent_color?, components: [...] } ]
      },
      updated_at, updated_by
    }
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from storage.settings.collections import db_manager
from storage.log import get_logger

logger = get_logger("BoardStore")

DEFAULT_BOARD_ID = "main"


class BoardStore:
    """Manages board_content documents in MongoDB."""

    def __init__(self):
        self._collection_key = "board_content"

    @property
    def _col(self):
        return db_manager.get_collection_manager(self._collection_key)

    @staticmethod
    def _key(guild_id: int, board_id: str = DEFAULT_BOARD_ID) -> Dict[str, str]:
        """Build the document key. guild_id is stored in canonical string form."""
        return {"guild_id": str(guild_id), "board_id": board_id}

    # ── Reads ────────────────────────────────────────────────────────────────

    async def get_document(
        self, guild_id: int, board_id: str = DEFAULT_BOARD_ID
    ) -> Optional[Dict[str, Any]]:
        """Get the full document, including where the board is posted."""
        return await self._col.find_one(self._key(guild_id, board_id))

    async def get_board(
        self, guild_id: int, board_id: str = DEFAULT_BOARD_ID
    ) -> Optional[Dict[str, Any]]:
        """Get just the board layout data. Returns None if this guild has no board."""
        doc = await self.get_document(guild_id, board_id)
        return doc.get("board_data") if doc else None

    @staticmethod
    def find_response(board_data: Dict[str, Any], response_id: str) -> Optional[Dict[str, Any]]:
        """Look a named response up in a board's response pool."""
        for response in board_data.get("responses") or []:
            if response.get("id") == response_id:
                return response
        return None

    @staticmethod
    def list_responses(board_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list(board_data.get("responses") or [])

    # ── Writes ───────────────────────────────────────────────────────────────

    async def save_board(
        self,
        guild_id: int,
        board_data: Dict[str, Any],
        updated_by: int,
        board_id: str = DEFAULT_BOARD_ID,
    ) -> bool:
        """Save (upsert) a board's layout.

        Deliberately does NOT touch channel_id / message_id: editing the layout
        must not lose track of where the board is already posted.
        """
        try:
            await self._col.update_one(
                self._key(guild_id, board_id),
                {"$set": {
                    "guild_id": str(guild_id),
                    "board_id": board_id,
                    "board_data": board_data,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": str(updated_by),
                }},
                upsert=True,
            )
            logger.info(f"Board saved for guild {guild_id} by user {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to save board for guild {guild_id}: {e}", exc_info=True)
            return False

    async def set_posted_message(
        self,
        guild_id: int,
        channel_id: Optional[int],
        message_id: Optional[int],
        board_id: str = DEFAULT_BOARD_ID,
    ) -> bool:
        """Record where the board is currently posted.

        Pass None/None to forget the posted message (used when the stored message
        turns out to be gone).
        """
        try:
            await self._col.update_one(
                self._key(guild_id, board_id),
                {"$set": {
                    "channel_id": str(channel_id) if channel_id else None,
                    "message_id": str(message_id) if message_id else None,
                    "posted_at": datetime.now(timezone.utc) if message_id else None,
                }},
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to record posted board message for guild {guild_id}: {e}",
                exc_info=True,
            )
            return False

    async def delete_board(self, guild_id: int, board_id: str = DEFAULT_BOARD_ID) -> bool:
        """Delete a guild's board."""
        try:
            result = await self._col.delete_one(self._key(guild_id, board_id))
            deleted = result.deleted_count > 0 if hasattr(result, "deleted_count") else bool(result)
            logger.info(f"Board deleted for guild {guild_id}: {deleted}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete board for guild {guild_id}: {e}", exc_info=True)
            return False


# Global instance
board_store = BoardStore()
