# Changelog

## [Unreleased] - 2026-08-13 (the settings page became a living web)

### Changed
- **Picking a server to manage is now a web you can play with.** The settings page fills the
  whole screen with your servers strung together on silk strands, drifting slowly and never
  quite settling. You can grab any server, or the sigil at the centre, drag it around and throw
  it - it carries on flying and bounces off the edges, and the rest of the web sways after it.
  Bigger servers feel heavier when you throw them.
- **Servers are sized by how many members they have,** so your busiest server is the biggest orb
  in the web. A server Codex has not counted yet just gets the standard size.
- **A server tells you where it stands at a glance.** Ready servers glow violet, servers that
  still need setting up have an amber pulse, and a server Codex has not been added to sits dim
  and faded until you invite it.
- **Choosing a server grows its menu out of the web itself,** on a glowing strand running back
  to the server you picked, with Edit Guide, Edit Greeting, Settings and Audit Log inside it
  (or the invite link, if Codex is not in that server yet). Close it with the x, by picking the
  same server again, or by clicking anywhere in the empty dark.
- **On a phone, the menu rises from the bottom of the screen** instead of floating over the web,
  and the web drifts upward to stay visible above it - the strand still runs from your server
  down into the menu.
- **Keyboard still works throughout** - tab to a server, press Enter or Space to open and close
  its menu. If you have asked your device to reduce motion, the web is drawn settled and still,
  with no drifting, no flight and no pulses, and everything remains selectable.

## [Unreleased] - 2026-08-12 (your stats are back, and the embed builder grew up)

### Fixed
- **Voting on the fourth or fifth answer of a poll works now.** It used to say your vote had
  failed even though it had been counted, and clicking again gave the same error every time.
- **Everyone can open the dashboard again, not just admins.** If you share a server with Codex,
  it now shows up when you log in, with your own stats - the redesign had accidentally locked
  members out entirely.

### Added
- **Your personal stats are on the dashboard for real this time** - votes cast, day streak, your
  suggestions with their outcomes, and what happened to questions you sent in. Admins see them
  too, first on the page with the server overview right below, so running the server does not
  cost you your own page.
- **Your votes are broken down by question type** - Would You Rather and answer-style polls each
  get their own count. Open-ended discussion questions do not have vote buttons, so they read
  "not counted" instead of pretending to be zero.
- **A "What you can use" section on the dashboard** shows what your roles unlock here: which
  embed features you have, your colour palettes with the actual colours shown, your description
  length limit, whether you can review questions or manage drops, the roles you can give
  yourself, and your screening status.
- **Building an embed now happens in two steps**: you fill in the text, then you get a private
  preview of the real embed - pick your colour from dropdowns, switch the timestamp on or off,
  and press Post when it looks right (or Cancel and nothing gets posted).
- **Footers work now.** If your roles allow it, there is a Footer box in the embed builder.
- **Embeds can show the time they were created**, next to the footer, if your roles allow it.
- **New server setting: "Free Color Access".** Admins can let everyone pick any colour they
  like. It is off to begin with, and the panel asks for confirmation before turning it on.

### Changed
- **Embed features are handed out per feature.** Anything an admin has not restricted is open to
  everyone; anything they have restricted belongs to those roles only. `/embed features` now
  tells you which is which instead of listing switches that did nothing.
- **Embed colours follow the palettes your roles give you.** If none of your roles has a
  palette, your embeds use the server's default colour, and `/embed colors` explains that
  instead of showing an empty list.
- **"Author Field" is gone from the embed feature list** - it never did anything.
- **Resetting a member's voting record in the admin panel now clears everything it should**:
  their leaderboard totals, the individual votes behind them, and their notification prompt
  settings. Questions they suggested are kept, since those belong to the server.

## [Unreleased] - 2026-08-12 (the dashboard fits a phone again)

### Fixed
- **The dashboard is readable on a phone.** Every panel was being squeezed into half the width of
  the screen, so headings wrapped mid-word and suggestion titles were cut off after a few letters
  ("Add a cha..."). On a narrow screen each panel now takes the full width and reads normally.

