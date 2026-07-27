# Changelog

## [Unreleased] - 2026-07-26

### Added
- **Info boards.** You can now build a permanent information message and post it in a channel -
  the sort of thing that usually sits pinned at the top of a welcome or info channel. The
  difference is that its buttons and dropdown actually do something: tap **Server Rules** and the
  rules appear just for you, without filling the channel with replies. One tidy message can hold
  a whole handbook.
- Everything a board button reveals is yours to write. In the new **Board** tab of the builder you
  create named responses - Rules, Roles, FAQ, whatever your server needs - and point buttons or
  dropdown options at them. Responses can have their own buttons leading to other responses, so
  you can build a small branching handbook. Buttons can also send someone to a channel or hand
  out a self-assignable role that they can tap again to remove.
- Posting a board is `/board post #channel`. After that, edit it in the builder and run
  `/board refresh` (or **Post / Update Board** in `/admin`) - it **updates the message already in
  the channel** instead of posting a duplicate. `/board info` tells you where the board lives and
  whether its layout is valid. If someone deletes the message, a refresh puts a fresh one back.
- The **Preview** button in the Board tab lets you click through the board exactly as a member
  would: pressing a button opens its private reply below, marked the way Discord marks a message
  only you can see.
- You can now sign yourself up to be pinged whenever a new **Would You Rather** question is
  posted. Every question has a **🔔 Notify Me** button, and the new `/wyr notify` command shows
  whether you're signed up with a single button to change it.
- After you vote or check the results, the bot offers you the notification role - but only if you
  don't already have it. If you'd rather not be asked, **Not Interested** stops the offer for good;
  the button on the question posts and `/wyr notify` still work if you change your mind later.
- Turning the pings back off is always one click: the same message that confirms you're signed up
  carries a **🔕 Turn Off Pings** button, and `/wyr notify` offers it too. Nobody needs to ask a
  moderator to add or remove the role.

### Changed
- **The welcome message is now called the greeting.** With info boards arriving, "welcome" meant
  two different things - the message sent when somebody joins, and the static message sitting in
  the welcome channel. The join message is now the **greeting** everywhere: `/welcome test` and
  `/welcome info` are now `/greeting test` and `/greeting info`, the builder tab reads
  **Greeting**, and the `/admin` panel shows **Greeting Channel** and **Greeting Message Builder**.
  Nothing you have set up changes - your existing layout, channel and on/off switch all carry over
  as they were.
  - One thing to know: buttons on greeting messages already sitting in your channel history will
    stop responding after this update. New greetings work normally.
- Server admins have a new **Notification Offer** switch (in `/admin` under WYR Settings, and on
  the dashboard) to stop the bot offering the role to people as they play. The role stays
  available through the question button and `/wyr notify` either way. For any of this to appear,
  the server needs a **WYR Ping Role** set, positioned below the bot's own role so the bot can
  hand it out.

### Fixed
- The `/admin` panel's setup progress was counting things you cannot actually configure. Screens
  like **View Status**, **Export** and **Update Status** were being added to each category's
  "X of Y configured" total, so a category could never read as finished no matter how much you
  set up - **Suggestions** was stuck at "1 of 4" with a fully working setup, and **New Members**
  and **Updates & Drops** were each one short. Only real settings count now, and a category that
  holds nothing but action screens just shows its name instead of a meaningless total.
- A list you had not put anything in yet (such as an empty tracker list) was being counted as
  configured. An empty list now correctly reads as still needing setup.
- The **Docs** button in the guide and welcome builders only said "Documentation file not found".
  The help pages had gone missing, so there was nowhere to look up what a block does or why a
  design refused to save. All of it is back and rewritten for the builder as it works today:
  a walkthrough of the screen, a plain-language reference for every block and its limits, the
  full list of `{placeholders}` and where each one works, and six copy-and-paste example layouts
  per builder, plus a list of the errors that block saving and how to clear each one.

## [Unreleased] - 2026-07-23

### Changed
- The dashboard now keeps a readable activity log. Every settings change, sign-in and rejected
  request is recorded with who did it, which server it was for, whether it worked and how long
  it took - so an admin can look back and see what happened. Ordinary page loads stay out of the
  log unless you ask for them (set `DASHBOARD_LOG_READS=1`).
