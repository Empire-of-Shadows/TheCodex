"""m11: rename the new_members welcome_* keys to greeting_*.

The per-join message TheCodex sends when a member arrives used to be called the
"welcome message". A separate, static info board now lives in the welcome channel,
so the per-join message was renamed to the **greeting** to keep the two apart.

The code no longer reads the old key names, and `GuildConfig.from_dict` has a
fixed-key whitelist, so any document left on the old names loses its configured
greeting layout, channel, and toggle on the next reload. This migration brings the
stored documents to the current schema:

    new_members.welcome_components      -> new_members.greeting_components
    new_members.welcome_channel_id      -> new_members.greeting_channel_id
    new_members.welcome_message_enabled -> new_members.greeting_enabled

Idempotent: each key is renamed only on documents that still carry the old name,
so a re-run after --apply matches nothing. Dry-run by default.

    python -m migrations.scripts.m11_welcome_to_greeting            # dry run (no writes)
    python -m migrations.scripts.m11_welcome_to_greeting --apply    # perform the writes

Run the DRY RUN first and confirm the counts, then --apply. Bring the bot and
dashboard down for the apply so no writer races the rename, and redeploy them on
the greeting-named code afterwards.
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args

_DB = "Settings"
_COLL = "GuildConfig"

# (old key, new key) pairs, all nested under new_members.
_RENAMES = [
    ("new_members.welcome_components", "new_members.greeting_components"),
    ("new_members.welcome_channel_id", "new_members.greeting_channel_id"),
    ("new_members.welcome_message_enabled", "new_members.greeting_enabled"),
]


def _pending_query(old: str, new: str) -> dict:
    """Docs that still carry `old`. `new` must not already exist, because $rename
    would silently overwrite it and destroy the newer value."""
    return {old: {"$exists": True}, new: {"$exists": False}}


def main() -> None:
    args = parse_args("Rename new_members.welcome_* keys to greeting_*.")
    client = connect()
    try:
        coll = client[_DB][_COLL]

        total = coll.count_documents({})
        print(f"{_DB}.{_COLL}: {total} doc(s).")

        # Safety: a doc holding BOTH names for the same setting is ambiguous - we
        # cannot know which value is current, so refuse rather than guess.
        conflicts = []
        for old, new in _RENAMES:
            n = coll.count_documents({old: {"$exists": True}, new: {"$exists": True}})
            if n:
                conflicts.append((old, new, n))
        if conflicts:
            for old, new, n in conflicts:
                print(f"ABORT: {n} doc(s) carry both {old} and {new}.")
            print("Resolve the duplicate keys by hand before running this migration.")
            return

        pending = {}
        for old, new in _RENAMES:
            pending[(old, new)] = coll.count_documents(_pending_query(old, new))
            print(f"  {old} -> {new}: {pending[(old, new)]} doc(s) to rename.")

        if not any(pending.values()):
            print("Nothing to rename. (Idempotent no-op.)")
            return

        if not args.apply:
            for (old, new), n in pending.items():
                if not n:
                    continue
                for d in coll.find(_pending_query(old, new), {"guild_id": 1}).limit(5):
                    print(f"  would rename {old} -> {new} on guild_id={d.get('guild_id')!r}")
            print(f"DRY RUN: would rename {sum(pending.values())} key(s). "
                  f"Re-run with --apply to write.")
            return

        for old, new in _RENAMES:
            result = coll.update_many(_pending_query(old, new), {"$rename": {old: new}})
            print(f"APPLIED {old} -> {new}: matched={result.matched_count} "
                  f"modified={result.modified_count}.")

        remaining = sum(
            coll.count_documents({old: {"$exists": True}}) for old, _ in _RENAMES
        )
        print(f"Verify: remaining docs with an old welcome_* key = {remaining} (should be 0).")
    finally:
        client.close()


if __name__ == "__main__":
    main()
