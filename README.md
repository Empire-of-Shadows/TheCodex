<div align="center">

# TheCodex

**A searchable server guide, new-member screening, info boards, daily questions and a suggestion box, in one Discord bot.**

[![Add to Discord](https://img.shields.io/badge/Add_to-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/oauth2/authorize?client_id=1372808379000684584)
[![Dashboard](https://img.shields.io/badge/Dashboard-codex.eosofficial.club-7603FF?style=for-the-badge)](https://codex.eosofficial.club)
[![Docs](https://img.shields.io/badge/Docs-Wiki-7603FF?style=for-the-badge)](https://wiki.eosofficial.club/bots/thecodex)
[![Support](https://img.shields.io/badge/Support-Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/pex4AKTbFV)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![MongoDB](https://img.shields.io/badge/MongoDB-pymongo_async-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![RapidFuzz](https://img.shields.io/badge/Search-RapidFuzz-7603FF)](https://github.com/rapidfuzz/RapidFuzz)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)

</div>

TheCodex is for servers where the rules are a pinned wall of text nobody reads and staff answer the
same questions every day. Members mention the bot in plain language ("how do I get roles?") and
land on the right page of a guide your server wrote. It also screens new accounts, posts a daily
question, and runs a suggestion box.

> [!NOTE]
> TheCodex is where the Empire of Shadows ecosystem started, and it is free to add to any server.
> Its guide search is fuzzy text matching over the guide you write; there is no AI involved.

## Contents

- [Features](#features)
- [Commands](#commands)
- [Getting started](#getting-started)
- [Dashboard](#dashboard)
- [Privacy](#privacy)
- [Permissions and intents](#permissions-and-intents)
- [Development](#development)
- [Links](#links)

## Features

<table>
<tr>
<td width="50%" valign="top">

### Server guide
- Mention the bot with a question and it opens the closest matching page.
- Pages form a tree, with a breadcrumb and Back, Home and Search buttons.
- Built in a drag-and-drop editor on the dashboard, with a live preview.

</td>
<td width="50%" valign="top">

### New-member screening
- Accounts younger than your minimum age (90 days by default) can be removed on join, after a
  DM explaining why. Auto-kick is a setting you choose.
- Whitelist a specific account with `/whitelist` to let it in; it gets a temporary role that is
  removed, with a congratulations DM, once the account is old enough.
- A welcome message you design, with placeholders for the member, the member count and more.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Info boards
- One permanent message whose buttons answer common questions privately, toggle self-roles, or
  point to channels. Built in the same editor as the guide.

</td>
<td width="50%" valign="top">

### Daily questions
- A daily Would You Rather, poll (up to 5 options) or open question, at the time and timezone you
  set, each with its own discussion thread and an optional ping role.
- Voting buttons that survive restarts, results, a leaderboard, and member submissions with
  review. NSFW questions only ever post in age-restricted channels.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Suggestions
- `/suggest` posts an idea with four vote buttons and a discussion thread, and warns about
  similar existing suggestions first. It can be anonymous.
- Statuses: Pending, Under Review, Approved, Implemented, Rejected, On Hold. The author gets a
  DM when the status changes.
- `/suggestions` searches and filters them.

</td>
<td width="50%" valign="top">

### And more
- **Announcements:** opens a discussion thread under each post in your announcement channel.
- **Prime Gaming drops:** posts new free Prime Gaming games daily, and `/drop` browses them.
- **Boost log** and **server tag role** for members who wear your server's tag.
- **Embed studio:** `/embed create` builds rich embeds, with features unlocked by role.

</td>
</tr>
</table>

## Commands

| Command | Who can use it | What it does |
|---|---|---|
| *Mention the bot* | Everyone | Search the server guide. |
| `/suggest` | Everyone | Submit a suggestion, or open a form to write one. |
| `/suggestions` | Everyone | Browse and search suggestions. |
| `/wyr submit` `stats` `notify` `results` `leaderboard` | Everyone | Daily questions: submit one, see stats, toggle the ping, see results and rankings. |
| `/drop` | Everyone | Browse current Prime Gaming drops. |
| `/embed create` `edit` `colors` `features` | By role | Build and edit embeds. What you can use depends on your roles. |
| **Clone Embed** (right-click a message) | Manage Messages | Copy an existing embed into the editor. |
| `/whitelist <user>` | Manage Server | Let an account in past the account-age check. |
| `/help` | Everyone | How everything works. |
| `/admin panel` | Manage Server or a panel admin role | Configure the bot for this server. |

There is no `/guide` command: mention the bot instead.

## Getting started

1. [Add TheCodex to your server](https://discord.com/oauth2/authorize?client_id=1372808379000684584).
2. Run `/admin panel` and switch on the features you want: guide, screening, daily questions,
   suggestions, announcements, drops.
3. Build your guide, info board and welcome message on the
   [dashboard](https://codex.eosofficial.club) with the drag-and-drop builder.
4. Mention the bot with a question to try the guide.

> [!IMPORTANT]
> If you turn on auto-kick, whitelist any new account you want to let in first. With auto-kick
> off, the bot never removes anyone, and you can decline the Kick Members permission.

## Dashboard

[codex.eosofficial.club](https://codex.eosofficial.club) signs you in with Discord, using the same
login as every Empire of Shadows site.

| Page | Who sees it |
|---|---|
| **Home** and **Privacy** - opt-outs, export and erase | You |
| **Server overview, Settings, Builder, Audit log** - everything in the panel, the guide/board/greeting builder, and who changed what | Admins (Manage Server or a panel admin role) |
| **Terms**, **Privacy policy** | Anyone, no login |

## Privacy

- Members can opt out from the dashboard's Privacy page, and export or erase what is held about
  them. Opted-out members cannot vote or submit.
- Command usage is counted in aggregate only, never per member.
- The full policy covering every Empire of Shadows bot is at
  [eosofficial.club/privacy](https://eosofficial.club/privacy).

## Permissions and intents

| Permission | Why |
|---|---|
| View Channel, Send Messages, Embed Links | Guides, boards, questions, suggestions. |
| Read Message History | Finding and updating its own boards, questions and embeds. |
| Create Public Threads, Send Messages in Threads, Manage Threads | Suggestion, question and announcement threads, and cleaning them up. |
| Attach Files | In the invite but not used today. A `/help` page with a picture would use it; `/help` still works without it. |
| Manage Roles | Self-roles from boards, the whitelist role, the server tag role, the question ping role. The bot's role must sit above them. |
| Kick Members | Only used if you turn on auto-kick. |

The invite link takes its permission set from the bot's Discord Developer Portal settings.

**Intents:** Guilds, Server Members, Guild Messages and Message Content. Server Members is needed
for screening joins and the tag role; Message Content for guide mentions. The bot cannot ping
@everyone or roles.

## Development

<details>
<summary><b>Running it locally</b></summary>

<br>

Requires Python 3.13 and MongoDB. Configuration is read from `docker/.env`, with an optional
`docker/.env.local` override. Both are gitignored.

```bash
pip install -r requirements.txt
python Codex.py                 # the bot, health endpoint on :50010

pip install -r dashboard/requirements.txt
python -m dashboard.app         # the dashboard API, :54010

cd dashboard/frontend
npm install && npm run build    # the React front end
```

`docker/codex.sh` deploys both services and rolls back if the new build fails its health check.

</details>

<details>
<summary><b>How the code is organised</b></summary>

<br>

| Path | What it is |
|---|---|
| `Codex.py` | Entry point: database, health endpoint, then the bot. |
| `startup/` | Bot construction and cog discovery. |
| `Features/` | Most features: guide, new members, daily questions, suggestions, boards, announcements, trackers, embed tools. |
| `commands/` | Help, drops and owner tools. |
| `storage/` | Database layer. Shared storage engine plus TheCodex's settings in `storage/settings/`. |
| `admin/` | The `/admin panel`. Shared admin engine plus TheCodex's panel tree in `admin/settings/`. |
| `markdownfiles/` | Builder documentation the dashboard serves to the editor. |
| `dashboard/` | FastAPI backend and React front end. |

Files that start with a `# VENDORED ... DO NOT EDIT HERE` banner are copied in from the shared
engines in the `EmpireSystems` repository. Change them there and re-sync; never edit the copy.

Tests and migrations live outside this repository, in the ecosystem's `TestsAndMigrations/TheCodex/`
folder.

</details>

## Links

- [Changelog](CHANGELOG.md) - what changed, in plain language
- [TheCodex on the wiki](https://wiki.eosofficial.club/bots/thecodex)
- [All six bots](https://wiki.eosofficial.club/bots) and [the main site](https://eosofficial.club)
- [Support server](https://discord.gg/pex4AKTbFV) for help and bug reports
- [Community server](https://discord.gg/xx86YEhaYF), where the bots were built and are played

## Contributing, security and license

Contributions are welcome under the terms in [CONTRIBUTING.md](CONTRIBUTING.md). Please report
security problems privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

Copyright (c) 2025-2026 Empire of Shadows. All rights reserved; see [LICENSE](LICENSE).

<div align="center">
<sub>Part of the <a href="https://eosofficial.club">Empire of Shadows</a> ecosystem</sub>
</div>
