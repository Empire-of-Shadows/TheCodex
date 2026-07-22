"""m7: Updates-Drops stats - compound ``_id.guild_id`` int -> str (IS-4 normalization).

StatsMonthly / StatsWeekly / StatsTotals embed the guild id INSIDE the compound ``_id``
document (e.g. ``{_id: {coll, year, month, guild_id}}``). ``_id`` is immutable, so this
cannot be an in-place ``$set``: each doc is copied to a new ``_id`` with ``guild_id``
stringified (preserving the original key ORDER - compound-``_id`` equality is
order-sensitive) and the old doc is then deleted. Insert-before-delete, so a crash
mid-way leaves a recoverable duplicate, never a loss; the re-run only matches docs still
carrying an int ``_id.guild_id``, so it is idempotent.

Global (guild-less) stats docs have no ``_id.guild_id`` key and are never matched.

    python -m migrations.scripts.m7_updates_stats_guild_id_to_str            # dry run
    python -m migrations.scripts.m7_updates_stats_guild_id_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args

_DB = "Updates-Drops"
_COLLECTIONS = ("StatsMonthly", "StatsWeekly", "StatsTotals")
_MATCH = {"_id.guild_id": {"$type": ["int", "long"]}}


def main() -> None:
    args = parse_args("Updates-Drops stats _id.guild_id int -> str (IS-4).")
    client = connect()
    try:
        db = client[_DB]
        total_pending = 0
        for name in _COLLECTIONS:
            coll = db[name]
            total = coll.count_documents({})
            pending = coll.count_documents(_MATCH)
            print(f"{_DB}.{name}: {total} doc(s); {pending} carry int _id.guild_id.")
            total_pending += pending
            if pending == 0:
                continue
            if not args.apply:
                for d in coll.find(_MATCH).limit(3):
                    print(f"  would rewrite _id={dict(d['_id'])}")
                continue

            converted = skipped = 0
            for doc in coll.find(_MATCH):
                old_id = doc["_id"]
                # Preserve key order; only the guild_id value changes type.
                new_id = {k: (str(v) if k == "guild_id" else v) for k, v in old_id.items()}
                if coll.count_documents({"_id": new_id}, limit=1):
                    print(f"  SKIP (target exists, resolve manually): {dict(old_id)}")
                    skipped += 1
                    continue
                new_doc = dict(doc)
                new_doc["_id"] = new_id
                coll.insert_one(new_doc)
                coll.delete_one({"_id": old_id})
                converted += 1
            remaining = coll.count_documents(_MATCH)
            print(f"  APPLIED: converted={converted} skipped={skipped}; "
                  f"remaining int docs = {remaining} (should equal skipped).")

        if total_pending == 0:
            print("Nothing to convert. (Idempotent no-op.)")
        elif not args.apply:
            print(f"DRY RUN: {total_pending} doc(s) across the three collections. "
                  f"Re-run with --apply.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
