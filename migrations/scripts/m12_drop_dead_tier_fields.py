"""m12: remove two dead GuildConfig fields left behind by the v2 collapse.

Both fields are read by nothing current and written by nothing at all. They are dropped
per the repo rule that once code stops reading a field, a migration `$unset`s it so no
orphaned data lingers.

    roles.tiers          - vestigial role->tier map from an older schema generation.
    embed.color_tiers    - the old per-tier {name: hex} dict.

**roles.tiers came with a live bug.** ``GuildConfig.get_all_tier_role_ids()`` still read
it, and it is the third branch of ``has_embed_permissions`` in
``Features/ce_utilities/create_embed.py``. Since nothing has written ``roles.tiers`` since
the v2 collapse it was always ``{}``, so that branch could never pass: members granted
embed access purely through the admin panel's **Role Tier Mapping** silently failed the
check and only got in if they also held an admin or mod role. The accessor now reads
``embed.role_tier``, which is the map the panel actually writes. That code fix ships with
this migration - the migration only removes the stale storage.

``embed.color_tiers`` was superseded by the Color Set collections
(``Settings.ColorSets`` / ``ColorSetAssignments``). Its five ``EmbedConfigActions``
accessors had no callers and have been deleted. **No data is carried across**: the Color
Set system has been the live source of member colors for some time, so anything still in
``embed.color_tiers`` is a pre-supersession leftover, not current configuration.

Idempotent: `$unset` only matches documents that still carry the key, so a re-run after
--apply matches nothing. Dry-run by default.

    python -m migrations.scripts.m12_drop_dead_tier_fields            # dry run (no writes)
    python -m migrations.scripts.m12_drop_dead_tier_fields --apply    # perform the writes

Run the DRY RUN first and confirm the counts. The dry run prints any NON-EMPTY value it is
about to drop, so you can eyeball whether a guild still had something in these fields
before it goes. Deploy the code that stops defaulting these keys in the same window,
otherwise the next ``save_config`` writes ``{}`` back.
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args

_DB = "Settings"
_COLL = "GuildConfig"

_DEAD_FIELDS = ["roles.tiers", "embed.color_tiers"]


def main() -> None:
    args = parse_args("Remove the dead roles.tiers and embed.color_tiers fields.")
    client = connect()
    try:
        coll = client[_DB][_COLL]

        total = coll.count_documents({})
        print(f"{_DB}.{_COLL}: {total} doc(s).")

        pending = {}
        for path in _DEAD_FIELDS:
            pending[path] = coll.count_documents({path: {"$exists": True}})
            print(f"  {path}: {pending[path]} doc(s) carry this field.")

        if not any(pending.values()):
            print("Nothing to remove. (Idempotent no-op.)")
            return

        # Surface any doc whose dead field is NOT empty. Dropping {} is uninteresting;
        # dropping real content is worth a human look before it goes.
        non_empty = 0
        for path in _DEAD_FIELDS:
            cursor = coll.find(
                {path: {"$exists": True, "$nin": [{}, None]}},
                {"guild_id": 1, path: 1},
            )
            for doc in cursor:
                non_empty += 1
                section, _, key = path.partition(".")
                value = (doc.get(section) or {}).get(key)
                print(f"  NON-EMPTY {path} on guild_id={doc.get('guild_id')!r}: {value!r}")
        if non_empty:
            print(f"  ^ {non_empty} doc(s) hold a non-empty value in a dead field.")
        else:
            print("  All present values are empty ({} or null) - nothing of substance is lost.")

        if not args.apply:
            print(f"DRY RUN: would unset {sum(pending.values())} field instance(s). "
                  f"Re-run with --apply to write.")
            return

        for path in _DEAD_FIELDS:
            result = coll.update_many(
                {path: {"$exists": True}}, {"$unset": {path: ""}},
            )
            print(f"APPLIED unset {path}: matched={result.matched_count} "
                  f"modified={result.modified_count}.")

        remaining = sum(
            coll.count_documents({path: {"$exists": True}}) for path in _DEAD_FIELDS
        )
        print(f"Verify: remaining docs with a dead field = {remaining} (should be 0).")
    finally:
        client.close()


if __name__ == "__main__":
    main()
