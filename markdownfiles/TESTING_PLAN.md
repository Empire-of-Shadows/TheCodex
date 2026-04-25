# TheCodex Multi-Guild Testing Plan

## Pre-Release Audit Summary

### Issues Found

**1. `updates-drops/drops-tracker.py` lines 31-35 — Hardcoded channel IDs (MODERATE)**
The channel map maps specific Discord channel IDs to collection names. Only works for one guild. To support multi-guild, the channel map should come from guild config or a DB collection. This is an isolated analytics feature and does not affect core bot functionality.

**2. `Guide/guide_mention.py` line 28 — Hardcoded `allowed_bot_ids` (LOW)**
Two bot IDs are hardcoded. Could be moved to guild config for per-guild customization, but since these are our own bot IDs, it works fine as-is across all guilds.

### Everything Else: Clean
- Suggestion system, Boost tracker, Tag tracker, Guide system, Welcome/Whitelist, WYR, Prime drops, User stats, Config system — all properly scoped by `guild_id`.

---

## Testing Plan

### Phase 1: Core Bot Startup
- [ ] Bot starts without errors
- [ ] All cogs load successfully (check logs)
- [ ] Database connections established
- [ ] Health endpoint responds

### Phase 2: Guild Configuration (`/config`)
- [ ] `/config channel` — set each channel type (welcome, suggestions, rewards, admin, drops, wyr, announcement, boost_log)
- [ ] `/config tag_tracker` — enable/disable, set server tag, set role
- [ ] `/config view` — verify all settings display correctly
- [ ] Test in a **second guild** to confirm configs are independent

### Phase 3: Guide System
- [ ] `/guide` — main menu loads with categories
- [ ] Navigate into a category, then a sub-item
- [ ] Back button and Main Menu button work
- [ ] Search functionality returns results
- [ ] Quick access saves and loads
- [ ] Breadcrumb navigation works
- [ ] Guide mention trigger (bot posts -> guide responds)
- [ ] Test in **second guild** — verify breadcrumbs/quick-access are independent

### Phase 4: Suggestion System
- [ ] `/suggest` — submit a suggestion
- [ ] Suggestion appears in configured channel
- [ ] Voting works (approve/deny buttons)
- [ ] `/suggestions list` — shows only current guild's suggestions
- [ ] `/suggestions stats` — stats scoped to guild
- [ ] Test in **second guild** — verify suggestions don't cross-pollinate

### Phase 5: Boost Tracker
- [ ] Simulate a boost event (or wait for one)
- [ ] Boost logged to configured `boost_log` channel
- [ ] `/boosters` — lists current guild's boosters
- [ ] `/boost_history` — shows guild-scoped history

### Phase 6: Tag Tracker
- [ ] Enable via `/config tag_tracker`
- [ ] Set server tag and role
- [ ] Verify role assignment runs for members with the tag
- [ ] Verify role removal for members who remove the tag

### Phase 7: Welcome / Whitelist System
- [ ] New member join triggers welcome in configured channel
- [ ] Whitelist commands work per-guild
- [ ] Role cleanup task runs without errors

### Phase 8: Daily Systems
- [ ] WYR daily post fires in configured channel
- [ ] Prime drops post fires in configured channel
- [ ] Both post to **each configured guild** independently

### Phase 9: Cross-Guild Isolation (Critical)
- [ ] Add bot to two test guilds
- [ ] Configure different channels in each
- [ ] Verify data doesn't leak between guilds (suggestions, stats, guides, boosts)
- [ ] Verify commands only show data for the current guild