"""m5: Suggestions domain - Discord snowflake IDs int -> str (IS-4 normalization).

Converts every snowflake-ID field in the Suggestions collections to the canonical
string form. ``suggestion_id`` is already a UUID string and ``_id`` is an ObjectId;
neither is touched.

    Suggestions.Suggestions        guild_id, user_id, message_id, thread_id, last_updated_by
    Suggestions.Votes              user_id
    Suggestions.UserStats          user_id
    Suggestions.NotificationQueue  user_id

Idempotent, dry-run by default. Deploy the string-keyed code (suggest.py, the admin
suggestions actions, dashboard activity/user_data routes) atomically with ``--apply``,
bot and dashboard down.

    python -m migrations.scripts.m5_suggestions_ids_to_str            # dry run
    python -m migrations.scripts.m5_suggestions_ids_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._int_ids import FieldSpec, convert_collection

_PLAN = {
    "Suggestions": [
        FieldSpec("guild_id"),
        FieldSpec("user_id"),
        FieldSpec("message_id"),
        FieldSpec("thread_id"),
        FieldSpec("last_updated_by"),
    ],
    "Votes": [FieldSpec("user_id")],
    "UserStats": [FieldSpec("user_id")],
    "NotificationQueue": [FieldSpec("user_id")],
}


def main() -> None:
    args = parse_args("Suggestions domain snowflake IDs int -> str (IS-4).")
    client = connect()
    try:
        db = client["Suggestions"]
        pending = sum(
            convert_collection(db, coll, specs, args.apply)
            for coll, specs in _PLAN.items()
        )
        if pending == 0:
            print("Nothing to convert. (Idempotent no-op.)")
        elif not args.apply:
            print(f"DRY RUN: {pending} doc(s) across the domain. Re-run with --apply.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
