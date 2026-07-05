# Changelog

## [Unreleased] - 2026-07-03

### Added
- You can now export a guide or welcome layout to a JSON file (an "Export JSON" button next to "Import JSON"), so you can back it up or share it with another server.

### Changed
- Importing a layout now checks that the file is a valid, reasonably-sized layout before loading it, instead of loading anything and only warning you when you try to save. Files that are too large or malformed are turned away with a clear message and your current work is left untouched.

### Fixed
- The admin "Edit Welcome" button now opens the welcome-message editor instead of taking you to the guide editor. The "Edit Guide" button still opens the guide editor as before.
- In the guide builder, the delete "×" button is no longer hidden behind the preview when a component is set to a dropdown (select) menu, so you can remove it again.
- Guide and welcome messages the bot posts can no longer ping @everyone, @here, or a role even if someone puts those into the text — they now show up as plain text. (Direct mentions of the person being welcomed still work, and the daily "Would You Rather" role ping is unaffected.)
