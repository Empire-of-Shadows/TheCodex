"""m8: Settings.AuditLog - guild_id / actor_id int -> str (IS-4 normalization).

Both audit writers (the bot's admin bindings and the dashboard settings router) stored
int ``guild_id`` and ``actor_id``; the dashboard audit reader filters by int guild_id.
This converts the stored entries; the writers and the reader flip to string in the same
deploy window. (The engine ``AuditLog.log_config_change`` helper is fixed to stringify
``actor_id`` in the same pass, so both audit code paths finally agree.)

Idempotent, dry-run by default.

    python -m migrations.scripts.m8_audit_log_ids_to_str            # dry run
    python -m migrations.scripts.m8_audit_log_ids_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._int_ids import FieldSpec, convert_collection


def main() -> None:
    args = parse_args("Settings.AuditLog guild_id/actor_id int -> str (IS-4).")
    client = connect()
    try:
        pending = convert_collection(
            client["Settings"], "AuditLog",
            [FieldSpec("guild_id"), FieldSpec("actor_id")],
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