## [Unreleased] - 2026-08-11 (the dashboard tells you what your server is doing)

### Added
- **Your server's dashboard now opens on a real overview instead of a row of links.** The first
  thing on the page is a line for every part of Codex - the daily question, suggestions, new
  members, the guide, the info board, drops, trackers and announcement threads - each saying
  whether it is on, off, or switched on but still missing something it needs. That last one
  matters most: a feature that looks enabled while quietly doing nothing now says so, and takes
  you straight to the setting that fixes it.
- **The daily question shows real history.** A day-by-day chart of the last 30 days, including
  the days nobody voted so a quiet stretch actually looks like one. Alongside it: today's
  question with its votes and how many people voted, when the next one goes out, and how healthy
  your question bank is - including how many questions can never be posted because they are in a
  format your server has switched off.
- **A "waiting on you" list.** Suggestions still needing a decision and member questions awaiting
  review, in one place with how long they have been sitting. It links into Discord rather than
  answering them for you, so there is still only one place a decision gets made.
- **Your server's own content is on the front page** - how many guide pages and board responses
  you have, when each was last edited and by whom, and a way straight into the editor.
- **Your own activity page now shows a real voting streak** as a run of consecutive days, plus a
  chart of your last 30 days.
- **You can finally see what happened to questions you sent in.** How many were used, how many
  are still waiting on a moderator, how many were turned down, and for the most recent one that
  was used, when it went up and how many people voted on it.
- **Your suggestions are listed with their outcome and vote count**, instead of just a total.
- **Boosters can see how long they have been boosting.**
- **You can search your settings.** Type in the box above the settings list and it narrows to the
  sections holding a matching setting, by name or by description.

### Changed
- **The dashboard uses the space on a wide screen.** Everything used to stretch to whatever width
  your monitor was, so a card holding two numbers could be over a thousand pixels wide and mostly
  empty. Sections are now sized to what they actually contain, and things that are only a single
  number - members, boosters, people wearing the server tag - sit together on one line instead of
  each taking a whole panel.
- **Server settings is easier to get around.** The row of nine tabs is gone, replaced by a list
  down the side grouped by what it affects, where each entry shows at a glance whether that
  feature is on, off, or still missing something. The settings themselves sit in a readable
  column, and a panel on the right shows what the feature you are looking at is currently doing.
- **Nothing moved out of reach.** Every setting is still there. The admin channel that used to sit
  under "General" now lives with Suggestions, which is what it is actually used for. Saving works
  exactly as before: nothing saves itself, each part has its own Save button, and you are warned
  before leaving with unsaved edits.
- **Links into settings land where they should.** The section you are on is part of the page
  address now, so a link from the overview opens straight to it and a reload keeps you there.
- **Picking a server is a menu rather than a row of buttons** that ran off the edge of the screen
  once you were in more than a handful of servers.

### Fixed
- **Admins who get access through a Panel Access role can use the settings form again.** The
  channel and role dropdowns came up empty for them with no error to explain why, because those
  two lists only accepted Manage Server holders while the page around them accepted the role.
  Both now accept exactly the same people the settings page does.
- **The channel and role pickers are honest when they cannot load.** They now say so, and keep
  whatever you already had saved, instead of showing an empty list that reads as "this server has
  no channels".
- **The activity chart on your dashboard shows your real voting history.** It was previously a
  fixed decorative shape that never changed, no matter how much or how little you had voted.
- **Removed a vote breakdown that never meant anything.** It added up how often you picked "the
  first option" across every question you had ever answered, but which option comes first is
  arbitrary from one question to the next, so the bar was showing noise.

## [Unreleased] - 2026-08-11 (buttons built in the dashboard save again)

### Added
- **An "Edit Board" button on the dashboard.** Your server's page already had shortcuts straight
  into the guide and the welcome message; the info board now has one too, so you no longer have
  to open the guide editor first and switch over to the board by hand.

### Fixed
- **The builder no longer refuses to save a button that jumps to another page or hands out a
  role.** Once you picked what a button should do, the builder complained that the button "must
  not have a url" - even though you had never given it one - and the Save button stayed greyed
  out. Pasting the very same layout in as JSON worked, which made the whole thing look
  arbitrary. Choosing a button's action now properly clears the leftover link address, so what
  you see in the builder is exactly what gets saved.
