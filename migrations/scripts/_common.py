"""Shared helpers for TheCodex data migrations.

Loads MongoDB credentials from the bot's local env exactly like the entrypoint
(docker/.env then docker/.env.local override), connects, and provides the
standard dry-run/apply argument parsing every migration shares.

Every migration is a standalone script:

    python -m migrations.scripts.<name>            # dry run (default, no writes)
    python -m migrations.scripts.<name> --apply    # perform the writes

All migrations are idempotent - re-running after --apply is a no-op.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse as up
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

# migrations/scripts/_common.py -> repo root is two parents up.
_BOT_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load env the way Codex.py does: docker/.env then docker/.env.local wins."""
    load_dotenv(_BOT_ROOT / "docker" / ".env")
    load_dotenv(_BOT_ROOT / "docker" / ".env.local", override=True)


def _direct(uri: str) -> str:
    """Rewrite a URI for a single-node direct connection (drop replicaSet)."""
    p = up.urlsplit(uri)
    q = [(k, v) for k, v in up.parse_qsl(p.query)
         if k.lower() not in ("replicaset", "directconnection")]
    q.append(("directConnection", "true"))
    return up.urlunsplit((p.scheme, p.netloc, p.path, up.urlencode(q), p.fragment))


def connect(timeout_ms: int = 8000) -> MongoClient:
    """Return a connected MongoClient using the bot's MONGO_URI.

    Tries the URI as-is first (works inside the bot's container/network). If
    replica-set discovery can't reach the members (e.g. running from a host that
    can't resolve the RS member names), retries with a direct single-node
    connection. A direct connection is fine for a dry run; run --apply where the
    normal RS connection works so writes reach the primary.
    """
    load_env()
    uri = os.getenv("MONGO_URI")
    if not uri:
        print("MONGO_URI not set (checked docker/.env and docker/.env.local).", file=sys.stderr)
        raise SystemExit(1)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        return client
    except ServerSelectionTimeoutError:
        print("Replica-set connection failed; retrying with a direct connection.", file=sys.stderr)
        client = MongoClient(_direct(uri), serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        return client


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the writes. Omit for a dry run (default).",
    )
    return parser.parse_args()
