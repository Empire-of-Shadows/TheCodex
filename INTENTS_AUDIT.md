# Discord Privileged Intents Audit - TheCodex Bot

Current intent configuration: `utils/bot.py:10-17`

---

## 1. Presence Intent

**Currently enabled:** NO (not in `utils/bot.py`)

**Where it is used:**

| Location | Usage | What breaks without it |
|---|---|---|
| `storage/cache.py:119-120` | `cache_guild_info()` - counts online members via `member.status != discord.Status.offline` | `member.status` will always be `offline` - online count will always be 0 |
| `storage/cache.py:416-419` | `cache_members()` - stores `member.status`, `mobile_status`, `desktop_status`, `web_status` | All status fields will be `offline`/`None` |
| `storage/cache.py:431-434` | `cache_members()` - stores `member.activities` (games, streaming, etc.) | Activities list will always be empty |
| `storage/cache.py:485-486` | `cache_guild_analytics()` - counts online members | Online count will always be 0 |
| `Features/NewMembers/joining.py:87-88` | `initialize_guild_cache()` - counts online members | Online count will always be 0 |
| `Features/NewMembers/joining.py:859-862` | `on_presence_update` event handler | Event will never fire - currently a stub (just logs, then `pass`) |

**Impact assessment:** MODERATE. Online/offline counts in the cache and analytics will always read as 0. No actual bot feature depends on these counts for decision-making - they are purely informational/analytics data cached to the database and dashboard.

**Can the same features be achieved without this intent?**

- **Online member count:** No reliable alternative. Discord does not provide online counts via REST API for bots. `guild.approximate_presence_count` is available but only populated when the guild is fetched with `with_counts=True` via REST, not from the cache. Could use that as an approximation on a scheduled task but it won't be real-time.
- **Member status/activity caching:** No alternative. Per-member status data is only available through the Presence intent.
- **`on_presence_update` event:** No alternative, but the handler is currently a stub that does nothing.

**Recommendation:** NOT NEEDED currently. The `on_presence_update` handler is a no-op stub. The online counts are nice-to-have analytics but no feature depends on them. If you want accurate online counts in the dashboard/cache, enable it. Otherwise, leave it off and either remove the status-checking code or accept 0 values.

---

## 2. Server Members Intent

**Currently enabled:** YES (`utils/bot.py:12` - `intents.members = True`)

**Where it is used:**

| Location | Usage | What breaks without it |
|---|---|---|
| **Member join/leave events** | | |
| `Features/NewMembers/joining.py:653` | `on_member_join` - triggers welcome messages, cache updates, security checks | Welcome system completely breaks. New members get no welcome message, no role assignment, no tracking. |
| `Features/NewMembers/joining.py:657` | `on_member_remove` - tracks member departures | Leave tracking breaks. |
| `Features/NewMembers/joining.py:661` | `on_member_update` - currently a logging stub | Event stops firing. No impact (stub). |
| `Features/trackers/boosts/boost_tracker.py:20` | `on_member_update` - detects boost start/stop via `premium_since` changes | Boost tracking completely breaks. Bot cannot detect when someone starts or stops boosting. |
| **Iterating `guild.members`** | | |
| `storage/cache.py:118,124,384,483,490,502` | Iterates all members for bot count, premium count, role distribution, member caching, analytics | `guild.members` will only contain the bot itself. All counts will be wrong (bot_count=0, human_count=0, etc.). Guild cache and analytics will be empty/incorrect. |
| `Features/NewMembers/joining.py:74,85,95,168,176,534` | Counts humans, bots, builds role distribution | Same as above - all guild metrics break. |
| `Features/Guide/guide_renderer.py:199-201` | `{member_count}` placeholder - counts non-bot members for guide display | Member count in guide pages shows "0". |
| `Features/NewMembers/welcome_actions.py:256` | `len(r.members)` - shows role member counts in welcome embeds | Role member counts show 0 in welcome messages. |
| `Features/NewMembers/admin/whitelist.py:159,178,218,348,377` | `guild.get_member()` and iterates `guild.members` for whitelist management | Whitelist role management breaks - can't look up members or iterate them. |
| `Features/NewMembers/tasks/whitelist_role_cleanup.py:95` | `guild.get_member()` for cleanup task | Cleanup task can't find members to remove stale whitelist entries. |
| **Fetching members** | | |
| `Features/trackers/tag/tag_tracker.py:51` | `guild.fetch_members(limit=None)` - iterates ALL members to check server tags | Tag tracker breaks. Note: `fetch_members()` itself requires this intent. |
| `commands/admin/admin_cog.py:1914` | `bot.http.get_member()` - fetches owner data via HTTP | This is an HTTP call, NOT dependent on the members intent. Still works. |

