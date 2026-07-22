"""m10: ServerData snapshots + boosts/whitelist + ColorSets + Guide - IDs int -> str.

The final IS-4 batch: every remaining int snowflake field across

    ServerData.Guilds        id, owner_id, system_channel_id, rules_channel_id,
                             public_updates_channel_id
    ServerData.Channels      guild_id, id, category_id, last_message_id,
                             user_list[], permissions[].id, archived_threads[].id
    ServerData.Roles         guild_id, id
    ServerData.Members       guild_id, id, top_role_id, voice_channel_id, roles[]
    ServerData.Analytics     guild_id
    ServerData.Events        guild_id
    ServerData.Boosts        guild_id, user_id
    ServerData.Boost_Events  guild_id, user_id
    ServerData.Whitelist     guild_id, user_id, added_by, removed_by, reactivated_by
    Settings.ColorSets       guild_id
    Settings.ColorSetAssignments  guild_id   (target_id is ALREADY a string - untouched)
    Guide.Content            guild_id, updated_by

The snapshot collections (Guilds/Channels/Roles/Members) also self-heal on the next
snapshot cycle, but converting them is required anyway: the flipped writers upsert on
string identity filters, and without conversion the old int docs would linger as
duplicates beside new string docs.

Idempotent, dry-run by default. Deploy atomically with the flipped engine extractors +
snapshot service and all flipped bot/dashboard callers, bot and dashboard down.

    python -m migrations.scripts.m10_serverdata_color_guide_ids_to_str            # dry run
    python -m migrations.scripts.m10_serverdata_color_guide_ids_to_str --apply    # write
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._int_ids import FieldSpec, convert_collection

_PLAN = {
    "ServerData": {
        "Guilds": [
            FieldSpec("id"),
            FieldSpec("owner_id"),
            FieldSpec("system_channel_id"),
            FieldSpec("rules_channel_id"),
            FieldSpec("public_updates_channel_id"),
        ],
        "Channels": [
            FieldSpec("guild_id"),
            FieldSpec("id"),
            FieldSpec("category_id"),
            FieldSpec("last_message_id"),
            FieldSpec("user_list", kind="id_array"),
            FieldSpec("permissions", kind="subdoc_array", subfield="id"),
            FieldSpec("archived_threads", kind="subdoc_array", subfield="id"),
        ],
        "Roles": [FieldSpec("guild_id"), FieldSpec("id")],
        "Members": [
            FieldSpec("guild_id"),
            FieldSpec("id"),
            FieldSpec("top_role_id"),
            FieldSpec("voice_channel_id"),
            FieldSpec("roles", kind="id_array"),
        ],
        "Analytics": [FieldSpec("guild_id")],
        "Events": [FieldSpec("guild_id")],
        "Boosts": [FieldSpec("guild_id"), FieldSpec("user_id")],
        "Boost_Events": [FieldSpec("guild_id"), FieldSpec("user_id")],
        "Whitelist": [
            FieldSpec("guild_id"),
            FieldSpec("user_id"),
            FieldSpec("added_by"),
            FieldSpec("removed_by"),
            FieldSpec("reactivated_by"),
        ],
    },
    "Settings": {
        "ColorSets": [FieldSpec("guild_id")],
        "ColorSetAssignments": [FieldSpec("guild_id")],
    },
    "Guide": {
        "Content": [FieldSpec("guild_id"), FieldSpec("updated_by")],
    },
}


def main() -> None:
    args = parse_args("ServerData/ColorSets/Guide snowflake IDs int -> str (IS-4).")
    client = connect()
    try:
        total_pending = 0
        for db_name, colls in _PLAN.items():
            db = client[db_name]
            for coll, specs in colls.items():
                total_pending += convert_collection(db, coll, specs, args.apply)
        if total_pending == 0:
            print("Nothing to convert. (Idempotent no-op.)")
        elif not args.apply:
            print(f"DRY RUN: {total_pending} doc(s) across all collections. "
                  f"Re-run with --apply.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
