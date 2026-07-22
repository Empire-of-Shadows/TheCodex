"""m6: Daily.WYR_Mappings - guild_id / channel_id int -> str (IS-4 normalization).

WYR_Mappings is the one WYR collection that still stores int IDs: its writer
stringified ``message_id`` but left ``guild_id`` and ``channel_id`` raw. The other
three WYR collections (WYR, WYR_Leaderboard, WYR_Votes) are already string-keyed and
are NOT touched. ``question_id`` is an internal question number, not a snowflake -
it stays an int everywhere.

Idempotent, dry-run by default. Deploy with the flipped writer/readers in WYR.py and
the joining.py cleanup, bot down.

    python -m migrations.scripts.m6_wyr_mappings_ids_to_str            # dry run
    python -m migrations.scripts.m6_wyr_mappings_ids_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._int_ids import FieldSpec, convert_collection


def main() -> None:
    args = parse_args("Daily.WYR_Mappings guild_id/channel_id int -> str (IS-4).")
    client = connect()
    try:
        pending = convert_collection(
            client["Daily"], "WYR_Mappings",
            [FieldSpec("guild_id"), FieldSpec("channel_id")],
            args.apply,
        )
        if pending == 0:
            print("Nothing to convert. (Idempotent no-op.)")
        elif not args.apply:
            print(f"DRY RUN: {pending} doc(s). Re-run with --apply.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
