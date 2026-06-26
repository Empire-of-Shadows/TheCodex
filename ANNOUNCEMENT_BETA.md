# TheCodex - Public Beta

> The bot that runs the unglamorous half of your server, now open for outside testing.

Most Discord bots focus on the loud parts of a community: games, music, points. **TheCodex** is built for the quiet, structural work that keeps a server livable - greeting new arrivals, answering "where do I find X," gathering member feedback, and keeping receipts on boosts and tags. It's the bot that handles the stuff your mods would otherwise be copy-pasting at 2am.

It was originally a private tool for one community. We've now rebuilt it so any server can host it, and we're opening that rebuild for outside testing.

> **Heads up:** This is a **beta**. The bot has been running steadily in its home server for a while, but it hasn't met the chaos of a multi-server install base yet. Bring it in, break it, and tell us where the seams show.

---

## The Toolkit

Everything drives off slash commands, an in-Discord admin panel, and a companion web dashboard.

**Member-facing**

- **Server Guide** - A page-tree guide rendered with Discord Components V2. Breadcrumbs, search, dropdowns, nested navigation. Authored as JSON or built visually on the dashboard.
- **Welcome Messages** - Interactive welcome flows with buttons, dropdowns, sections, and media. Same builder experience as the guide.
- **Would You Rather** - Daily scheduled questions, persistent vote buttons, auto-spawned discussion threads, per-user stats, leaderboards.
- **Natural-language guide lookup** - Ping the bot with a question; it points members at the matching guide page.

**Server-facing**

- **Suggestions** - Free text or templated submissions, community voting, status workflow, DM notifications on state change.
- **Announcements** - Auto-threads every post in your announcement channel so discussion has somewhere to land.
- **Trackers** - Boost tracking with reconcile-on-startup, server-tag rewards, and a `/drop` feed for Prime Gaming freebies.
- **New Member Screening** - Account-age gate with a whitelist for trusted friends.
- **Embed Utilities** - Build, clone, and edit rich embeds through guided modals with color presets and conflict detection.

---

## Rebuilt For Multi-Server Life

The original codebase baked "this is the only server" into config storage, guide content, and tracker state. That assumption is gone.

- **Hard tenant isolation.** Your guide, welcome layout, WYR schedule, suggestion queue, and tracker data live only in your server.
- **Self-installing, self-cleaning.** Joins set up scaffolding; leaves clean up after themselves.
- **Per-server admin panel.** Channels, roles, schedules, and feature toggles each managed from a navigable in-Discord panel.

---

## The Web Dashboard

The Discord admin panel is the fast path. The web dashboard is the deep path. You sign in with Discord, and your access is re-checked against live Discord roles on every request - so a permission change in Discord takes effect immediately on the dashboard.

- **Admin** (Manage Server, or a role you mark as admin) - every setting, every toggle, full audit log.
- **Mod** (roles you mark as mod) - just the features you trust them with.
- **Member** - public stats, personal data export, self-delete.

The dashboard's standout pieces:

- **Guide Builder.** Drag-and-drop page tree, live preview, schema validation, publish without touching JSON.
- **Welcome Builder.** Same editor, pointed at your new-member layout.
- **Audit Log.** Who changed what, when.
- **Privacy Center.** Every user can pull their data or wipe it themselves.

---

## What You'll Notice In Practice

- **Status that survives restarts.** The bot's presence rotates naturally and doesn't reset to a blank state after a deploy.
- **Persistent voting.** WYR buttons keep working across restarts - no dead posts.
- **Quiet reconciles.** Boost and tag trackers catch up on anything that changed while the bot was offline, without spam.
- **GDPR-shaped privacy flow.** Users own their data and can act on it without opening a ticket.
- **No dead ends in the panel.** Every screen has a way back and a current-state summary.

---

## What To Expect From A Beta

Honest expectations beat surprise frustrations:

- **Wild-server data is thin.** Most edge cases haven't met a server that isn't ours.
- **Flows may move.** Admin panel layout, dashboard structure, and schema shapes can change before stable.
- **Data isn't sacred yet.** Suggestion history, WYR stats, and tracker counts may reset during beta. Don't archive anything important off this bot.
- **Bugs are the point.** A detailed report - even a vague one - is worth more than a silent uninstall.

---

## How To Actually Help

The most useful thing testers can do is push the parts that have only been tested by one community:

- Build out a real guide and welcome with the visual builders. Nest pages, attach media, use the odd button layouts.
- Run WYR for at least a week, ideally across timezones, so we see schedule drift.
- Stress the admin panel: swap channels mid-flow, revoke a mod's role, log in as a regular member.
- Use the trackers in a server that genuinely boosts and tags so we get real-world reconcile data.
- File the rough edges in the support server: https://discord.gg/Zy7sSbKDmU

Multi-server is a different game than single-server, and we can only learn what breaks by watching it run somewhere else. Thanks for being one of the somewhere-elses.

---

**Add the bot:** https://discord.com/oauth2/authorize?client_id=1372808379000684584

**Support & bug reports:** https://discord.gg/Zy7sSbKDmU

^(TheCodex - currently in beta. Built by the Empire of Shadows team.)