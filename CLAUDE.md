# CLAUDE.md

Guidance for Claude Code when working in TheCodex (`codex`).

This file deliberately does **not** restate what you can read from the repo - there is no
directory tour, no entry-point walkthrough, no changelog format block. Read the code for
those. What is here is the stuff that is expensive or impossible to discover by reading:
ownership boundaries, invariants, and the specific things that have already gone wrong.

Root `../../CLAUDE.md` holds the ecosystem-wide rules (no gambling, hyphen-minus only,
changelog mandate, migrations over fresh starts, no compat shims). They apply here.

## The one thing the name gets wrong

**TheCodex does not use an LLM.** Its knowledge base is RapidFuzz fuzzy search over curated
markdown. Do not reach for the Claude API here.

## Engine distribution: vendored, never edit the copy

Both shared engines are **vendored copies**; codex does not pip-install `EmpireSystems`.
Files with a `# VENDORED ... DO NOT EDIT HERE` banner are generated - edit the master in
`../../EmpireSystems/` and re-run the sync tool. `--check` gates drift:

```bash
# from the monorepo root
python EmpireSystems/tools/sync_admin_engine.py   --check --bot codex
python EmpireSystems/tools/sync_storage_engine.py --check --bot codex
```

**The seam** (codex's to hand-edit inside the engine dirs) is exactly:
`storage/settings/`, `admin/settings/`, and the bot-owned modules in `admin/actions/` and
`admin/views/`. Everything else under `storage/` and `admin/` is generated, including the
master-owned `admin/bot_specific/codex/` subtree (edit that at
`EmpireSystems/admin_engine/bot_specific/codex/`; a file here the master lacks is `[ORPHAN]`).

**Two MIXED directories** - the banner is the only reliable signal, so check it before editing:

| Dir | Vendored | Bot-owned |
|---|---|---|
| `admin/actions/` | the subpackages `collections/ config/ data/ discord_objects/ features/ structure/` | `__init__.py`, `*_actions.py`, `*_nodes.py`, `panel_flow.py` |
| `admin/views/` | `__init__.py`, `base.py`, `panel_engine.py`, `panel_views.py` | the per-feature view modules |

**Changing an engine master is a 7-repo operation.** `EmpireSystems/` is its **own git repo**,
and all **6** bots vendor the admin engine on the same `settings` layout - so a master edit means
`sync_admin_engine.py` (no `--check`) plus a commit in EmpireSystems *and* in every bot repo
whose vendored copy changed. Prefer **additive, opt-in-defaulted** changes so no other bot's
behavior moves, and prove it: diff old-rule vs new-rule over each bot's `MAIN_PANEL` rather than
assuming.

**Adopt engine services, do not re-roll them.** Codex uses the engine `AuditLog` and `SetupGate`
(the old hand-rolled `AuditLogger` / `SetupGatekeeper` are gone). Every "not configured yet" and
"you do not have the tier" message comes from `admin/setup_notice.py` - do not hand-write one; it
names the panel breadcrumb *and* who can actually open the panel, which on a fresh guild is only
the owner and Manage Server holders.

## Gotchas - things that have already tripped us up

### Admin panel / PanelNode

- **A childless `kind="menu"` node is a dead end.** It renders its description and a Back button
  and nothing else - no controls, no error. Six panel entries shipped like this as label-only
  "reserved slots"; see `.docs/TheCodex/ADMIN_PANEL_PLACEHOLDERS.md`. Never create one.
- **`kind="action"` covers two unrelated things.** Stateless one-shots (View Status, Export,
  Publish, Reset) *and* bespoke settings editors that own real config. A stateful one needs
  **three** things or it half-works:
  `get_values` (so "configured" is decidable), `summary_builder` (or its summary line renders
  **blank**), and `counts_as_setting=True` (or the category's "N of M configured" badge silently
  ignores it - and a category built entirely from such nodes shows *no badge at all*).
  A `summary_builder`'s empty state **must** return one of the engine's `_UNSET_SUMMARIES`
  strings (`"Not configured"` / `"Not set"` / `"Not assigned"` / `"Empty"`) or the badge
  over-counts.
- **`action` nodes do not get the engine's permission pre-checks** that `role_select` /
  `channel_select` leaves get for free. Declare `requires_role_manage` /
  `required_channel_perms` and call `check_role_permissions` / `check_channel_permissions`
  yourself, or the setting saves and then fails silently at runtime.
- **Render bespoke flows through `cog._rebind_session_view(ctx.session, layout)`.** A freshly
  built `LayoutView` otherwise loses the panel's author lock and runs on its own 300s timeout
  instead of the session's shared idle timer. (The vendored `info_action` and the suggestion
  nodes do not do this - do not take them as the example.)
- **Modal submits: respond with `modal_interaction.response.edit_message(...)`.** UPDATE_MESSAGE
  is legal because every panel modal opens from a component on message 2. Do **not** copy
  `_handle_inline_modal`'s pattern of deferring the modal interaction and then calling
  `edit_original_response` on the component interaction whose response was already consumed by
  `send_modal` - the engine wraps that call in `try/except HTTPException`, which suggests it does
  not reliably land.
