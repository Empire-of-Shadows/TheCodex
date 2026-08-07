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

## 3. Dead tier fields  (`m12_drop_dead_tier_fields`)  -  NOTHING TO DO (verified 2026-08-01)

> **Dry-run against production reports a no-op.** `Settings.GuildConfig` holds 2 documents;
> **0** carry `roles.tiers` and **0** carry `embed.color_tiers`. Neither field was ever
> persisted - they existed only as in-memory defaults, and the code that produced those
> defaults was removed before any `save_config` wrote them down. There is no orphaned data
> to drop, so `--apply` would match nothing.
>
> The script is kept rather than deleted: it is idempotent, it costs nothing to leave in
> place, and it documents why the two fields are gone. **No action is required.** The rest
> of this section is the original analysis and stays for the record.

From the 2026-07-29 admin-panel placeholder audit
([`.docs/TheCodex/ADMIN_PANEL_PLACEHOLDERS.md`](../../../.docs/TheCodex/ADMIN_PANEL_PLACEHOLDERS.md)).
`$unset`s two GuildConfig fields that nothing writes and nothing current reads:

| Field | Why it is dead |
|---|---|
| `roles.tiers` | Vestigial role->tier map from a pre-v2-collapse generation. |
| `embed.color_tiers` | Old per-tier `{name: hex}` dict, superseded by the Color Set collections. |

**`roles.tiers` carried a live bug, fixed in the same change.**
`GuildConfig.get_all_tier_role_ids()` read it, and that is the third branch of
`has_embed_permissions` in `Features/ce_utilities/create_embed.py`. Nothing had written
`roles.tiers` since the v2 collapse, so it was always `{}` and the branch could never pass:
members granted embed access purely through the admin panel's **Role Tier Mapping** failed
the check and only got in if they also held an admin or mod role. The accessor now reads
`embed.role_tier`, which is what the panel actually writes.

**Code that ships with this migration** (deploy together - `from_dict` uses
`_merge_unknown_keys`, so a stored key survives in memory until it is `$unset`, and the
defaults would otherwise write `{}` back on the next `save_config`):

- `storage/settings/config_manager.py` - `get_all_tier_role_ids()` repointed at
  `embed.role_tier`; both keys dropped from `_default_roles()` / `_default_embed()` and from
  `from_dict`; the unused `GuildConfigManager.embed_color_tiers()` accessor removed.
- `admin/actions/embed_config_actions.py` - the five dead `embed.color_tiers` accessors
  (`get_color_tiers`, `set_tier_colors`, `add_color`, `remove_color`, `remove_tier`) removed;
  all had zero callers.

**No data is carried across.** The Color Set collections have been the live source of member
colors for some time, so anything still in `embed.color_tiers` is a pre-supersession
leftover. The dry run prints every NON-EMPTY value it is about to drop so you can eyeball
this before committing.

**Runbook:** dry-run, read the non-empty report, then `--apply` and deploy the code in the
same window. *(Superseded 2026-08-01 - the dry run found nothing to remove. The code half
is already deployed; there is no data half to run.)*

## 4. Retired moderator tier  (`m13_drop_mod_role_ids`)  -  NOT YET RUN

From the owner ruling of 2026-08-04: admin surfaces are **admin-only fleet-wide**. There is
no Mod tier - a former mod-role holder cannot open, view, or write anything on the admin
panel or the web dashboard. Codex converted 2026-08-06.

`$unset`s one GuildConfig field the code no longer reads:

| Field | Why it is dead |
|---|---|
| `roles.mod_role_ids` | The Mod Access role list. Nothing resolves the tier any more. |

**Code that ships with this migration** (deploy together - `from_dict` uses
`_merge_unknown_keys`, so a stored key survives in memory until it is `$unset`, and the
defaults would otherwise write it back on the next `save_config`):

- `admin/settings/bindings.py` - `resolve_panel_role` collapses to `"admin"` / `"none"`;
  `MOD_ALLOWED_CATEGORIES` removed; `ROLE_ACCESS_PATH` added for the flattened node.
- `admin/settings/panel_configs.py` - `panel_roles_pair(include_mod=False)`; the
  single-child "Role Configuration" wrapper menu flattened to a top-level **Panel Access
  Roles** leaf (ADMIN_PANEL_STANDARD.md 1.1); every `mod_allowed=` flag dropped.
- `storage/settings/config_manager.py` - `mod_role_ids` out of `_default_roles()`,
  `to_dict`, `from_dict`; `is_moderator_role` / `is_staff_role` / `has_staff_role` removed
  (zero callers); `set_role` no longer accepts `"moderator"`.
- Feature permission checks now admin-only: `Features/Board/board.py`,
  `Features/ce_utilities/create_embed.py`, `Features/NewMembers/admin/whitelist.py`,
  `Features/NewMembers/admin/greetingtrigger.py`.
- Dashboard - `auth/panel_role.py` two-tier; `routers/settings.py` drops
  `MOD_ALLOWED_SECTIONS`; `routers/dashboard.py` drops `can_access_mod_any`; frontend
  `PanelRole` narrowed and every mod-tier control removed.

**No access is carried across.** Mod role ids are deliberately NOT merged into
`roles.admin_role_ids` - that would widen access, the opposite of the ruling. The dry run
prints every non-empty list so the admin can re-grant Panel Access by hand where intended.

**Runbook:** dry-run, capture the non-empty report (the role ids are not recoverable from
the document afterwards), then `--apply` and deploy the code in the same window.
