---
name: bot-startup-logging-standardization
description: Ongoing effort to unify startup/logging across the EoS Discord bots, with locked decisions
metadata:
  type: project
---

Standardizing startup + logging across the Empire of Shadows bots so their boot
sequences and logs read identically. **TheCodex is the structural baseline.**

Canonical layout (every bot): main file stays at repo root (`codex.py`, `Host.py`); a
**`startup/` package** holds `bot.py`, `sync.py`, `phases.py`:
- `startup/bot.py` — bot instance, TOKEN, intents, `s = " " * 5` (standardized indent).
- `startup/sync.py` — cog loading (parallel + priority phase) + `attach_databases()`
  (per-bot body) + owner `.load_cogs` cmd + `log_all_commands()` (tree table: groups list
  their subcommands indented with `↳`, columns Command/Description/Type).
- `startup/phases.py` — `startup_phase`, `startup_metrics`, `log_startup_summary` (no command
  logging — that moved to sync.py).
The **logger stays put** (`utils/logger.py` / `utilities/logger_setup.py`) — NOT moved into
startup/ — but both bots share the same logger system.

Locked decisions:
- Folder is **`startup/`** for all bots (Codex's startup files moved OUT of `utils/`).
  (This supersedes an earlier "keep per-bot dir names / no rename" decision — the move is
  cheap: `bot.py` is imported by only ~4 files in Host / ~6 in Codex; sync/phases only by the
  main file.)
- Cog loader = TheHost's parallel + priority loader, per-bot `COG_DIRECTORIES` /
  `PRIORITY_COG_DIRECTORIES` (Codex priority = []).
- Command table = **tree under parent** (chosen format), lives in `startup/sync.py`.
- Logging = best practices, no reinvention. Do NOT change `get_logger` defaults (level/log_dir)
  — ~55 modules rely on them; changing alters verbosity / relocates log files.
- No bot runs databaseless — DB mandatory; raise/exit on failed connection.
- Standard extras for every bot: `DISCORD_TOKEN` validation + `docker/.env.local` override.
- Remove dead code when found.

DONE (2026-06-18): **TheHost + Codex** restructured into `startup/` per the above. TheHost
also: DB made mandatory in `Host.py` (`initialize_subsystems` moved into
`startup/sync.py` as `attach_databases`; on_ready phase renamed "Systems Initialization" →
"Database Attachment"). Codex dead code removed (`log_command_details`, `log_prefix_commands`,
`cache_guild_roles`). Both verified: py_compile + import smoke pass, no stale imports.
NOT yet runtime-tested (needs Mongo + token).

DONE (Ecom): `FunEngagement/EcomRebuild` restructured into `startup/` (utils/ removed). sync.py
got tree command table + owner `.load_cogs`; `initialize_subsystems(bot, db_manager)` → `attach_databases()`
(no args, imports db_manager internally); phases.py switched to canonical OrderedDict metrics
(removed dict-based metrics + manual ready_time/total/start_time writes in ecom.py); on_ready phase
"Systems Initialization" → "Database Attachment"; dead `log_command_details`/`log_prefix_commands`
removed; added `.env.local` override + DISCORD_TOKEN validation. Ecom's logger stays in `loggers/`
(its own richer system — NOT unified with Codex's). Verified compile + import smoke, no stale imports.

DONE (ImperialReminder): `Informatinal/ImperialReminder` restructured into `startup/` (utils/
kept — still holds logger.py, env.py, health_endpoint_template.py). sync.py: swapped sequential
loader for canonical parallel+priority, added tree command table, kept its attach_databases
(db/cache/audit/guild_config/gatekeeper/premium/timer) + .load_cogs; phases.py dropped
log_all_commands; bot.py s→5; Reminder.py imports→startup.*, added .env.local override +
DISCORD_TOKEN validation (kept its extra "Timer Reschedule" on_ready phase). Verified.

DONE (Stygian-Relay): `Informatinal/Stygian-Relay` restructured into `startup/` (root `bot.py`
→ startup/bot.py with `s` added; `core/sync.py` → startup/sync.py; `core/startup.py` →
startup/phases.py; `core/` removed; `logger/` system stays). sync.py: sequential single-dir
loader → canonical parallel+priority + tree command table + .load_cogs; removed dead
`log_command_details`/`log_synced_commands`. No `attach_databases` (Stygian wires guild settings
via `initialize_existing_guilds` in startup/bot.py, kept). phases.py dropped log_all_commands.
main.py + status/idle.py imports → startup.*; on_ready phase "Systems Initialization" →
"Database Attachment" (non-fatal, no early return since guild-init isn't critical); added
docker/.env + .env.local override (TOKEN validation already present). Verified.

DONE (TheDecree): `FunEngagement/TheDecree` restructured into `startup/` (utils/ kept — env.py,
logger.py, __init__.py). sync.py: sequential loader → canonical parallel+priority + tree command
table; kept its owner **slash** `load-cogs` command (Decree is fully slash-driven, no
message_content intent) and quote-specific attach_databases (quote_manager/audit/quote_time/idle).
phases.py dropped log_all_commands; bot.py s→5; quote.py imports→startup.*, added .env.local
override + DISCORD_TOKEN validation (kept its extra "Background Tasks" on_ready phase). Updated 6
`commands/admin/actions/*` importers. Verified. (One stale `from utils.bot` remains only in a
`commands/admin/PAGINATED_LIST_PORTING.md` doc — not code.)

**ALL SIX BOTS COMPLETE**: TheHost, Codex, Ecom, ImperialReminder, Stygian-Relay, TheDecree all
restructured to the `startup/` package standard. None runtime-tested yet (need Mongo + token).
Plan file: `~/.claude/plans/we-want-to-further-fuzzy-stroustrup.md`.
