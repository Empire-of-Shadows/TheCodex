"""
Storage module for TheCodex Bot

Provides MongoDB-backed database management, configuration, and collection access.
"""

from storage.database_manager import db_manager, DatabaseManager
from storage.mongo_track import track_manager, TrackManager
from storage.config_manager import (
    GuildConfigManager,
    get_guild_config_manager,
    get_config_manager,
    set_config_manager,
    ConfigManager,        # backward-compat alias
)
from storage.core.collection_manager import CollectionManager
from storage.core.collection_config import CollectionConfig
