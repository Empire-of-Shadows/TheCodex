# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

**TheCodex** (`codex`) is the Empire of Shadows **knowledge base + new-member screening** bot,
with several community features layered on top. It is part of the larger Empire of Shadows
ecosystem (see the monorepo root `../../CLAUDE.md` and the engine masters in `../../EmpireSystems/`).

Despite the name, **TheCodex does not use an LLM** - its knowledge base is RapidFuzz fuzzy
search over curated markdown, not the Claude API. Feature areas (mostly under `Features/`):

- **Guide / knowledge base** (`Features/Guide/`) - fuzzy-searchable FAQ / guide content.
- **New-member screening** (`Features/NewMembers/`) - account-age gate, whitelist, screening DMs.
- **Suggestions** (`Features/suggestion/` + `/suggest`) - community suggestions with voting.
- **Would You Rather** (`Features/daily/`) - daily WYR posts, stats, leaderboard.
- **Prime Gaming drops** (`commands/drops/`, `Features/updates-drops/`) - the `/drop` browser.
- Plus announcements, trackers, and embed / utility tools.

- **Entry point:** `Codex.py` - loads `docker/.env` (+ `.env.local` override) ->
  `setup_application_logging` (loguru) -> signal handlers -> `DatabaseManager` init -> health
  endpoint (**port 50010**) -> `bot.start` raced against a shutdown event -> idempotent `on_ready`
  (guarded by `_init_done`): Database Attachment (`attach_databases`) -> Cog Loading -> Command
  Sync -> Status Setup. On reconnect it only refreshes presence.
- **Bot construction** (`startup/bot.py`): `command_prefix=commands.when_mentioned` (slash-only,
  no text prefix) with a safe `allowed_mentions` default (everyone / roles off, users on).
  `load_cogs` survives only as a **mention-only owner command**, not a prefix command.
- **Run locally:** `python Codex.py`  ·  **Docker:** `docker/codex.sh` (joins `obsidian_grid`;
  `--local` builds from the working tree instead of cloning from GitHub).

## Engine distribution: vendored, not installed

Both shared engines are **vendored copies** living in this repo. Codex does NOT pip-install
`EmpireSystems`; there is no engine entry in `requirements.txt`.

| Master | Vendored into | Owner |
|---|---|---|
| `../../EmpireSystems/storage_engine/` | `storage/` (imported as `storage`) | master |
| `../../EmpireSystems/admin_engine/` | `admin/` (at the repo root) | master |
| `../../EmpireSystems/admin_engine/bot_specific/codex/` | `admin/bot_specific/codex/` | master, codex only |
| - | `storage/settings/`, `admin/settings/`, `admin/actions/` (its `__init__.py` + bot action modules) | **codex** (the seam) |

Files carrying a `# VENDORED ... DO NOT EDIT HERE` banner are generated. **Never edit them.**
Edit the master in `../../EmpireSystems/` and re-run the sync tool; drift is caught by `--check`.

Codex, like relay, is on the **root-`admin/` + `settings/`-seam layout** and the loguru `log/`
engine (it imports `from storage.log import ...`), so both engines sync with no `--scope` or
`LEGACY_LOGGING` restriction. The other four bots are still on the flat `commands/admin/` layout,
and `sync_admin_engine.py` refuses to vendor the engine across layouts.

### Syncing

```bash
# from the monorepo root
python EmpireSystems/tools/sync_admin_engine.py   --check --bot codex
python EmpireSystems/tools/sync_storage_engine.py --check --bot codex
```

## Layout