- **Link buttons save properly too.** The same fault hit them from the other side: typing a web
  address into a link button made the builder insist the button "must not have an action", and
  again refuse to save. Both info boards and the welcome message were affected.
- **You can read the "Unsaved changes" warning again.** When you left the builder with work you
  had not saved, the pop-up asking whether to stay or leave showed its two buttons as pale
  boxes with near-invisible white labels, so you had to guess which one was Leave and which was
  Stay. They now use the same colours as every other button in the dashboard.

## [Unreleased] - 2026-08-10 (two pairs of commands became one each)

### Changed
- **Browsing suggestions is now one command, `/suggestions`.** It replaces `/suggest-search`
  and `/suggest-mine`. It opens a private list only you can see, and you can change the
  category and status filters right there instead of running the command again. **Mine only**
  narrows it to your own suggestions. Every entry shows its status, category, short ID and
  vote count. Submitting a suggestion has not changed - `/suggest` works exactly as before.
- Anything you sent in anonymously is not tied to your account, so it will not appear under
  **Mine only**. That is what anonymous means, and the list says so rather than leaving you
  wondering where it went.
- **The member whitelist is now one command, `/whitelist <user>`.** It replaces
  `/whitelist add` and `/whitelist remove`. Give it a user ID or an exact username and it
  tells you where that person stands - whether they are on the list, who put them there and
  why, or that they were taken off before - and offers only the button that fits: Add, Remove
  or Reactivate. It also shows how old their account is against what this server asks for and
  whether they would be turned away without a whitelist entry, which you previously had to
  work out yourself.
- Removing someone from the whitelist now asks you to confirm first, and the screen updates
  itself afterwards instead of leaving you looking at information that is already out of date.

### Fixed
- **You can now reach every suggestion.** The old search showed the first five matches and
  there was no way to see the sixth, and the count underneath was wrong - it would say
  something like "showing 5 of 10" no matter how many suggestions actually matched. It now
  reports the true number of matches and lets you page through all of them.
- **The whitelist no longer claims to have removed a role when it did not.** If the bot cannot
  take the whitelist role off someone - usually because the role sits above the bot's own - it
  now says so and tells you to remove it by hand, instead of reporting a clean removal.
- Removing someone from the whitelist is recorded the same way whether you did it from the
  command or from the panel, and the entry in your server's audit log now names the command
  you actually used.

## [Unreleased] - 2026-08-10 (your own questions come first)

### Changed
- **Your server's own questions now get posted before the shared ones.** If you are drawing
  from both, the daily question is picked from the questions you added yourself for as long
  as there are any your server has not seen yet. Only once you have worked through your own
  does it start using the shared bank, and only once everything has been posted at least
  once does it begin repeating - the least-seen question first, so the rotation never
  stalls. Before this, your questions simply queued up alongside the shared ones and a
  server that wrote its own could go a long time without seeing one.
- A question of your own that has already run several times does not jump ahead of a shared
  question your server has never seen. "Yours first" means the ones you have not used yet,
  otherwise the shared bank would never be reached at all.
- Nothing changes for a server that has not added any questions of its own.

## [Unreleased] - 2026-08-10 (command list cleanup)

### Changed
- **The slash command list is a lot shorter, and members only see commands they can
  actually use.** Several staff commands were showing up for everyone and simply refusing
  to run - Discord had no way to know they were restricted. Those are now hidden from
  members who cannot use them, and the ones that were really admin screens have moved into
  `/admin panel` where the rest of the settings already live.
- **The info board commands are gone.** `/board post`, `/board refresh` and `/board info`
  all now live in the panel under **Info Board**. **Post / Update Board** puts the board up
  in a channel you pick, moves it somewhere else, or refreshes the copy that is already
  posted; **Board Status** shows where it lives and whether the layout is valid. Posted
  boards keep working exactly as before - nothing needs re-posting.
