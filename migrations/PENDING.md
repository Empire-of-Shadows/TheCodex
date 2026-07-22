# Pending migrations

Migrations required as a consequence of the 2026-07-20 Fable 5 audit rulings and fixes.
Each follows the standard framework in [`scripts/_common.py`](scripts/_common.py) -
dry-run by default, `--apply` to write, idempotent - and is dry-run-verified against
production before `--apply`.

## 1. Int-ID -> string normalization  (IS-4 ruling)  -  ALL APPLIED 2026-07-21

> **m5-m10 were applied and verified 2026-07-21** (every script re-run reports 0 int
> docs remaining; m4 verified still clean). The flipped code must be deployed in the
> same window; if the old bot wrote any int doc between apply and redeploy, re-running
> the affected script after redeploy is a safe idempotent cleanup.

The full set is now written; the field-by-field audit behind it found two corrections to
the assumptions above: `daily_wyr_mappings` was NOT all-string (its `guild_id`/`channel_id`
were int; `message_id` was already str), and `prime_drops.sent_by_guild` needs NO migration
(BSON map keys are inherently strings; no other int IDs in those docs).

| Script | Converts |
|---|---|
| `m4_guildconfig_guild_id_to_str` | Settings.GuildConfig `guild_id` (**APPLIED 2026-07-21**) |
| `m5_suggestions_ids_to_str` | Suggestions.{Suggestions,Votes,UserStats,NotificationQueue} snowflakes |
| `m6_wyr_mappings_ids_to_str` | Daily.WYR_Mappings `guild_id`/`channel_id` (`question_id` stays int - not a snowflake) |
| `m7_updates_stats_guild_id_to_str` | Updates-Drops Stats{Monthly,Weekly,Totals} compound `_id.guild_id` (copy-and-replace, insert-before-delete) |
| `m8_audit_log_ids_to_str` | Settings.AuditLog `guild_id`/`actor_id` |
| `m9_guildconfig_role_ids_to_str` | Settings.GuildConfig `roles.admin_role_ids`/`roles.mod_role_ids` elements |
| `m10_serverdata_color_guide_ids_to_str` | ServerData snapshots + Boosts/Boost_Events/Whitelist, Settings.ColorSets/Assignments, Guide.Content |

Shared conversion helpers: `scripts/_int_ids.py` (guarded aggregation-pipeline `$set`,
idempotent; scalar / id-array / subdoc-array shapes).

**Writers are already flipped in the tree** (deploy atomically with the `--apply` run,
bot + dashboard down): engine `discord/extractors.py` + `discord/service.py` (str IDs +
string query boundary), engine `AuditLog.log_config_change` (`actor_id` now str), engine
`GuildConfigStore.add_role`/`remove_role` (store str, `$pull` matches both forms);
codex `suggest.py`, WYR mappings, `drops-tracker.py`, `joining.py` (cleanup + whitelist),
`whitelist.py`, `whitelist_role_cleanup.py`, `boost_tracker.py`, `guide_store.py`/`guide.py`,
`color_set_actions.py`, admin suggestion actions (master), audit bindings; dashboard
`settings.py`, `audit_log.py`, `activity.py`, `user_data.py`, `builder.py`.

In-memory convention: `GuildConfig.from_dict` still coerces the role lists to int
(comparisons against discord.py's int role ids); `to_dict` serializes them back to str.
Storage is string; memory is whatever the consumer needs.

**Runbook (downtime window):** stop bot + dashboard -> run m5 through m10 each with
`--apply` (order does not matter; each is independent and idempotent) -> deploy this
code -> start both. Verify each script reports 0 remaining.

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
