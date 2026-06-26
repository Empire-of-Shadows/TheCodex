"""
Guide Store — DB CRUD for guide_content collection.

One document per guild containing the entire guide page tree.
Loads the default template from defaults/guide_template.json on first access.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from storage.manager import db_manager
from utils.logger import get_logger

logger = get_logger("GuideStore")

_TEMPLATE_PATH = os.path.join(
	os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
	"defaults", "guide_template.json",
)


class GuideStore:
	"""Manages guide_content documents in MongoDB."""

	def __init__(self):
		self._collection_key = "guide_content"

	@property
	def _col(self):
		return db_manager.get_collection_manager(self._collection_key)

	async def get_guide(self, guild_id: int) -> Optional[Dict[str, Any]]:
		"""Get the guide data for a guild. Returns None if not found."""
		doc = await self._col.find_one({"guild_id": guild_id})
		if doc:
			return doc.get("guide_data")
		return None

	async def get_or_create_guide(self, guild_id: int) -> Dict[str, Any]:
		"""Get the guide data, creating from default template if needed."""
		data = await self.get_guide(guild_id)
		if data is not None:
			return data

		logger.info(f"No guide found for guild {guild_id}, loading default template")
		data = self._load_default_template()
		await self.save_guide(guild_id, data, updated_by=0)
		return data

	async def save_guide(self, guild_id: int, guide_data: Dict[str, Any], updated_by: int) -> bool:
		"""Save (upsert) guide data for a guild."""
		try:
			await self._col.update_one(
				{"guild_id": guild_id},
				{"$set": {
					"guild_id": guild_id,
					"guide_data": guide_data,
					"updated_at": datetime.now(timezone.utc),
					"updated_by": updated_by,
				}},
				upsert=True,
			)
			logger.info(f"Guide saved for guild {guild_id} by user {updated_by}")
			return True
		except Exception as e:
			logger.error(f"Failed to save guide for guild {guild_id}: {e}", exc_info=True)
			return False

	async def delete_guide(self, guild_id: int) -> bool:
		"""Delete guide data for a guild."""
		try:
			result = await self._col.delete_one({"guild_id": guild_id})
			deleted = result.deleted_count > 0 if hasattr(result, "deleted_count") else True
			logger.info(f"Guide deleted for guild {guild_id}: {deleted}")
			return deleted
		except Exception as e:
			logger.error(f"Failed to delete guide for guild {guild_id}: {e}", exc_info=True)
			return False

	async def get_raw_document(self, guild_id: int) -> Optional[Dict[str, Any]]:
		"""Get the full document including metadata."""
		return await self._col.find_one({"guild_id": guild_id})

	def _load_default_template(self) -> Dict[str, Any]:
		"""Load the default guide template JSON."""
		try:
			with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
				return json.load(f)
		except Exception as e:
			logger.error(f"Failed to load default guide template: {e}", exc_info=True)
			# Return minimal fallback
			return {
				"accent_color": "#4D0EB3",
				"pages": [
					{
						"id": "welcome",
						"label": "Welcome",
						"description": "Welcome to the server guide",
						"content": {
							"components": [
								{"type": "text", "content": "# Server Guide\n\nThis guide is being set up. Check back soon!"}
							]
						}
					}
				]
			}


# Global instance
guide_store = GuideStore()
