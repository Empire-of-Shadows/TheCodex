"""Concrete DatabaseManager for TheCodex (bot-owned, NOT vendored).

Composes the vendored engine base (``DatabaseManagerBase``) with this bot's
``DefineCollections`` mixin and instantiates the shared ``db_manager`` the rest of the bot
imports. The engine stays generic; the bot supplies its collections.

There is no separate ``database_properties.py`` any more: the engine base builds the
attribute accessor map itself from the registry, so every collection is reachable as
``db_manager.<registry_key>`` (and ``db_manager.<accessor>`` when a ``CollectionConfig``
sets one). Import sites use ``from storage.manager import db_manager``.
"""

from __future__ import annotations

from storage.database_manager import DatabaseManagerBase
from storage.define_collections import DefineCollections
from storage import bindings


class DatabaseManager(DatabaseManagerBase, DefineCollections):
    """TheCodex's MongoDB manager: engine core + this bot's collection registry."""


# Global database manager instance (shared across the bot; initialized at startup).
db_manager = DatabaseManager(
    primary_uri=bindings.MONGO_URIS["primary"],
    cache=bindings.build_cache(),
    watched_collections=bindings.WATCHED_COLLECTIONS,
)