- **Reviewing question suggestions and clearing a member's voting record moved to the
  panel**, under **WYR Settings -> Question Bank**. `/wyr queue` and `/wyr reset_stats` are
  gone; **Review Suggestions** walks you through what is waiting one at a time, and
  **Reset Member Stats** has a member picker and a confirmation step.
- **Whitelist and greeting commands are now hidden from ordinary members.** If you give
  Panel Access to a role that does not have Manage Server, you can still hand that role the
  commands under **Server Settings -> Integrations**.
- **The whitelist and greeting screens moved into the panel.** `/whitelist list` and
  `/whitelist check` are gone - **New Members -> Whitelisted Members** shows everyone on the
  list a page at a time instead of stopping at 25, with who added them, when and why, and a
  Remove button that also takes the whitelist role back off them. Since the list shows
  everybody, there is nothing left to look one person up for. Acting on one person is
  still a command.
- **Testing your greeting now tells you where it is going.** `/greeting test` has become
  **New Members -> Send a Test Greeting**. It names the channel the test will be posted in
  before you send it, lets you pick who gets greeted, and refuses with a clear reason when
  the greeting could not arrive - no greeting channel, a channel that has been deleted, no
  greeting built yet, a layout with a mistake in it, or the bot not being allowed to post
  there. `/greeting info` is gone; **New Members -> View Status** already showed everything
  it did.
- **The boost commands are gone, and boost information moved into the panel.** `/boosters`
  and `/boosthistory` have been replaced by **Trackers -> View Boosters**, which shows the
  server's boost count and level, everyone boosting right now with how long they have been
  at it, and the recent boost starts and stops in one screen instead of two commands. Who
  is boosting is now something staff look up rather than anything a member can pull into
  chat. Boost tracking itself is unchanged - starts and stops are still posted to your
  boost log channel as they happen.
- The `/help` menu's "Boosts & Drops" section is now just **Drops**, since `/drop` is the
  only command left in it. It still explains where boost information lives.

### Fixed
- **Boost history could come back blank after a restart.** When the bot came back online it
  compares who is boosting against what it recorded, and working out how long a member had
  boosted before they stopped could fail outright - so anyone who stopped boosting while the
  bot was offline was never written into the history. Those catch-ups now go through
  correctly.
- **Owner-only tools no longer appear in the command list of every server.** They now
  register to a single private server. If that server is not configured they simply do not
  load, instead of quietly falling back to being visible everywhere.
- **A denied whitelist command used to point you at a command that does not exist.** It said
  to run `/config view` to see who has access. It now names the Panel Access role and where
  it is granted, the same way every other permission message does.

## [Unreleased] - 2026-08-10

### Added
- **You can now fill the daily question bank with your own questions.** Until now every daily
  question came from one shared pool and there was no way to add to it. Under **WYR Settings ->
  Question Bank** in the admin panel you can now write questions one at a time, or upload a whole
  file of them at once with **Import Questions** (there is a Download Template button so you can
  see the shape before you start). Questions you add are private to your server - no other server
  will ever post them - and a question you already have is skipped rather than added twice.
- **You can choose where your daily questions come from.** Keep drawing from the shared pool plus
  your own questions, use only your own, or use only the shared pool. If you pick "only my own"
  before adding any questions, nothing will post until you add some.
- **Daily questions no longer have to be a choice between two things.** Alongside Would You
  Rather, a server can post a general question with up to five answers, or an open-ended prompt
  with no answers at all where the thread is the whole point. Pick which kinds your server posts
  under **Question Types**; servers keep posting Would You Rather only until you change it.
- **Browse and delete your own questions** from the panel, a page at a time, with a confirmation
  step before anything is removed.
- **Members can suggest questions, and a moderator approves them.** Turn on **Member Suggestions**,
  pick a channel for the review posts (or a reviewer role), and members can send in their own
  questions with `/wyr submit`. Each one arrives with Approve and Decline buttons; approving it
  puts it straight into your server's rotation, and the member gets a DM either way. You can cap
  how many suggestions one member can have waiting, and `/wyr queue` lists what is outstanding.
  If nobody is set up to review them, a member is told so up front rather than sending a
  suggestion into a queue nobody will read.