| Path | What it is |
|---|---|
| `Codex.py` | Main entrypoint (bot-named, PascalCase). |
| `startup/` | `bot.py` (instance / intents / token, `when_mentioned` + `allowed_mentions`), `sync.py` (auto-discovery cog loader + `attach_databases()`; `COG_DIRECTORIES = ["./commands", "./admin", "./Features"]`), `phases.py` (startup metrics / summary). Canonical ecosystem startup package. |
| `commands/` | Codex slash-command cogs: `drops/` (the `/drop` Prime Gaming browser) and `status/`. |
| `Features/` | Where most of codex's domain lives, as feature packages each owning its cogs + stores: `Guide/` (knowledge base), `NewMembers/` (screening + whitelist), `suggestion/`, `daily/` (WYR), `announcements/`, `trackers/`, `updates-drops/`, `ce_utilities/`, plus `error_handler.py`. Any `.py` defining `async def setup(bot)` auto-loads. |
| `admin/` | **Vendored `admin_engine`** (the shared `/admin` panel), at the repo root. Seam = `admin/settings/` (`bindings.py`, `panel_configs.py` = the MAIN_PANEL tree, `panel_branding.py`, `setup_gatekeeper.py`) **plus** `admin/actions/` (a MIXED dir: the vendored engine action subpackages `collections/ config/ data/ discord_objects/ features/ structure/`, and codex's bot-owned `__init__.py` + action modules `new_member_actions.py`, `wyr_actions.py`, `guide_actions.py`, `drops_actions.py`, `announcement_actions.py`, `tracker_actions.py`, `embed_config_actions.py`, `color_set_actions.py`). `admin/admin_cog.py` is the only `def setup(...)` under `admin/`. Tier resolution delegates to the engine resolver via `bindings.resolve_panel_role`. |
| `admin/bot_specific/codex/suggestions/` | The Suggestions admin feature - **master-owned**, authored in `../../EmpireSystems/admin_engine/bot_specific/codex/suggestions/` and vendored to codex only. |
| `storage/` | **Vendored `storage_engine`**. Seam = `storage/settings/` in the **consolidated** shape: `bindings.py`, `collections.py` (collection registry + the concrete `db_manager`), and `config_manager.py` (the typed guild-config layer). This is the ecosystem's blessed seam shape; relay is still on the older `define_collections` / `manager` trio. |
| `dashboard/` | FastAPI backend (`routers/`, `services/`, `auth/`) + React / Vite SPA (`frontend/`). Standalone process; shares the cross-bot SSO session store. Health / dashboard on `:54010`. |
| `migrations/` | Idempotent, dry-run-first migration scripts over **real production data** (see Development Status). |
| `defaults/`, `markdownfiles/`, `memory/` | Codex content: default panel payloads, knowledge-base markdown, guide JSON. |
| `docker/` | Dockerfile(s), docker-compose, `.env(.local)`, `codex.sh`. |

## What is and isn't yours

Only the **seam** is codex's to hand-edit inside the engine dirs: `storage/settings/`,
`admin/settings/`, and `admin/actions/` (its `__init__.py` + bot-owned `*_actions.py` modules).
Everything else under `storage/` and `admin/` is generated - the engine (from `ENGINE_FILES`) and
the master-owned `admin/bot_specific/codex/` subtree. Codex's own feature / domain code lives
OUTSIDE the engine dirs, under `Features/` and `commands/`.

To change the Suggestions admin feature, edit the **master** at
`../../EmpireSystems/admin_engine/bot_specific/codex/suggestions/` and re-vendor - editing the copy
here is what `--check` reports as drift, and a file here the master lacks is `[ORPHAN]`.

**Adopt engine services, do not re-roll them.** Codex uses the engine `AuditLog` and `SetupGate`
(its old hand-rolled `AuditLogger` / `SetupGatekeeper` are gone); `setup_gatekeeper.py` in the admin
seam is a thin wrapper that delegates to the engine `SetupGate`. When adding a structured setting to
`config_manager`, remember its `from_dict` whitelist is fixed-key - a new subkey must be whitelisted
or it silently drops on reload. All config writes (bot and dashboard) are surgical dotted `$set` of
changed keys only; never write the whole document.

## Where codex differs from relay (the two reference bots)

Both are on the same layout, but a few deliberate choices differ - keep them in mind:

- **Storage seam shape:** codex is **consolidated** (`bindings` + `collections` + `config_manager`);
  relay is on the trio (`bindings` + `define_collections` + `manager`). Codex's shape is the target.
- **Panel branding:** codex keeps a separate `admin/settings/panel_branding.py`; relay inlines the
  same strings in `bindings.py`. Either is valid - the engine reads branding only through the
  bindings seam, never by importing `panel_branding.py`.
- **IDs:** codex stores **integer** guild / user IDs in most collections (WYR is the string-ID
  exception). The ecosystem standard is string IDs; the normalization is scheduled but not yet run
  - see `migrations/PENDING.md`. Do not assume string IDs when writing codex queries today.
- **Domain code home:** codex's per-feature logic lives in `Features/` and `commands/` (there is no
  `storage/bot_specific/codex/`), unlike relay's master-owned `storage/bot_specific/relay/<feature>/`.

