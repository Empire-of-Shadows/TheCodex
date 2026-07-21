"""
Color Set Actions - All DB I/O for the Color Set system.

Uses db_manager.get_collection_manager() for the two Color Set collections:
  - color_color_sets
  - color_color_set_assignments

Colors are stored and returned as list[dict] with keys:
  {"name": str, "value": int}  - name is the admin-given display label

CollectionManager API:
  find_many(filter, projection, sort, limit, skip)  → list[dict]
  find_one(filter, projection)                       → dict | None
  create_one(document)                               → inserted_id  (auto-adds created_at/updated_at)
  update_one(filter, update_dict, upsert=False)      → bool  (auto-adds updated_at to $set)
  delete_one(filter)                                 → bool
  delete_many(filter)                                → int
"""

from __future__ import annotations

from typing import Optional

from storage.log import get_logger

logger = get_logger("ColorSetActions")

DEFAULT_TIER_PRESETS = [
    {
        "tier": "tier_1",
        "name": "Common",
        "description": "Default Tier 1 color palette",
        "colors": [
            {"name": "Ash",     "value": 0x95A5A6},
            {"name": "Slate",   "value": 0x7F8C8D},
            {"name": "Seafoam", "value": 0x1ABC9C},
        ],
    },
    {
        "tier": "tier_2",
        "name": "Uncommon",
        "description": "Default Tier 2 color palette",
        "colors": [
            {"name": "Emerald",   "value": 0x2ECC71},
            {"name": "Sky",       "value": 0x3498DB},
            {"name": "Sunflower", "value": 0xF1C40F},
        ],
    },
    {
        "tier": "tier_3",
        "name": "Rare",
        "description": "Default Tier 3 color palette",
        "colors": [
            {"name": "Amethyst",  "value": 0x9B59B6},
            {"name": "Cobalt",    "value": 0x2980B9},
            {"name": "Nephrite",  "value": 0x27AE60},
        ],
    },
    {
        "tier": "tier_4",
        "name": "Epic",
        "description": "Default Tier 4 color palette",
        "colors": [
            {"name": "Crimson",  "value": 0xE74C3C},
            {"name": "Wisteria", "value": 0x8E44AD},
            {"name": "Ember",    "value": 0xE67E22},
        ],
    },
    {
        "tier": "tier_5",
        "name": "Legendary",
        "description": "Default Tier 5 color palette",
        "colors": [
            {"name": "Midnight", "value": 0x2C3E50},
            {"name": "Gold",     "value": 0xF39C12},
            {"name": "Imperial", "value": 0xC0392B},
        ],
    },
    {
        "tier": None,
        "name": "Celestial",
        "description": "Unassigned - space-themed palette",
        "colors": [
            {"name": "Nebula",  "value": 0xE91E8C},
            {"name": "Nova",    "value": 0xFF6B35},
            {"name": "Void",    "value": 0x1A1A2E},
        ],
    },
    {
        "tier": None,
        "name": "Nature",
        "description": "Unassigned - earth-toned palette",
        "colors": [
            {"name": "Moss",  "value": 0x4A7C59},
            {"name": "Dusk",  "value": 0xB5838D},
            {"name": "Bark",  "value": 0x8B6355},
        ],
    },
    {
        "tier": None,
        "name": "Prism",
        "description": "Unassigned - vivid accent palette",
        "colors": [
            {"name": "Coral", "value": 0xFF6B6B},
            {"name": "Aqua",  "value": 0x4ECDC4},
            {"name": "Lemon", "value": 0xFFE66D},
        ],
    },
]


def _normalize_colors(raw_colors: list) -> list[dict]:
    """Normalize a colors list from DB to always be list[{"name": str, "value": int}].

    Handles legacy int-only format from before named colors were introduced.
    """
    result = []
    for c in raw_colors:
        if isinstance(c, dict):
            result.append({"name": c.get("name", ""), "value": int(c.get("value", 0))})
        elif isinstance(c, int):
            result.append({"name": "", "value": c})
    return result