- The dashboard had been running with debug logging left on, which buried anything useful under
  a constant stream of internal chatter. It now logs at the normal level, to both the console and
  a rotating file under `logs/`. Set `LOG_LEVEL=DEBUG` if you ever need the extra detail back.

### Fixed
- In the `/admin` panel, changing a setting that opens a text box saved your value but then
  errored out instead of taking you back to the menu, and the panel stopped responding. It
  now returns you to the menu with the new value showing.
- The **Privacy Policy** link on the sign-in screen was showing in the browser's default
  blue, which is very hard to read on the dark background - and it turned an even darker
  purple once you had visited the page. It is now a light violet with an underline, so it
  reads clearly and obviously looks like a link. Any other plain link on the dashboard that
  had the same problem is fixed too.
- Links in the footer (including **Privacy Policy**) were the same grey as the text next to
  them, so they did not look clickable. They are now brighter and underline when you hover
  or tab to them.

## [Unreleased] - 2026-07-21

### Changed
- Exporting suggestions from the admin panel now uses the same exporter as the rest of the ecosystem. Exports contain the same information as before; CSV column headers now use the field names (for example `suggestion_id` instead of "ID"), and dates in the JSON export are in standard ISO format.

## [Unreleased] - 2026-07-20

### Fixed
- Uploading a custom **Welcome Message** or **Guide** JSON file in the admin panel works again. Every upload was failing behind the scenes, so custom layouts could never be saved. Uploads are now checked against the expected format before saving, and a bad or non-JSON file gives a clear explanation instead of a generic error.
- Changing a suggestion's status from the admin panel no longer throws an error when you type a status it doesn't recognise. It now replies with the list of valid statuses so you can try again.
- When you enter a value the admin panel rejects (for example a number outside the allowed range), it now shows a short "Invalid Input" note explaining the problem, instead of failing with a generic error and losing what you typed.

### Changed
- Adding or removing members from the screening whitelist is now limited to admins. Moderators can still view the whitelist (`/whitelist list` and `/whitelist check`) but can no longer change who's on it, matching the rule that moderator tools are view-only.
- The Would You Rather commands (`/wyr stats`, `/wyr leaderboard`, and the rest) no longer appear in direct messages, where they had no server to look things up in. They are server-only now, like the rest of the bot's commands.

## [Unreleased] - 2026-07-19

### Fixed
- The `/drop` command works again. It had stopped loading entirely after a recent admin-panel update, so browsing Prime Gaming drops (and the manager-only test and unsent-drops views) were unavailable. When one of these drop panels sits unused for five minutes it now shows a clear "session timed out, use `/drop` again" notice instead of leaving dead buttons.

## [Unreleased] - 2026-07-17

### Fixed
- Would You Rather now keeps adult questions out of channels that are not age-restricted. If a server's WYR channel is not marked **Age-Restricted** in Discord, the daily question is always a safe-for-work one, even if the category is set to NSFW or Mixed. Posting one by hand with `/wyr post category:nsfw` in a channel that is not age-restricted is turned down with a note explaining why, instead of posting.
- The **Mixed** WYR category works now. It was never posting anything at all, so servers using it saw no daily question. It now draws from both safe-for-work and adult questions in an age-restricted channel, and from safe-for-work questions only everywhere else.

## [Unreleased] - 2026-07-12

### Changed
- Adding TheCodex to a server from the dashboard now asks only for the permissions the bot actually uses (posting messages and embeds, managing its own discussion threads, managing the whitelist/tag/guide roles, and removing brand-new accounts) instead of requesting full Administrator access.
- If the bot is removed from a server and added back within a day, that server's settings and history are now kept instead of being wiped straight away. Previously, leaving a server - even briefly or by accident - erased all of its saved data immediately.
- Checking server boosters is now done with slash commands - `/boosters` (who's currently boosting) and `/boosthistory` (a member's boost status and recent boost activity) - instead of the old `.boosters` and `.boosthistory` text commands, matching the rest of the bot's commands.
- Cloning a bot embed is now done by right-clicking the message and choosing **Apps -> Clone Embed** (available to members who can Manage Messages). It asks where to post - this channel, or another one you pick from a menu - then re-posts the embed(s) there as a clean copy, with no "used a command" line above it, and leaves the original message in place. This replaces the old hidden `.embed clone` / `.embed preview` / `.embed batch` text commands.

