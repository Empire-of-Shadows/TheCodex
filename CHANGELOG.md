# Changelog

## [Unreleased] - 2026-07-10

### Added
- Running `/suggest` on its own now opens an interactive suggestion form instead of asking you to fill in command options. The form has an **Edit Details** button (title, description, and optional extra details), a dropdown to pick the category, a button to turn anonymous posting on or off, and **Submit** / **Cancel** buttons. Your choices update in place as you go. You can still use `/suggest` the quick way by passing `suggestion_text` directly, which skips the form.

### Changed
- Removed the `template` option from `/suggest`. It overlapped with the category choices and made the command more confusing than helpful. Guided prompts still live inside the new form (and the "suggest a feature" button in the welcome flow is unchanged).
- Tidied up the admin panel by removing the leftover **View Status** entries under Embed Settings, WYR, Trackers, Announcements, and the Guide. Those entries only repeated settings you can already see, and they opened to a blank screen. The overview at the top of the panel still shows every setting when you press **Show Config Details**. The **View Status** entries that show real activity (Suggestions and Drops) are unchanged.

### Fixed
- The admin **Suggestions** panel now works again. Viewing the suggestion stats (View Status), changing a suggestion's status (Update Status), and exporting suggestions to CSV/JSON were all silently failing behind the scenes; they now run correctly.

## [Unreleased] - 2026-07-09

### Added
- Admins can once again change a suggestion's status (Under Review, Approved, Implemented, Rejected, or On Hold) from the admin panel, under **Suggestions → Update Status**. Updating a suggestion refreshes the posted suggestion message, renames its discussion thread to show the new status, and (for non-anonymous suggestions) sends the author a direct message about the change.
- The **Suggestions** section of the admin panel now has a working **View Status** summary (totals, a breakdown by status and category, and the top contributors) and an **Export** option to download all suggestions as a CSV or JSON file.

## [Unreleased] - 2026-07-06

### Changed
- Mentioning the bot now takes you straight into the guide instead of a topic-picker menu. The old "📖 Server Guide — Select a topic below" menu has been removed. The page at the top of your guide is now its **Home page**: mentioning the bot with "help" (or "guide", "faq", "support"), or with anything that doesn't match a specific topic, opens the Home page. Mentioning it with a keyword that matches a topic still opens that topic directly.
- Mentioning the bot on its own (with no words) shows a short "How to Use the Server Guide" walkthrough with tips on the different ways to ask for help, plus quick buttons to open the guide or search.
- The "Main Menu" button on guide pages is now labelled "Home" and takes you to the guide's Home page (the page at the top of your guide). The Home page itself no longer shows the Back or Home buttons, since it's already the top of the guide.
- The Home page now automatically shows a "Jump to a section" dropdown listing the guide's other top-level sections (the Home page itself is left out), so people can reach any section from the start without you having to add links by hand.

### Fixed
- Dropdown options you add to a guide page that link to another page now work when selected. Previously they did nothing and Discord showed "Interaction failed"; they now open the linked page as expected. (Link buttons were already working — this was only the dropdowns.)

## [Unreleased] - 2026-07-03

### Added
- You can now export a guide or welcome layout to a JSON file (an "Export JSON" button next to "Import JSON"), so you can back it up or share it with another server.

### Changed
- Importing a layout now checks that the file is a valid, reasonably-sized layout before loading it, instead of loading anything and only warning you when you try to save. Files that are too large or malformed are turned away with a clear message and your current work is left untouched.
- The import button now only accepts real `.json` layout files. If you pick something else (an image, a document, a program, a zipped file, or a file just renamed to `.json`), it's turned away with a clear message instead of being loaded.
- Imports are now checked for unsafe content and turned away if found: raw HTML or script snippets in your text or labels, hidden right-to-left/invisible characters that can be used to disguise text, and a couple of special property names that could be used to tamper with the page. Normal formatting, emoji, channel/role mentions, and non-English (for example Cyrillic or Chinese) text are all still fine.

### Fixed
- The admin "Edit Welcome" button now opens the welcome-message editor instead of taking you to the guide editor. The "Edit Guide" button still opens the guide editor as before.
- In the guide builder, the delete "×" button is no longer hidden behind the preview when a component is set to a dropdown (select) menu, so you can remove it again.
- Guide and welcome messages the bot posts can no longer ping @everyone, @here, or a role even if someone puts those into the text — they now show up as plain text. (Direct mentions of the person being welcomed still work, and the daily "Would You Rather" role ping is unaffected.)
