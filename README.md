<div align="center">

# TheCodex

**The guide and community management bot for Empire of Shadows**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.6+-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MongoDB](https://img.shields.io/badge/MongoDB-motor-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

Information hub, daily engagement, suggestions, announcements, new member screening,
boost tracking, and more — all configurable per guild through slash commands and an admin panel.

A companion **web dashboard** lets admins build and preview guide pages with a drag-and-drop editor.

</div>

---

## Features

<table>
<tr>
<td width="50%" valign="top">

### :book: Guide System
- Page-tree navigation with breadcrumbs and search
- Natural language mention-based lookups
- Guide content rendered as Discord Components V2
- Web dashboard with drag-and-drop builder and live preview

</td>
<td width="50%" valign="top">

### :thinking: Would You Rather
- Scheduled daily question posts with configurable time and timezone
- Persistent button voting that survives bot restarts
- Category filtering and thread auto-creation

</td>
</tr>
<tr>
<td width="50%" valign="top">

### :bulb: Suggestions
- Submit ideas with `/suggest submit`, browse with `/suggest search`
- Community voting with live result updates
- Status tracking: Pending, Under Review, Approved, Implemented, Rejected, On Hold
- DM notifications on status changes

</td>
<td width="50%" valign="top">

### :mega: Announcements
- Channel-based announcement posting
- Optional thread auto-creation
- Configurable thread naming and archive duration

</td>
</tr>
<tr>
<td width="50%" valign="top">

### :shield: New Member Screening
- Configurable account age requirements
- Whitelist role bypass and auto-kick
- Welcome messages with customizable header, body, and channel highlights

</td>
<td width="50%" valign="top">

### :rocket: Boost Tracking
- Logs server boosts and boost events to a configured channel

</td>
</tr>
<tr>
<td width="50%" valign="top">

### :label: Tag Tracker
- Monitors server tag usage
- Assigns a role when the tag is active

</td>
<td width="50%" valign="top">

### :video_game: Updates & Drops Tracker
- Tracks gaming drops and updates across configured channels
- Weekly, monthly, and all-time statistics

</td>
</tr>
</table>

### :gear: Admin Panel
> `/admin` command with grouped settings for every feature — channels, roles, toggles, guide template upload, and more — all through interactive menus.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Bot** | Python 3.13 &middot; discord.py 2.6+ &middot; MongoDB (motor) |
| **Dashboard** | FastAPI &middot; React 19 &middot; Vite &middot; TypeScript |
| **Search** | RapidFuzz fuzzy matching |
| **Deployment** | Docker Compose with health checks and auto-rollback |

---

## License

This bot is developed for the **Empire of Shadows** community and is not available for external use at this time. See [LICENSE](./LICENSE) for details.

<div align="center">
<sub>Built for the Empire of Shadows community</sub>
</div>