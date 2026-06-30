"""One-shot migration: canonicalize TheCodex panel-role config keys.

Renames the per-guild role lists inside Settings.GuildConfig:

    roles.admin      -> roles.admin_role_ids
    roles.moderator  -> roles.mod_role_ids

The dashboard and bot now read the canonical `admin_role_ids` / `mod_role_ids`
names (with a read-time fallback to the legacy names), so this migration is for
tidiness/consistency rather than correctness. It is idempotent: re-running it
does nothing once every document has been converted.

Usage:
    MONGO_URI="mongodb://..." python -m dashboard.migrations.migrate_role_keys [--apply]

Without --apply it runs in dry-run mode and only reports what would change.
"""

from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the writes. Omit for a dry run.",
    )
    args = parser.parse_args()

    uri = os.environ.get("MONGO_URI")
    if not uri:
        print("MONGO_URI environment variable is required", file=sys.stderr)
        return 1

    client = MongoClient(uri)
    coll = client["Settings"]["GuildConfig"]

    # Any doc that still carries a legacy key inside `roles`.
    query = {"$or": [{"roles.admin": {"$exists": True}}, {"roles.moderator": {"$exists": True}}]}
    candidates = list(coll.find(query, projection={"guild_id": 1, "roles": 1}))

    print(f"Found {len(candidates)} guild config(s) with legacy role keys.")
    converted = 0
    for doc in candidates:
        roles = doc.get("roles") or {}
        set_ops: dict = {}
        unset_ops: dict = {}

        # Only populate the canonical key if it is not already present, so we
        # never clobber a value written by the new code path.
        if "admin" in roles:
            if "admin_role_ids" not in roles:
                set_ops["roles.admin_role_ids"] = roles.get("admin") or []
            unset_ops["roles.admin"] = ""
        if "moderator" in roles:
            if "mod_role_ids" not in roles:
                set_ops["roles.mod_role_ids"] = roles.get("moderator") or []
            unset_ops["roles.moderator"] = ""

        if not set_ops and not unset_ops:
            continue

        update: dict = {}
        if set_ops:
            update["$set"] = set_ops
        if unset_ops:
            update["$unset"] = unset_ops

        gid = doc.get("guild_id")
        if args.apply:
            coll.update_one({"_id": doc["_id"]}, update)
            print(f"  migrated guild {gid}")
        else:
            print(f"  would migrate guild {gid}: {update}")
        converted += 1

    mode = "Migrated" if args.apply else "Would migrate"
    print(f"{mode} {converted} document(s).")
    if not args.apply:
        print("Dry run only — re-run with --apply to write changes.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
