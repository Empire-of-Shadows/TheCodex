# Would You Rather (WYR) System

## Overview

Would You Rather (WYR) posts a daily question to a designated channel, presenting two or three options for the community to vote on. Each question arrives as a Discord embed with voting buttons. Clicking a button casts your vote and you can change your mind at any time. A discussion thread is automatically created alongside every question so members can talk through their choices.

***

## How Questions Work

Every day at a configurable time the bot selects the least used question from the question pool and posts it in the configured WYR channel. The question appears as an embed titled **"Would You Rather..."** showing two or three bold options beneath it.

### Voting

Below every question you will find up to four buttons:

* **1️⃣ Option 1** votes for the first choice
* **2️⃣ Option 2** votes for the second choice
* **3️⃣ Option 3** votes for the third choice (only shown when the question includes a third option)
* **Show Results** reveals the current vote breakdown privately, visible only to you

When you cast a vote a private confirmation message appears. If you change your mind simply click a different button and your vote updates instantly. Your leaderboard count only increases on your very first vote for a given question. Changing your answer does not add more votes to your total.

### Discussion Threads

Each posted question automatically opens a discussion thread directly beneath the post. The thread name and opening message are fully customisable by server admins and can include details pulled from the question itself using placeholders. Threads archive automatically after a configurable period of inactivity.

***

## Commands

All WYR commands start with `/wyr`.

***

### /wyr stats

Displays your WYR voting history, or the history of another member if one is mentioned.

**Usage**

* `/wyr stats` shows your own stats
* `/wyr stats user:@Member` shows stats for the mentioned member

**What you see**

* How many times you voted for each option
* Your total vote count across all questions
* Your voting preference shown as percentages
* When you cast your first ever vote and your most recent vote

***

### /wyr results

Shows the live vote counts and percentage breakdown for any WYR question posted in this server.

**Usage**

* `/wyr results message_id:<ID>` right click any WYR post, copy its message ID, then paste it here

**What you see**

* A progress bar for each option showing the percentage of the community that chose it
* The raw vote count per option
* The total number of votes cast so far

Results are shown only to you so you can check without influencing anyone else.

**How to copy a message ID**

Enable Developer Mode in Discord settings under App Settings > Advanced, then right click the WYR post and choose **Copy Message ID**.

***

### /wyr leaderboard

Shows the most active voters in the server, ranked by total vote count.

**Usage**

* `/wyr leaderboard` shows the top 10 voters
* `/wyr leaderboard limit:20` shows up to 20 voters

***

### /wyr post (Admin only)

Immediately posts a WYR question without waiting for the daily schedule. Requires the **Manage Messages** permission.

**Usage**

* `/wyr post` posts the next least used question using the server's default category
* `/wyr post category:sfw` restricts the pick to safe for work questions
* `/wyr post category:nsfw` restricts the pick to not safe for work questions
* `/wyr post random_pick:True` picks a completely random question instead of the least used one

***

### /wyr reset_stats (Admin only)

Wipes all WYR voting history for a specific member. Requires the **Administrator** permission. This action cannot be undone.

**Usage**

* `/wyr reset_stats user:@Member`

***

## Admin Setup

All WYR settings are managed through the admin panel. Open the admin panel and navigate to **WYR** to find the following sections.

***

### WYR Channel

The channel where questions are posted each day. Only one channel per server is supported. No questions will post until a channel is set.

***

### WYR Ping Role

An optional role that gets mentioned every time a new question is posted. Leave this empty if you do not want any pings.

***

### WYR Schedule

Controls when the daily question goes out. Each field saves independently.

* **Post Hour** the hour of day to post, in 24 hour format (0 = midnight, 12 = noon, 20 = 8 PM)
* **Post Minute** the minute offset within that hour (:00, :15, :30, or :45)
* **Timezone** the timezone used to interpret the hour and minute above

The bot checks the schedule every minute and posts once per day per guild as soon as the clock matches the configured hour and minute in the guild's timezone.

***

### WYR Category

The default pool of questions to draw from when posting.

* **SFW** safe for work questions only
* **NSFW** not safe for work questions only
* **Mixed** draws from both pools

***

### WYR Thread Settings

Controls the discussion thread that is created alongside every question post.

#### Thread Name & Message

Both the thread name format and the opening starter message are configured together in a single panel entry. Clicking **Edit** opens a modal with two fields that save atomically.

**Thread Name Format** (field 1)

The name given to the discussion thread when it is created. Discord caps thread names at 100 characters, so the bot automatically trims the name to that limit after filling in any placeholders.

Default: `🎲 WYR · Q{question_num} · {date}`

**Starter Message** (field 2)

The opening message posted inside the thread when it is first created. Supports the same placeholders as the thread name above. Up to 500 characters. Leave blank to post no opening message.

Default:
```
🎲 **{question}**

1️⃣ {option_1}
2️⃣ {option_2}

What's your reasoning? Share your thoughts below!
```

**Available placeholders** (both fields)

* `{date}` inserts the post date formatted as MM/DD (example: `02/25`)
* `{question_num}` inserts the sequential question number (example: `401`)
* `{category}` inserts the question category in title case (example: `General`)
* `{option_1}` inserts the full text of the first option
* `{option_2}` inserts the full text of the second option
* `{option_3}` inserts the full text of the third option, or an empty string if the question only has two options
* `{question}` inserts the full question text

Any text that looks like a placeholder but is not on the list above is left exactly as typed with no error.

**Example thread name**

```
🎲 WYR · Q{question_num} · {date}
```

Produces: `🎲 WYR · Q401 · 02/25`

If the question only has two options, `{option_3}` resolves to an empty string. Consider phrasing any line containing it so an empty value looks natural, or omit `{option_3}` entirely if your question pool is two-option only.

#### Auto Archive Duration

How long the thread stays open after the last message before Discord archives it automatically.

* 1 Hour
* 1 Day
* 3 Days
* 1 Week

***

### WYR Cleanup

Controls how long the bot keeps internal records that link each Discord message to its question. Older records are removed automatically on a rolling basis. This setting does not delete the posted messages themselves. It only removes the internal tracking data that `/wyr results` relies on.

If a question post is older than the cleanup window `/wyr results` will no longer be able to look it up by message ID.

Available windows: 7 days, 14 days, 30 days, 60 days, 90 days.

***

## Quick Reference

**For regular members**

* Vote by clicking the option buttons on any WYR post
* Change your vote at any time by clicking a different button
* Use `/wyr stats` to see your personal voting history
* Use `/wyr leaderboard` to see the top voters
* Use `/wyr results message_id:<ID>` to check the vote breakdown on any question

**For admins**

* Set up a WYR channel in the admin panel before any questions will post
* Configure the post time, timezone, and category to suit your community
* Customise thread names and starter messages using placeholders for dynamic content
* Use `/wyr post` to push a question out immediately outside the normal schedule