## Changelog Requirements

**IMPORTANT**: When making any user-facing changes, you MUST update `CHANGELOG.md` using plain language that community members can understand.

### What to Document
- New guides, FAQ answers, or shortcuts
- Changes to how search or navigation works
- Bug fixes that affect people asking the bot questions
- Changes to commands or settings

### How to Write Changelog Entries
Write entries as if explaining to a server member, not a programmer:
- **DO**: "The guide now understands more ways of asking the same question"
- **DON'T**: "Lowered the RapidFuzz match threshold and added query normalization"

- **DO**: "Added a shortcut so typing `rules` jumps straight to the server rules"
- **DON'T**: "Registered a new entry in the shortcut map"

- **DO**: "Fixed broken back-navigation when browsing nested guide sections"
- **DON'T**: "Fixed breadcrumb stack pop on nested section traversal"

### Changelog Format
```markdown
## [Unreleased] - [Date]

### Added
- Brief, plain-language description of new feature

### Changed
- What changed and how it affects users

### Fixed
- What was broken and that it's now working
```

## Development Status

This project has real users and production data. Schema and storage changes MUST preserve that data:

- **Migrations, not fresh starts**: when the data structure changes, ship an idempotent migration under `migrations/scripts/` that transforms existing documents. Never "drop the collection and start fresh". Each script is standalone and dry-run by default (`python -m migrations.scripts.<name>`), applying writes only with `--apply`, and loads Mongo creds from the bot's local env (`docker/.env` then `.env.local`). See `_common.py` for the shared harness.
- **Remove old fields via migration**: once the code stops reading a field, a migration should `$unset` it from stored documents so no orphaned data lingers.
- **Migrate the data, keep the code clean**: prefer bringing documents to the current schema over carrying long-term `from_dict()` legacy-generation handling or field-rename fallbacks in the live code (a short read-time fallback is acceptable only as a bridge while a migration rolls out). The pre-collapse conversion logic is preserved frozen in `migrations/scripts/_guildconfig_v2.py` for reference.
- **Runbook**: run the dry-run first, confirm the reported changes, then re-run with `--apply`. Migrations are idempotent, so re-running after apply is a no-op.

## Conventions

- Slash commands + UI components (Components v2) only; no prefix commands. `when_mentioned`
  construction with a safe `allowed_mentions` default.
- Async / await throughout; structured logging via the vendored loguru `storage.log`
  (`setup_application_logging`); graceful shutdown via signal handlers.
- MongoDB via the vendored `storage_engine` `db_manager`; typed guild config through
  `storage/settings/config_manager.py` with surgical dotted `$set` writes only.
- Health endpoint on `:50010`; dashboard on `:54010`. All services share the external
  `obsidian_grid` Docker network.
- Hard rules (root `CLAUDE.md`): no gambling; hyphen-minus only (no em / en dashes); CHANGELOG.md in
  community language; migrations (not fresh starts) for production data; no compat shims without
  sanction.