- **The settings pages now warn you when a question will not be posted.** Adding, importing or
  approving a question of a type your server does not currently post says so, and offers a single
  button to turn that type on - so a question can never quietly sit in the bank unused.
- **The web dashboard covers all of it too**, including separate thread wording for each question
  type, and the vote breakdown now counts every answer on questions with four or five options.

### Fixed
- **A question posted by hand now counts toward the rotation.** Posting one with `/wyr post` used
  to leave it looking unused, so the same question could come back again the next morning.

## [Unreleased] - 2026-08-07

### Added
- **The dashboard now links to the project's new About page.** The login page and the footer
  both point to a new page on the main site (eosofficial.club/about) explaining the whole
  Empire of Shadows project - what each bot does, why it is built as six separate bots instead
  of one big one, and how to report problems.

## [Unreleased] - 2026-08-06

### Changed
- **The separate moderator access level is gone.** The admin panel and the web dashboard now
  need **Manage Server** or a **Panel Access** role - there is no longer a lesser "mod" tier that
  could open them with a limited view. Anyone who was reaching the panel or the dashboard through
  a Mod Access role will find they no longer can; give them a Panel Access role if you want them
  to keep getting in, and remember that grants full access. The same applies to the staff-only
  commands: the info board, the greeting commands, and the whitelist (including `/whitelist list`
  and `/whitelist check`, which mods could previously view) are all admin-only now.
- **The Mod Access Roles picker has been removed** from both the admin panel and the dashboard,
  and any roles you had listed there no longer grant anything.
- **"Role Configuration" is now just "Panel Access Roles".** With only one setting left inside it,
  the extra menu step was pointless - picking it from the panel's main list opens the role picker
  straight away instead of a menu holding a single entry.

## [Unreleased] - 2026-08-05

### Added
- **Create roles and channels straight from the picker.** Every role and channel picker in the
  admin panel now carries a Create button: type a name and the new role or channel is created and
  selected in one step, without leaving the panel. The button first checks that the bot itself is
  allowed to create it and tells you which permission is missing instead of failing afterwards.
  Text channel names follow Discord's rules (lowercase letters, digits and dashes), and a rejected
  name comes back with a Try Again button that keeps what you typed.
- **Pick a category when creating a channel.** The Create Channel button in the admin panel now
  lets you choose which category the new channel goes under - or leave the picker empty to create
  it at the top of the channel list. If something goes wrong, Try Again keeps both the name you
  typed and the category you picked.

### Changed
- **The panel now refuses roles that would not actually work.** The pickers that decide who can
  open the admin panel no longer accept @everyone or roles managed by an integration (bot roles,
  booster roles) - membership of those is outside the server's control, so allowing them would
  open the panel wider than intended. Regular admin roles still work, including ones that sit
  above the bot. Every refusal explains itself.

## [Unreleased] - 2026-08-02

### Added
- **There is now a `/help` menu.** Run `/help` and you get a browsable panel covering
  everything the bot can do, one category at a time: the server guide and info board,
  suggestions, Would You Rather, boosts and Prime Gaming drops, and embed building. Each
  page lists the commands it covers and what they take. Pick a category from the dropdown
  to switch pages, and there is a button straight through to the web dashboard. Only you
  can see it. If you can manage the server you also get an Admin page covering the admin
  panel, the board, greeting, whitelist and Would You Rather staff commands.

## [Unreleased] - 2026-08-01

### Changed
- **The bot now asks Discord for far less than it used to.** TheCodex was subscribed to a broad
  default set of server events, most of which it never did anything with - reactions, emoji and
  sticker changes, voice activity, typing, invites, webhooks, integrations, bans, scheduled events
  and automod. It now asks only for the four it actually uses. Nothing you can see changes; the
  bot simply stops being told about things it was ignoring anyway.

### Fixed
- **The privacy policy was wrong about how your suggestions reach us.** It said the bot reads your
  messages and stores the text when it is part of a submission. That is not what happens.
  Suggestions are typed into a pop-up form, and that form's contents are what get stored - the bot
  is not reading your messages to find them. Would-You-Rather was described the same wrong way; all
  that is stored there is which of the two options you picked, and the questions come from a
  question bank we write rather than from members.
