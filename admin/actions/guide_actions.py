"""
Guide Admin Actions

Business logic for guide configuration in the admin panel.
"""

import json
from typing import Any, Dict, List, Optional

from storage.settings.config_manager import get_guild_config_manager, get_config
from Features.Guide.guide_store import guide_store
from Features.Guide.guide_schema import validate_guide_schema, normalize_pages
from Features.Guide.guide import guide_manager
from storage.log import get_logger

logger = get_logger("GuideActions")


class GuideActions:
	"""Static methods for guide admin panel operations."""

	@staticmethod
	async def get_guide_channel_as_list(guild_id: int) -> list:
		config = await get_config(guild_id)
		ch = config.guide.get("channel_id")
		return [str(ch)] if ch else []

	@staticmethod
	async def set_guide_channel(guild_id: int, channel_id: int) -> bool:
		manager = await get_guild_config_manager()
		return await manager.set_channel(guild_id, "guide", channel_id)

	@staticmethod
	async def clear_guide_channel(guild_id: int) -> bool:
		manager = await get_guild_config_manager()
		return await manager.set_channel(guild_id, "guide", None)

	@staticmethod
	async def get_enabled(guild_id: int) -> bool:
		config = await get_config(guild_id)
		return config.guide.get("enabled", True)

	@staticmethod
	async def get_enabled_as_list(guild_id: int) -> list:
		enabled = await GuideActions.get_enabled(guild_id)
		return ["true" if enabled else "false"]

	@staticmethod
	async def set_enabled_from_list(guild_id: int, values: list) -> bool:
		enabled = values[0] == "true" if values else True
		manager = await get_guild_config_manager()
		config = await manager.get_config(guild_id)
		config.guide["enabled"] = enabled
		return await manager.save_config(config)

	@staticmethod
	async def get_guide_json_raw(guild_id: int) -> list:
		"""Get raw guide JSON as a list (for file_upload panel node)."""
		data = await guide_store.get_guide(guild_id)
		if data:
			return [json.dumps(data, indent=2, ensure_ascii=False)]
		return []

	@staticmethod
	async def set_guide_json_from_list(guild_id: int, values: list) -> bool:
		"""Upload guide JSON. values[0] is the JSON string."""
		if not values:
			return False

		raw = values[0]
		try:
			data = json.loads(raw)
		except json.JSONDecodeError as e:
			logger.warning(f"Invalid JSON uploaded for guild {guild_id}: {e}")
			return False

		# Normalize (auto-generate IDs)
		data = normalize_pages(data)

		# Validate
		ok, msg = validate_guide_schema(data)
		if not ok:
			logger.warning(f"Guide schema validation failed for guild {guild_id}: {msg}")
			return False

		# Save
		saved = await guide_store.save_guide(guild_id, data, updated_by=0)
		if saved:
			guide_manager.invalidate_cache(guild_id)
		return saved

	@staticmethod
	async def clear_guide_json(guild_id: int) -> bool:
		"""Delete custom guide and revert to default template."""
		deleted = await guide_store.delete_guide(guild_id)
		if deleted:
			guide_manager.invalidate_cache(guild_id)
		return deleted

	@staticmethod
	async def get_guide_status(guild_id: int) -> Dict[str, Any]:
		"""Get guide status for the admin panel."""
		config = await get_config(guild_id)
		doc = await guide_store.get_raw_document(guild_id)

		status = {
			"enabled": config.guide.get("enabled", True),
			"channel_id": config.guide.get("channel_id"),
			"has_custom_guide": doc is not None,
			"updated_at": doc.get("updated_at") if doc else None,
			"updated_by": doc.get("updated_by") if doc else None,
		}

		# Count pages
		if doc and doc.get("guide_data"):
			pages = doc["guide_data"].get("pages", [])
			total = _count_pages(pages)
			status["page_count"] = total
		else:
			status["page_count"] = 0

		return status


def _count_pages(pages: list) -> int:
	"""Recursively count pages in a tree."""
	count = len(pages)
	for page in pages:
		children = page.get("children", [])
		if children:
			count += _count_pages(children)
	return count