class ColorSetActions:
    """Static async methods for managing Color Sets and their Assignments."""

    # ── Color Sets ─────────────────────────────────────────────────────────────

    @staticmethod
    async def list_color_sets(guild_id: int) -> list[dict]:
        """Return all color sets for a guild, sorted by name."""
        try:
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_sets")
            docs = await col.find_many(
                {"guild_id": str(guild_id)},
                sort=[("name", 1)],
            )
            return [
                {
                    "set_id": str(doc["_id"]),
                    "name": doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "colors": _normalize_colors(doc.get("colors", [])),
                    "created_at": doc.get("created_at"),
                }
                for doc in docs
            ]
        except Exception as e:
            logger.error(f"list_color_sets failed for guild {guild_id}: {e}", exc_info=True)
            return []

    @staticmethod
    async def get_color_set(guild_id: int, set_id: str) -> Optional[dict]:
        """Return a single color set by its string ID, or None if not found."""
        try:
            from bson import ObjectId
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_sets")
            doc = await col.find_one({"_id": ObjectId(set_id), "guild_id": str(guild_id)})
            if not doc:
                return None
            return {
                "set_id": str(doc["_id"]),
                "name": doc.get("name", ""),
                "description": doc.get("description", ""),
                "colors": _normalize_colors(doc.get("colors", [])),
                "created_at": doc.get("created_at"),
            }
        except Exception as e:
            logger.error(f"get_color_set failed for {set_id}: {e}", exc_info=True)
            return None

    @staticmethod
    async def create_color_set(
        guild_id: int,
        name: str,
        description: str,
        colors: list[dict],
    ) -> Optional[str]:
        """Create a new color set. Returns the new set_id string, or None on failure.

        colors: list of {"name": str, "value": int} dicts.
        """
        try:
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_sets")
            # create_one auto-adds created_at and updated_at
            inserted_id = await col.create_one({
                "guild_id": str(guild_id),
                "name": name.strip(),
                "description": description.strip(),
                "colors": colors,
            })
            return str(inserted_id)
        except Exception as e:
            logger.error(f"create_color_set failed for guild {guild_id}: {e}", exc_info=True)
            return None

    @staticmethod
    async def update_color_set_colors(
        guild_id: int,
        set_id: str,
        colors: list[dict],
    ) -> bool:
        """Replace the colors list on an existing color set.

        colors: list of {"name": str, "value": int} dicts.
        """
        try:
            from bson import ObjectId
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_sets")
            # update_one auto-adds updated_at to $set
            return await col.update_one(
                {"_id": ObjectId(set_id), "guild_id": str(guild_id)},
                {"$set": {"colors": colors}},
            )
        except Exception as e:
            logger.error(f"update_color_set_colors failed for {set_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def delete_color_set(guild_id: int, set_id: str) -> bool:
        """Delete a color set and all its assignments."""
        try:
            from bson import ObjectId
            from storage.settings.collections import db_manager
            sets_col = db_manager.get_collection_manager("color_color_sets")
            assign_col = db_manager.get_collection_manager("color_color_set_assignments")

            # Remove all assignments for this set first
            await assign_col.delete_many({"guild_id": str(guild_id), "color_set_id": set_id})

            return await sets_col.delete_one({"_id": ObjectId(set_id), "guild_id": str(guild_id)})
        except Exception as e:
            logger.error(f"delete_color_set failed for {set_id}: {e}", exc_info=True)
            return False

    # ── Assignments ────────────────────────────────────────────────────────────

    @staticmethod
    async def list_assignments(
        guild_id: int,
        set_id: Optional[str] = None,
    ) -> list[dict]:
        """Return all assignments for a guild, optionally filtered by set_id."""
        try:
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_set_assignments")
            query: dict = {"guild_id": str(guild_id)}
            if set_id is not None:
                query["color_set_id"] = set_id
            docs = await col.find_many(query)
            return [
                {
                    "assignment_id": str(doc["_id"]),
                    "color_set_id": doc.get("color_set_id", ""),
                    "target_type": doc.get("target_type", ""),
                    "target_id": doc.get("target_id", ""),
                    "override_mode": doc.get("override_mode", "additive"),
                }
                for doc in docs
            ]
        except Exception as e:
            logger.error(f"list_assignments failed for guild {guild_id}: {e}", exc_info=True)
            return []

    @staticmethod
    async def upsert_assignment(
        guild_id: int,
        set_id: str,
        target_type: str,
        target_id: str,
    ) -> bool:
        """Create or update an assignment (unique per guild+set+target).

        Always stores override_mode="additive" - the system is always-additive.
        The field is preserved in the schema for backwards compatibility with
        existing documents, but the resolver ignores it.
        """
        try:
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_set_assignments")
            # update_one with upsert=True; auto-adds updated_at to $set
            return await col.update_one(
                {
                    "guild_id": str(guild_id),
                    "color_set_id": set_id,
                    "target_type": target_type,
                    "target_id": target_id,
                },
                {
                    "$set": {"override_mode": "additive"},
                    "$setOnInsert": {
                        "guild_id": str(guild_id),
                        "color_set_id": set_id,
                        "target_type": target_type,
                        "target_id": target_id,
                    },
                },
                upsert=True,
            )
        except Exception as e:
            logger.error(f"upsert_assignment failed: {e}", exc_info=True)
            return False

    @staticmethod
    async def delete_assignment(
        guild_id: int,
        set_id: str,
        target_type: str,
        target_id: str,
    ) -> bool:
        """Delete a specific assignment."""
        try:
            from storage.settings.collections import db_manager
            col = db_manager.get_collection_manager("color_color_set_assignments")
            return await col.delete_one({
                "guild_id": str(guild_id),
                "color_set_id": set_id,
                "target_type": target_type,
                "target_id": target_id,
            })
        except Exception as e:
            logger.error(f"delete_assignment failed: {e}", exc_info=True)
            return False

    # ── Server Default Color ───────────────────────────────────────────────────

    @staticmethod
    async def get_default_color(guild_id: int) -> Optional[int]:
        """Return the server default color int for this guild, or None if not set."""
        try:
            from storage.settings.config_manager import get_config
            config = await get_config(guild_id)
            return config.embed["default_color"]
        except Exception as e:
            logger.error(f"get_default_color failed for guild {guild_id}: {e}", exc_info=True)
            return None

    @staticmethod
    async def set_default_color(guild_id: int, color: int) -> bool:
        """Set (or update) the server default color for this guild. Cannot be cleared."""
        try:
            from storage.settings.config_manager import get_guild_config_manager
            manager = await get_guild_config_manager()
            config = await manager.get_config(guild_id)
            config.embed["default_color"] = color
            return await manager.save_config(config)
        except Exception as e:
            logger.error(f"set_default_color failed for guild {guild_id}: {e}", exc_info=True)
            return False

    # ── Seeding ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def seed_default_sets(
        guild_id: int,
        server_default_color: Optional[int] = None,
    ) -> int:
        """Seed default color sets for a guild on first open.

        Creates 5 tier-assigned sets and 3 unassigned sets (Celestial, Nature, Prism).
        Tier-assigned sets are linked to their corresponding tier automatically.
        Unassigned sets are created but left for the admin to assign manually.
        Skips any color whose value equals the server default color.
        Returns the number of sets successfully created.
        """
        created = 0
        for preset in DEFAULT_TIER_PRESETS:
            colors = [
                c for c in preset["colors"]
                if server_default_color is None or c["value"] != server_default_color
            ]
            if not colors:
                continue
            set_id = await ColorSetActions.create_color_set(
                guild_id,
                preset["name"],
                preset["description"],
                colors,
            )
            if set_id:
                if preset.get("tier"):
                    await ColorSetActions.upsert_assignment(
                        guild_id, set_id, "tier", preset["tier"]
                    )
                created += 1
        logger.info(f"Seeded {created} default color sets for guild {guild_id}")
        return created

    # ── Convenience ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_resolution_data(guild_id: int) -> tuple[list[dict], list[dict]]:
        """Fetch all data needed for conflict detection and resolution.

        Returns:
            (color_sets, assignments) - both as flat dicts.
        """
        sets = await ColorSetActions.list_color_sets(guild_id)
        assignments = await ColorSetActions.list_assignments(guild_id)
        return sets, assignments
