"""m9: Settings.GuildConfig - roles.admin_role_ids / roles.mod_role_ids int -> str.

The panel-permission role lists inside the (already string-keyed, see m4) GuildConfig
document still hold int role IDs. This converts the list elements to strings - the
storage-canonical form. In code (same deploy window):

- ``GuildConfig.to_dict`` stringifies the lists on the way OUT (so saves write str),
  while ``from_dict``'s ``_as_int_id_list`` keeps coercing to int on the way IN
  (bot-side permission checks compare against discord.py's int role ids).
- The engine ``GuildConfigStore.add_role`` / ``remove_role`` store str role ids.
- The dashboard settings PUT keeps role-list entries as strings instead of
  int-coercing them.

Readers are unaffected mid-migration: the bot int-coerces on read, the dashboard
str-coerces on read - both handle either stored form.

    python -m migrations.scripts.m9_guildconfig_role_ids_to_str            # dry run
    python -m migrations.scripts.m9_guildconfig_role_ids_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._int_ids import FieldSpec, convert_collection


def main() -> None:
    args = parse_args("Settings.GuildConfig roles.*_role_ids int -> str (IS-4).")
    client = connect()
    try:
        pending = convert_collection(
            client["Settings"], "GuildConfig",
            [
                FieldSpec("roles.admin_role_ids", kind="id_array"),
                FieldSpec("roles.mod_role_ids", kind="id_array"),
            ],
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