- **One response per interaction.** To both refresh a screen and explain something, spend the
  response on the re-render and deliver the explanation as a `followup`.
- `admin/actions/panel_flow.py` (`PanelFlow`) exists so you do not re-derive the six points
  above. Subclass it for any new bespoke action flow.

### Storage / config

- **Stored IDs are STRINGS, everywhere.** Migrations m4-m10 ran 2026-07-21; every `guild_id` /
  `user_id` / snowflake in every collection is a string today (verified against production).
  Querying with an `int` matches nothing, silently. In *memory*, `from_dict` coerces the role
  lists back to `int` for comparisons against discord.py's int ids - storage is string, memory is
  whatever the consumer needs.
- **`from_dict` is NOT a fixed-key whitelist.** Every section runs through
  `_merge_unknown_keys`, which preserves stored subkeys the dataclass does not model, so
  load -> save is lossless and a new subkey needs no whitelisting to survive. The corollary is
  the one that bites: a field you *delete from the code* still round-trips from storage until a
  migration `$unset`s it.
- **`save_config` is only surgical when the config carries `_loaded_snapshot`.** It diffs against
  what you loaded and writes just the changed leaves. A hand-constructed `GuildConfig` has no
  snapshot and falls back to a **full write of every top-level section** - so always mutate a
  config you got from `get_config` / `manager.get_config`.

### Auditing dead code

- **"Nothing writes it" does not mean "nothing reads it".** `roles.tiers` had no writers since
  the v2 collapse, so it looked like dead data - but `GuildConfig.get_all_tier_role_ids()` still
  read it, and that is a branch of the `/embed create` permission check. It returned `{}` forever,
  so tier-granted embed access silently never worked for anyone. A field with a live reader and no
  writer is **more** dangerous than one with neither, because the read returns a default that
  looks like a legitimate empty answer. When you find an unwritten field, grep its readers before
  calling it dead.

### Testing panel work

Panel flows can be verified offline, with no Discord and no Mongo, and this catches the bug class
that actually occurs. Fake the cog (`_send_or_edit`, `_rebind_session_view`, `_check_cooldown`,
`_audit`, `_invalidate_guild_caches`, `_navigate_to`) and the interaction (asserting one response
each), stub the `*Actions` class in memory, then **drive the real component callbacks off the
built `LayoutView`** rather than only calling flow methods - the `interaction.data` -> handler
boundary is where callback-arity, payload-shape and closure late-binding bugs hide. Importing
`admin.settings.panel_configs` needs `MONGO_URI` set to any value.

## Production data

Codex has **real users and real data**. Schema changes ship an idempotent migration under
`TestsAndMigrations/TheCodex/migrations/scripts/` (`_common.py` is the harness): dry-run by
default, `--apply` to write, re-runnable as a no-op. Run the dry run, read its report, then
apply. Never "drop the collection and start fresh". Once code stops reading a field, `$unset` it
via migration rather than leaving orphaned data. Prefer migrating documents over carrying
long-term `from_dict()` legacy handling;
`TestsAndMigrations/TheCodex/migrations/scripts/_guildconfig_v2.py` keeps the pre-collapse schema
frozen for reference. Pending work is tracked in
`TestsAndMigrations/TheCodex/migrations/PENDING.md`.

> The `migrations/` tree moved out of this repo to the monorepo-level
> `TestsAndMigrations/TheCodex/migrations/` on 2026-08-08. Paths above are relative to the
> monorepo root, not to this service. The package shape (`migrations.scripts.mN_...`) is
> unchanged, so scripts still run as `python -m migrations.scripts.mN_...` from
> `TestsAndMigrations/TheCodex/` with `MONGO_URI` set.

## Changelog

Mandatory for user-facing changes, written for a community member and not a programmer. The
style is the part that needs judgment:

- **DO** "The guide now understands more ways of asking the same question"
  **DON'T** "Lowered the RapidFuzz match threshold and added query normalization"
- **DO** "Added a shortcut so typing `rules` jumps straight to the server rules"
  **DON'T** "Registered a new entry in the shortcut map"
- **DO** "Fixed broken back-navigation when browsing nested guide sections"
  **DON'T** "Fixed breadcrumb stack pop on nested section traversal"

## Non-obvious conventions

- Slash commands and Components v2 only. `startup/bot.py` builds the bot with
  `when_mentioned`, so there is no text prefix; `load_cogs` survives only as a mention-only
  owner command.
- Health endpoint `:50010`, dashboard `:54010`, shared external `obsidian_grid` Docker network.
- Codex's per-feature logic lives in `Features/` and `commands/`. There is no
  `storage/bot_specific/codex/` - unlike relay, whose feature code is master-owned under
  `storage/bot_specific/relay/<feature>/`.
- Codex is the reference for the **consolidated** storage seam (`bindings` + `collections` +
  `config_manager`); relay is still on the older `define_collections` / `manager` trio. Codex's
  shape is the target, so copy from here, not from there.
