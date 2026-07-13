"""Canonicalize TheCodex panel-role config keys in Settings.GuildConfig.

Renames the per-guild role lists:

    roles.admin      -> roles.admin_role_ids
    roles.moderator  -> roles.mod_role_ids

The dashboard and bot read the canonical ``admin_role_ids`` / ``mod_role_ids``
names, so this is for tidiness/consistency. Idempotent: re-running does nothing
once every document has been converted. (M1 also performs this rewrite; this
remains as a standalone, targeted alternative.)

    python -m migrations.scripts.migrate_role_keys           # dry run
    python -m migrations.scripts.migrate_role_keys --apply
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args


def main() -> int:
    args = parse_args(__doc__)
    client = connect()
    coll = client["Settings"]["GuildConfig"]

    query = {"$or": [{"roles.admin": {"$exists": True}}, {"roles.moderator": {"$exists": True}}]}
    candidates = list(coll.find(query, projection={"guild_id": 1, "roles": 1}))
    print(f"Found {len(candidates)} guild config(s) with legacy role keys.")

    converted = 0
    for doc in candidates:
        roles = doc.get("roles") or {}
        set_ops: dict = {}
        unset_ops: dict = {}

        # Only populate the canonical key if it isn't already present, so we
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

    verb = "Migrated" if args.apply else "Would migrate"
    print(f"{verb} {converted} document(s).")
    if not args.apply and converted:
        print("Dry run only - re-run with --apply to write changes.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