**Impact assessment:** CRITICAL. Removing this intent would break:
1. The entire welcome/join system
2. Boost tracking
3. All guild member analytics and caching
4. Tag tracker
5. Whitelist management
6. Member count placeholders in guides and welcome messages

**Can the same features be achieved without this intent?**

- **`on_member_join` / `on_member_remove`:** NO alternative. These events require the Members intent.
- **`on_member_update`:** NO alternative. Required for boost detection.
- **`guild.members` iteration:** Partial alternative. Could use `guild.fetch_members()` but that ALSO requires the Members intent. Without the intent, you'd need to track members yourself via join events (which also require the intent). There is no workaround.
- **`guild.get_member()`:** Could use `await guild.fetch_member(user_id)` as a REST fallback, but this is rate-limited and still requires the intent for the full member list.

**Recommendation:** REQUIRED. This is non-negotiable. The majority of the bot's features depend on it.

---

## 3. Message Content Intent

**Currently enabled:** YES (`utils/bot.py:13` - `intents.message_content = True`)

**Where it is used:**

| Location | Usage | What breaks without it |
|---|---|---|
| `Features/Guide/guide_mention.py:50` | `message.content.lower().strip()` - reads message text to parse guide search queries after bot mention | Guide mention search breaks. `message.content` will be empty string. Bot can't read what the user typed after mentioning it. |
| `Features/Guide/guide_mention.py:64` | Strips bot mention from content to get clean search query | Same as above. |
| `Features/announcements/announcements.py:45` | `message.content[:50]` - logs message preview | Log line shows empty string. Minor. |
| `Features/announcements/announcements.py:105-114` | `message.content` - used to format thread names from announcement text | Thread names will be empty/generic since content is empty. Threads still get created but with no meaningful name. |
| `Features/NewMembers/joining.py:885-892` | `on_message` event + `bot.process_commands(message)` | The `on_message` event still fires (messages intent handles that). However, prefix commands (`.command`) will not work because `message.content` will be empty - `process_commands` can't parse the prefix. Slash commands are unaffected. |
| `Features/updates-drops/drops-tracker.py:123-178` | `on_message` listener - counts messages in tracked channels | This still works! The drops tracker only cares that a message was sent (counts it), not what the content is. The `on_message` event fires regardless of this intent. `message.content` length is logged but not used for logic. |
| `Features/updates-drops/drops-tracker.py:180-198` | `on_message_edit` listener - checks embed changes | Still works. Only checks `message.embeds`, not content. |

**Impact assessment:** MODERATE-HIGH. Removing this intent would break:
1. Guide mention search (primary guide access method via `@bot <query>`)
2. Announcement thread naming (threads still created but with bad names)
3. Any prefix commands (`.command` style)

Features that would NOT break:
- Slash commands (all admin commands)
- Drops tracker (only counts messages, doesn't read content)
- Message event firing (still fires, just with empty `content`)

**Can the same features be achieved without this intent?**

- **Guide mention search:** PARTIAL. When the bot is mentioned, it does receive `message.content` even without the intent (bot mentions are an exception in Discord's API). So this feature may actually still work since the bot checks `if self.bot.user not in message.mentions` first. **However**, this exception only applies when the bot is directly mentioned, not for prefix commands.
- **Announcement thread naming:** Could switch to using the first embed's title/description as the thread name instead of `message.content`. Since announcements often contain embeds, this could work.
- **Prefix commands:** Switch entirely to slash commands. The bot already uses slash commands for all admin functionality. If there are no user-facing prefix commands that matter, this is viable.

**Recommendation:** LIKELY NEEDED. The guide mention feature is a core user-facing feature. While the bot-mention exception *might* deliver content, it's not guaranteed for all message types. If you want to remove this intent, test that the bot-mention exception works reliably, switch announcement thread naming to use embeds, and ensure no prefix commands are needed.

---

## Summary Table

| Intent | Enabled | Verdict | Features at risk |
|---|---|---|---|
| **Presence** | No | NOT NEEDED | Online counts (analytics only), `on_presence_update` (stub) |
| **Server Members** | Yes | REQUIRED | Welcome system, boost tracking, all member analytics, tag tracker, whitelist |
| **Message Content** | Yes | LIKELY NEEDED | Guide mention search, announcement thread names, prefix commands |

## Notes

- `intents.messages = True` and `intents.guild_messages = True` (lines 11, 17) are redundant. `guild_messages` is a subset of `messages`. Having both is harmless but `guild_messages` alone would suffice if you don't need DM message events.
- `intents.reactions = True` (line 15) is used by reaction event handlers in `joining.py:924+`. Not a privileged intent.
- `intents.emojis = True` (line 16) is not a privileged intent.
- `intents.guilds = True` (line 14) is included in `Intents.default()` already, so explicitly setting it is redundant but harmless.