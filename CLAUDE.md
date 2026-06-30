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

This project has no real users and no production data. As a result:

- **No migration scripts needed** — if the data structure changes, drop the collection and start fresh
- **No backward compatibility** — old document formats do not need to be supported
- **No migration shims** — do not add `from_dict()` legacy generation handling or field rename fallbacks for past schemas
- When a schema changes, update the code directly and assume clean data

If existing code contains any of the above (migration logic, legacy `from_dict()` generation handling, backward compat fallbacks), **remove it** rather than working around it.