- **It also never explained what the bot does read.** TheCodex can see message text, and the policy
  now says exactly where that is used and that none of it is kept: the words you type after
  mentioning the bot become a search of the guide, an announcement's text is used to name the
  discussion thread opened underneath it, and posts in channels set up for drop tracking are only
  counted. None of that text is written down anywhere.

### Changed
- **The policy you agree to when you sign in now covers every Empire of Shadows service.** One
  login signs you in to all of the bot dashboards, but the login screen only ever pointed at
  TheCodex's own privacy policy, which does not describe what the other bots do with your data.
  Signing in now points you to a single combined Empire of Shadows privacy policy covering every
  bot, dashboard and tool. TheCodex's own privacy page has not gone anywhere - it is linked from
  the same line and from the footer, and still holds the detail specific to this bot.

## [Unreleased] - 2026-07-29

### Fixed
- **You can pick your actual timezone again for scheduled posts.** The Timezone setting for both
  Would You Rather and Prime Drops only offered nine choices, so if your server was not in one of
  those nine the closest you could get was "near enough". It is back to the two-step picker: choose
  a region first (Americas, Europe, Asia, Africa, Australia, Pacific and so on), then page through
  the cities in it and pick yours - for example Americas, then Chicago. Each city shows its current
  UTC offset next to it so you can confirm you have the right one. Posts land at the hour you set
  in your own local time, daylight saving included.

- **The builder preview now shows spacing the way Discord actually will.** If you left an
  empty line between two paragraphs, the preview closed the gap up and showed them stacked
  together - then the real message in Discord had the empty line after all. Text that looked
  right while you were writing it came out looking stretched. The preview now leaves the same
  gap Discord does, so what you see while building is what members see.

- **Color Tiers in the admin panel now actually opens.** Picking **Embed Settings -> Color Tiers**
  used to show a short description and a Back button and nothing else, so there was no way to set
  up member colors from Discord at all. It now opens the full Color Sets manager.
- The first time you open it, it asks you to pick a **server default color** - one color everybody
  on the server can always use. Once that is saved, the server is stocked with eight ready-made
  palettes (Common through Legendary, plus Celestial, Nature and Prism) so there is something to
  work with straight away instead of an empty list.
- From there you can create your own palettes, add and remove colors by name, and hand a palette
  out either to a **tier** (everyone at that rank gets it) or directly to a **role** (for staff and
  other special cases). You can also change the server default color at any time, and delete a
  whole palette behind a confirmation step so it cannot happen by accident.
- Small guards so the setup cannot end up in a broken state: a palette always keeps at least one
  color, a palette can only belong to one tier at a time, and colors you have already added are
  skipped rather than duplicated. If a color code cannot be read, the bot now tells you which
  lines it could not understand instead of silently dropping them.

- **The whole Trackers section of the admin panel now works.** Both **Tag Tracker** and
  **Boost Tracker** used to open to a description and a Back button with no controls, so neither
  could be set up from Discord at all.
- **Tag Tracker** now lets you switch it on or off, pick the role to hand out, and set the server
  tag to watch for. There is also a **Detect Tag** button that reads your server's tag straight
  from Discord so you do not have to type it in and risk a typo - it tells you what it found, or
  says plainly if your server has no tag set.
- **Boost Tracker** now lets you switch it on or off and choose the channel where boosts get
  logged.
- Neither tracker will let you switch it on before it can actually work. Tag Tracker asks for both
  a role and a tag first, and Boost Tracker asks for a log channel, instead of turning on and
  then quietly doing nothing.
- The panel also checks the bot can do the job before saving. If the role you picked sits above
  the bot in the role list, or the bot cannot post in the channel you picked, it now says so and
  explains how to fix it rather than accepting the setting and failing later.

- **Updates & Drops can be set up from the admin panel now too.** **Drops Channel**,
  **Tracked Channels** and **Manager Role** were the last three entries that opened to nothing.
  With these done, every entry in the admin panel leads somewhere real.
