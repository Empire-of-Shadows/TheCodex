"""M3 - drop indexes orphaned by the audit's schema changes.

The audit switched the Suggestions index from ``author_id`` to ``user_id``
(documents store ``user_id``, so the old index was dead). New indexes are created
automatically on startup, but the engine never drops removed ones, so the stale
``author_id_1`` index lingers. This removes it.

Idempotent: a missing index is a no-op.

    python -m migrations.scripts.m3_drop_orphan_indexes           # dry run
    python -m migrations.scripts.m3_drop_orphan_indexes --apply
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args

# (database, collection, index_name) tuples to drop.
_ORPHAN_INDEXES = [
    ("Suggestions", "Suggestions", "author_id_1"),
]


def main() -> int:
    args = parse_args(__doc__)
    client = connect()

    dropped = 0
    for db_name, coll_name, index_name in _ORPHAN_INDEXES:
        coll = client[db_name][coll_name]
        existing = {ix["name"] for ix in coll.list_indexes()}
        if index_name not in existing:
            print(f"  {db_name}.{coll_name}: '{index_name}' not present - skip")
            continue
        if args.apply:
            coll.drop_index(index_name)
            print(f"  {db_name}.{coll_name}: dropped '{index_name}'")
        else:
            print(f"  {db_name}.{coll_name}: would drop '{index_name}'")
        dropped += 1

    verb = "Dropped" if args.apply else "Would drop"
    print(f"{verb} {dropped} orphaned index(es).")
    if not args.apply and dropped:
        print("Dry run only - re-run with --apply.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
