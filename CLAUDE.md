# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Status

This project has no real users and no production data. As a result:

- **No migration scripts needed** — if the data structure changes, drop the collection and start fresh
- **No backward compatibility** — old document formats do not need to be supported
- **No migration shims** — do not add `from_dict()` legacy generation handling or field rename fallbacks for past schemas
- When a schema changes, update the code directly and assume clean data

If existing code contains any of the above (migration logic, legacy `from_dict()` generation handling, backward compat fallbacks), **remove it** rather than working around it.