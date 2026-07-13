# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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