### Fixed
- Tightened the safety check on where the dashboard sends you after you sign in, so a specially crafted login link can no longer bounce you to a look-alike outside site.
- When the guide is turned off for a server, mentioning the bot there no longer pops up a guide response. It now respects the guide's on/off setting.
- Searching suggestions with `/suggest-search` returns matching results again, and submitting a suggestion once more warns you when a very similar one already exists. Both had quietly stopped working and always came back empty.
- The 👍 / 👎 / ❤️ / 🤔 vote buttons on posted suggestions keep working after the bot restarts. Previously, any vote cast after a restart was recorded against the wrong place instead of the suggestion you clicked on.

## [Unreleased] - 2026-07-10

### Added
- Running `/suggest` on its own now opens an interactive suggestion form instead of asking you to fill in command options. The form has an **Edit Details** button (title, description, and optional extra details), a dropdown to pick the category, a button to turn anonymous posting on or off, and **Submit** / **Cancel** buttons. Your choices update in place as you go. You can still use `/suggest` the quick way by passing `suggestion_text` directly, which skips the form.
- The **View Status** screens for **Updates & Drops** and **New Members** now actually work instead of opening to a blank screen. For Drops it shows a live summary - the posting channel, daily post time, tracked channels, and per-category drop totals. For New Members it shows the screening settings plus whitelist counts (active, inactive, total, and how many currently have the role).

### Changed
- Removed the `template` option from `/suggest`. It overlapped with the category choices and made the command more confusing than helpful. Guided prompts still live inside the new form (and the "suggest a feature" button in the welcome flow is unchanged).
- Tidied up the admin panel by removing the leftover **View Status** entries under Embed Settings, WYR, Trackers, Announcements, and the Guide. Those entries only repeated settings you can already see, and they opened to a blank screen. The overview at the top of the panel still shows every setting when you press **Show Config Details**. The **View Status** entries that show real activity (Suggestions, Updates & Drops, and New Members) are kept and working.

### Fixed
- The admin **Suggestions** panel now works again. Viewing the suggestion stats (View Status), changing a suggestion's status (Update Status), and exporting suggestions to CSV/JSON were all silently failing behind the scenes; they now run correctly.

## [Unreleased] - 2026-07-09

### Added
- Admins can once again change a suggestion's status (Under Review, Approved, Implemented, Rejected, or On Hold) from the admin panel, under **Suggestions → Update Status**. Updating a suggestion refreshes the posted suggestion message, renames its discussion thread to show the new status, and (for non-anonymous suggestions) sends the author a direct message about the change.
- The **Suggestions** section of the admin panel now has a working **View Status** summary (totals, a breakdown by status and category, and the top contributors) and an **Export** option to download all suggestions as a CSV or JSON file.

## [Unreleased] - 2026-07-06

### Changed
- Mentioning the bot now takes you straight into the guide instead of a topic-picker menu. The old "📖 Server Guide - Select a topic below" menu has been removed. The page at the top of your guide is now its **Home page**: mentioning the bot with "help" (or "guide", "faq", "support"), or with anything that doesn't match a specific topic, opens the Home page. Mentioning it with a keyword that matches a topic still opens that topic directly.
- Mentioning the bot on its own (with no words) shows a short "How to Use the Server Guide" walkthrough with tips on the different ways to ask for help, plus quick buttons to open the guide or search.
- The "Main Menu" button on guide pages is now labelled "Home" and takes you to the guide's Home page (the page at the top of your guide). The Home page itself no longer shows the Back or Home buttons, since it's already the top of the guide.
- The Home page now automatically shows a "Jump to a section" dropdown listing the guide's other top-level sections (the Home page itself is left out), so people can reach any section from the start without you having to add links by hand.

### Fixed
- Dropdown options you add to a guide page that link to another page now work when selected. Previously they did nothing and Discord showed "Interaction failed"; they now open the linked page as expected. (Link buttons were already working - this was only the dropdowns.)

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
- Guide and welcome messages the bot posts can no longer ping @everyone, @here, or a role even if someone puts those into the text - they now show up as plain text. (Direct mentions of the person being welcomed still work, and the daily "Would You Rather" role ping is unaffected.)
