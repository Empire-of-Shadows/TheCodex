"""m13: remove the retired moderator tier from GuildConfig.

Owner ruling of 2026-08-04: admin surfaces are ADMIN-ONLY fleet-wide. There is no Mod
tier - a former mod-role holder can no longer open, view, or write anything on the admin
panel or the web dashboard. TheCodex's code stopped reading ``roles.mod_role_ids`` on
2026-08-06, so per the repo rule (once code stops reading a field, a migration ``$unset``s
it) the stored key goes too.

    roles.mod_role_ids   - the Mod Access role list.

**Why the data half matters here.** ``GuildConfig.from_dict`` runs every section through
``_merge_unknown_keys``, which preserves stored subkeys the dataclass does not model. A
field deleted from the code therefore keeps round-tripping load -> save until it is
``$unset``: the panel would carry a Mod Access list nothing honors, and the dashboard's
settings GET would keep echoing a key its PUT now rejects as unknown. (The dashboard also
lists the key in ``_SECTION_EXCLUDED_KEYS["roles"]`` so it cannot be echoed back before
this runs - that exclusion is what keeps Panel Access Roles saveable in the meantime.)

**No access is carried across.** Mod role ids are deliberately NOT merged into
``roles.admin_role_ids``: mods were a strictly lower tier and promoting them to full admin
would widen access, which is the opposite of the ruling. The dry run prints every
NON-EMPTY list it is about to drop so an admin can note which roles held the tier and
re-grant Panel Access by hand where they want to.

Idempotent: ``$unset`` only matches documents that still carry the key, so a re-run after
--apply matches nothing. Dry-run by default.

    python -m migrations.scripts.m13_drop_mod_role_ids            # dry run (no writes)
    python -m migrations.scripts.m13_drop_mod_role_ids --apply    # perform the writes

Run the DRY RUN first and confirm the counts. Deploy the code that stops defaulting this
key in the same window, otherwise the next ``save_config`` writes it back.

Rollback: this drops a field the code no longer reads, so rolling the CODE back is the
rollback - re-deploying the previous build restores ``mod_role_ids: []`` as a default and
the Mod tier resolves to empty. The role ids themselves are not recoverable from the
document once applied, which is why the dry run prints them: capture that output before
running --apply if you want a record.

APPLIED against production 2026-08-06 (bot down): matched=2 modified=2, verify 0
remaining. The two dropped lists are recorded in migrations/PENDING.md section 4.
Re-running is a no-op.
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args

_DB = "Settings"
_COLL = "GuildConfig"

_DEAD_FIELD = "roles.mod_role_ids"


def main() -> None:
    args = parse_args("Remove the retired roles.mod_role_ids field (no Mod tier).")
    client = connect()
    try:
        coll = client[_DB][_COLL]

        total = coll.count_documents({})
        pending = coll.count_documents({_DEAD_FIELD: {"$exists": True}})
        print(f"{_DB}.{_COLL}: {total} doc(s).")
        print(f"  {_DEAD_FIELD}: {pending} doc(s) carry this field.")

        if not pending:
            print("Nothing to remove. (Idempotent no-op.)")
            return

        # Surface any doc whose mod list is NOT empty. Dropping [] is uninteresting;
        # dropping real role ids means a server actually delegated the tier, and the
        # admin will want to know which roles just lost it.
        non_empty = 0
        cursor = coll.find(
            {_DEAD_FIELD: {"$exists": True, "$nin": [[], None]}},
            {"guild_id": 1, _DEAD_FIELD: 1},
        )
        for doc in cursor:
            non_empty += 1
            value = (doc.get("roles") or {}).get("mod_role_ids")
            print(f"  NON-EMPTY {_DEAD_FIELD} on guild_id={doc.get('guild_id')!r}: {value!r}")
        if non_empty:
            print(f"  ^ {non_empty} doc(s) had roles holding the Mod tier. Those roles lose "
                  f"panel access; re-grant Panel Access Roles by hand where intended.")
        else:
            print("  All present values are empty - no server had delegated the Mod tier.")

        if not args.apply:
            print(f"DRY RUN: would unset {pending} field instance(s). "
                  f"Re-run with --apply to write.")
            return

        result = coll.update_many(
            {_DEAD_FIELD: {"$exists": True}}, {"$unset": {_DEAD_FIELD: ""}},
        )
        print(f"APPLIED unset {_DEAD_FIELD}: matched={result.matched_count} "
              f"modified={result.modified_count}.")

        remaining = coll.count_documents({_DEAD_FIELD: {"$exists": True}})
        print(f"Verify: remaining docs with {_DEAD_FIELD} = {remaining} (should be 0).")
    finally:
        client.close()


if __name__ == "__main__":
    main()