- **Drops Channel** lets you pick where the daily Prime Gaming post goes, and switch the whole
  feature on or off. The on/off button only appears once a channel is chosen, so you cannot
  switch it on and then wonder why nothing is posting.
- **Tracked Channels** lets you set the channel watched for each of the Updates, Free and Prime
  categories, and there is now a **Clear** button for each one so a channel you tracked by
  mistake can be removed rather than only re-pointed.
- **Manager Role** lets you name one role that can manage drops with `/drop`, alongside admins.
  It can be cleared again to go back to admins only.
- As with the trackers, the panel checks the bot can actually see and post in a channel before
  accepting it, and explains what to fix if not.

- **Members given embed access by tier can now actually use `/embed create`.** If you granted
  a role access through **Embed Settings -> Role Tier Mapping**, that on its own was never
  enough - the command still turned people away unless they also held an admin or mod role.
  The permission check was looking at an old, empty setting instead of the tier mapping the
  panel writes. Tier-based access now works the way the panel has always said it does.

- **Every feature section can now show you its current setup at a glance.** **WYR**,
  **Announcements** and **Trackers** were missing the **View Status** entry that New Members,
  Drops, Suggestions and Info Board already had. All of them have one now, and moderators can
  read it without being able to change anything. The Trackers one also shows how many people
  are currently boosting and how many boost events have been recorded.

- **The admin panel counts the newly-added settings again.** Sections show a "3 of 5 configured"
  style progress note, and the settings added above were being left out of it: **Trackers** had
  no progress note at all, while **Updates & Drops** and **Embed Settings** undercounted. Those
  entries also showed a blank space where their current setting should be. All of them now show
  their progress and a short summary of what is set, for example "On, tag EoS, role set" for the
  Tag Tracker or "2 of 3 tracked (Free, Prime)" for the drops channels.

### Fixed (small things)
- A warning shown when a tier has no roles assigned used a dash style the rest of the bot does
  not use, and said "won't" where the surrounding text spells it out. Reworded for consistency.

## [Unreleased] - 2026-07-27

### Changed
- **Commands now tell you how to switch a feature on instead of looking broken.** Before a server
  is set up, things like `/wyr notify`, `/suggest`, `/drop`, `/embed create`, `/board info` and
  mentioning the bot for the guide all came back with a dead end - "not available", "no colors",
  or just an empty list that looked like nothing had happened. Each of them now says plainly that
  the feature has not been set up yet and names the exact place to do it, for example
  `/admin panel` -> **Suggestions -> Suggestion Channel**.
- Those messages also say **who** can do it. On a brand new server the only people who can open the
  admin panel are the server owner and anyone with Manage Server, so the notice names the owner
  rather than telling everyone else to run a command they cannot use. The owner is pointed at
  **Role Configuration -> Panel Access Roles** so they can hand panel access to their staff and
  stop being the only person who can set anything up.
- If you already have panel access, the same messages address you directly and tell you that you
  can fix it yourself right now.
- Being told "you can't use this" is more useful too. `/board`, `/whitelist` and `/greeting`
  previously answered with a bare "Command Unavailable". They now explain which staff role is
  needed, and if no staff roles exist yet they say so, instead of implying you were denied.
- An empty result no longer pretends to be an answer. `/drop` with no drops channel, an empty
  `/wyr leaderboard` on a server that never turned WYR on, and `/suggest-search` where suggestions
  were never set up now say the feature is not switched on rather than "nothing found".

### Fixed
- Submitting a suggestion on a server with no suggestions channel used to save your suggestion and
  then fail, leaving it stored with nowhere to vote on it. The bot now checks there is somewhere to
  post **before** taking your suggestion, and tells you to send it again once the channel is set,
  so nothing gets quietly swallowed.
- You also find out about a missing suggestions channel straight away, rather than after working
  through the "similar suggestions found" prompt.

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
- Builder error messages were punctuated inconsistently - the same message could mix three
  different dash and arrow characters depending on which part of the check produced it, and the
  wording did not always match between the live editor and the message you got on save. They now
  read the same everywhere: `Container #1 -> Button "Rules" - label must be a non-empty string.`
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
