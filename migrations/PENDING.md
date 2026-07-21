# Pending migrations

Migrations required as a consequence of the 2026-07-20 Fable 5 audit rulings and fixes.
These are **not yet written**. Each must follow the standard framework in
[`scripts/_common.py`](scripts/_common.py) - dry-run by default, `--apply` to write,
idempotent - and be dry-run-verified against production before `--apply`.

## 1. Int-ID -> string normalization  (IS-4 ruling: string IDs are canonical)

TheCodex stores guild/user/role/channel IDs as raw ints in most collections. The WYR
collections are the exception - they already use strings. The ecosystem ruling
(`EmpireSystems/README.md` "Settled standard") makes string IDs canonical everywhere.

> **Partially done (2026-07-21):** `Settings.GuildConfig.guild_id` is covered by the
> WRITTEN migration `scripts/m4_guildconfig_guild_id_to_str.py` (DU-2 Phase C). The
> config layer, dashboard routers, and cleanup paths are already flipped to string
> keys in code; that code and the m4 `--apply` MUST deploy together with the bot and
> dashboard down. Everything else below (other collections, role-id lists, actor_id,
> audit-log guild_id) remains pending.

- **Before writing:** audit EVERY collection in `storage/settings/collections.py`
  field-by-field for int-typed ID fields. Known int-ID areas:
  - `serverdata_*` snapshot collections: `id`, `guild_id`, `owner_id`, `top_role_id`,
    `system_channel_id`, role/member id lists, `user_list`, etc. (written by
    `storage_engine/discord/extractors.py`, still int by design pending this migration).
  - `suggestions_*`: `user_id`, `message_id`, and any actor ids.
  - `prime_drops`: the `sent_by_guild.<guild_id>` map keys.
  - structured config `roles.admin_role_ids` / `roles.mod_role_ids` (from_dict currently
    coerces these to int via `_as_int_id_list`; that coercion must flip to str too).
  - `storage/audit_log.py` writes an int `actor_id` beside a str `guild_id` in one doc
    (the engine `services/audit_log.py` has the same shape) - normalize `actor_id` to str.
  - **Leave WYR collections alone** - already string, cleanup traced correct.
- **Approach:** per collection, convert ID fields to string form with an aggregation-pipeline
  `$set` (`{"$toString": "$field"}`) so each doc converts atomically. Idempotent: converting
  an already-string value is a no-op. Unique/compound indexes are type-agnostic, so a
  half-run is safe, but prefer pipeline `$set` over read-modify-write.
- **Rollback:** the inverse (`$toLong`) is safe for Discord snowflakes (they fit int64), but
  prefer forward-only.
- **Also flip the writers** in the same change window so new docs are written as strings:
  `discord/extractors.py` ID fields, `config_manager.from_dict` role-id coercion.

## 2. Snapshot timestamp backfill  (IS-4 extractor fix - OPTIONAL)

`storage_engine/discord/extractors.py` now writes snapshot timestamps as BSON datetimes
(previously ISO-8601 strings). Existing `serverdata_*` docs still hold ISO strings until the
next snapshot cycle overwrites them - snapshots upsert-replace per entity, so this
**self-heals** and the migration is only needed if you want the engine's `delete_before_date`
/ `cleanup_old_data` datetime cutoffs to match pre-existing docs before they refresh.

- **Approach:** for each `serverdata_*` collection, convert string `created_at` / `joined_at`
  / `premium_since` / `timestamp` to datetimes (`{"$dateFromString": ...}`), guarding for
  already-datetime values (idempotent).

Both touch production data: dry-run first, verify counts, then `--apply` from where the
normal replica-set connection reaches the primary.
