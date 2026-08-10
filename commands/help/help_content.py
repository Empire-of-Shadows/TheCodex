"""
Category content for the /help command.

Plain data module (no setup(), so the cog loader leaves it alone). The view
and cog live in help_commands.py.

TextDisplay formatting rules (verified against live rendering):
  - Bold (**text**) does NOT auto-newline. Append \\n explicitly after every
    bold header.
  - Use unicode bullets instead of dash list markers.
  - Keep each body well under the 4000-char TextDisplay limit.
"""

from dataclasses import dataclass
from typing import Optional

import discord

DASHBOARD_URL = "https://codex.eosofficial.club"


@dataclass(frozen=True)
class HelpCategory:
    key: str
    label: str
    description: str  # select-option description, max 100 chars
    emoji: str
    accent: int
    thumbnail: Optional[str]  # asset filename; None = bot avatar
    admin_only: bool
    blurb: str  # short line beside the thumbnail
    body: str


OVERVIEW = HelpCategory(
    key="overview",
    label="Overview",
    description="What this bot does and how to use this help",
    emoji="\N{BOOKS}",
    accent=discord.Color.blue().value,
    thumbnail=None,
    admin_only=False,
    blurb="The server's information desk, in one place.",
    body=(
        "**What this bot does**\n"
        "TheCodex holds the information members need and hands it back on request: "
        "a searchable server guide, an info board, suggestions, daily Would You "
        "Rather questions, Prime Gaming drops, and boost tracking.\n"
        "\n"
        "**Things that happen without a command**\n"
        "\N{BULLET} Mention the bot and it searches the server guide for you\n"
        "\N{BULLET} New accounts are screened on join, and members get the server's "
        "greeting message\n"
        "\N{BULLET} Posts in the announcement channel get a discussion thread opened "
        "under them\n"
        "\N{BULLET} Server boosts and the server tag are tracked, and boosters keep "
        "their perks automatically\n"
        "\n"
        "**Using this help**\n"
        "Pick a category from the dropdown below. Commands with [brackets] have "
        "optional parameters, <angle brackets> are required. Some commands are only "
        "available to certain roles, and the bot will tell you if yours is not one "
        "of them.\n"
        "\n"
        f"The web dashboard at {DASHBOARD_URL} is where server staff configure all "
        "of this in the browser.\n"
        "\n"
        "Responses to /help are only visible to you."
    ),
)

GUIDE = HelpCategory(
    key="guide",
    label="Guide & Info Board",
    description="Search the server guide and use the info board",
    emoji="\N{OPEN BOOK}",
    accent=discord.Color.from_rgb(77, 14, 179).value,  # guide accent, matches the renderer default
    thumbnail=None,
    admin_only=False,
    blurb="Ask the bot a question and it finds the answer for you.",
    body=(
        "**Mention the bot**\n"
        "There is no command for the guide - just mention the bot and type what you "
        "are looking for. It searches the guide your server wrote and opens the "
        "closest matching page.\n"
        "\N{BULLET} Mention it with nothing else and you get the how-to-use page\n"
        "\N{BULLET} Mention it with a word like help, info or guide and you land on "
        "the guide's home page\n"
        "\N{BULLET} Mention it with anything else and it searches, for example "
        "\"where are the rules\"\n"
        "\n"
        "**Getting around the guide**\n"
        "Every page has Back and Home buttons and a Search button, and pages with "
        "sections get a dropdown. Some pages have buttons that point you at a "
        "channel or hand you a self-assignable role.\n"
        "\n"
        "**The info board**\n"
        "A server can post a static info board in a channel. Its buttons and "
        "dropdowns reply to you privately, so the channel stays tidy. Nothing to "
        "run - just click.\n"
        "\n"
        "The guide can be turned off per server, and the pages are written by your "
        "staff, so what you find depends on what they have filled in."
    ),
)

SUGGESTIONS = HelpCategory(
    key="suggestions",
    label="Suggestions",
    description="Submit, search, and track suggestions",
    emoji="\N{ELECTRIC LIGHT BULB}",
    accent=discord.Color.gold().value,
    thumbnail=None,
    admin_only=False,
    blurb="Put an idea in front of the people who can act on it.",
    body=(
        "**`/suggest [suggestion_text] [anonymous] [category]`**\n"
        "Submit a suggestion. Run it with nothing and you get an interactive "
        "builder to write it in; pass suggestion_text and it posts straight away. "
        "Set anonymous to hide your name, and pick a category from Bot Feature, "
        "Server Improvement, Event Idea, Rule Change, or Other.\n"
        "Suggestions are capped at 2000 characters, and there is a 30 second wait "
        "between submissions.\n"
        "\n"
        "**`/suggest-search [query] [category] [status] [author]`**\n"
        "Search the server's suggestions. Filter by category, by status (Pending, "
        "Under Review, Approved, Implemented, Rejected, On Hold), or by who posted "
        "it. Shows the top 5 matches.\n"
        "\n"
        "**`/suggest-mine`**\n"
        "Your own suggestion history with each one's status and vote count.\n"
        "\n"
        "If your suggestion looks like one already posted, the bot shows you the "
        "similar ones first so you can decide whether to submit anyway."
    ),
)

WYR = HelpCategory(
    key="wyr",
    label="Would You Rather",
    description="Vote on the daily question and check your stats",
    emoji="\N{BLACK QUESTION MARK ORNAMENT}",
    accent=discord.Color.green().value,
    thumbnail=None,
    admin_only=False,
    blurb="A question a day, with a thread to argue about it in.",
    body=(
        "**Voting**\n"
        "A question is posted on a schedule with a thread underneath it. Click an "
        "option button to vote. You can change your vote at any time, and Show "
        "Results gives you the current split with your own pick marked.\n"
        "\n"
        "**`/wyr stats [user]`**\n"
        "Your voting record: how many times you picked each option, your overall "
        "split, and when you first and last voted. Pass a user to look up someone "
        "else.\n"
        "\n"
        "**`/wyr leaderboard [limit]`**\n"
        "The server's most active voters. Shows 10 by default, up to 25.\n"
        "\n"
        "**`/wyr results <message_id>`**\n"
        "The results for one specific question, by the message ID of the post.\n"
        "\n"
        "**`/wyr notify`**\n"
        "Turn the ping for new questions on or off. One button, and it tells you "
        "which state you are in.\n"
        "\n"
        "**`/wyr submit`**\n"
        "Suggest a question of your own, if this server has suggestions turned on. "
        "Pick the kind of question, write it, and send it - a moderator approves it "
        "before it can be posted, and you get a DM either way.\n"
        "\n"
        "Questions come from a written question bank, and a server can add its own "
        "on top of the shared one. A question can be a Would You Rather, a question "
        "with up to five answers, or an open-ended prompt with no answers at all. "
        "Age-restricted questions are only ever posted in channels Discord marks as "
        "age-restricted."
    ),
)

BOOSTS_DROPS = HelpCategory(
    key="boosts_drops",
    label="Boosts & Drops",
    description="Server boosts and free Prime Gaming drops",
    emoji="\N{ROCKET}",
    accent=discord.Color.from_rgb(255, 115, 250).value,  # nitro pink, matches the boost embeds
    thumbnail=None,
    admin_only=False,
    blurb="Who is boosting, and what is free to claim right now.",
    body=(
        "**`/drop`**\n"
        "Browse the Prime Gaming drops the bot has posted to this server, newest "
        "first, a page at a time. Members with the drops manager role also get "
        "buttons to see unsent drops and to push them out.\n"
        "\n"
        "**`/boosters`**\n"
        "Everyone currently boosting the server, longest-boosting first, with the "
        "server's boost count and level.\n"
        "\n"
        "**`/boosthistory [user]`**\n"
        "A member's boost status, when they started, how long they have been "
        "boosting, and their recent boost events. Defaults to you.\n"
        "\n"
        "Drops need a drops channel set up before anything is posted. If the list "
        "is empty, the bot tells you which of the two it is."
    ),
)

EMBEDS = HelpCategory(
    key="embeds",
    label="Embeds",
    description="Build and edit embeds, if your role allows it",
    emoji="\N{ARTIST PALETTE}",
    accent=discord.Color.from_rgb(88, 101, 242).value,  # blurple
    thumbnail=None,
    admin_only=False,
    blurb="Embed building, handed out per role.",
    body=(
        "**`/embed create`**\n"
        "Opens a form to build an embed. How long your description can be and "
        "which colors you get depend on your roles.\n"
        "\n"
        "**`/embed colors`**\n"
        "The colors your roles are allowed to use.\n"
        "\n"
        "**`/embed features`**\n"
        "The embed features your roles unlock.\n"
        "\n"
        "**`/embed edit <message_link_or_channel_id> [message_id]`**\n"
        "Edit an embed the bot posted. Pass a full message link, or a channel ID "
        "plus a message ID. Unless you are an admin you must be the one who made "
        "it, and only for a limited time after creating it.\n"
        "\n"
        "Embed access is opened up per role by server staff. If none of your roles "
        "have been given a tier yet, the bot says so and points staff at the "
        "setting rather than failing silently."
    ),
)

ADMIN = HelpCategory(
    key="admin",
    label="Admin",
    description="Server configuration and staff tools",
    emoji="\N{WRENCH}",
    accent=discord.Color.red().value,
    thumbnail=None,
    admin_only=True,
    blurb="Configuration and staff tools. Manage Server permission required.",
    body=(
        "**`/admin panel`**\n"
        "The full configuration panel: role access, embed settings, Would You "
        "Rather, new members, trackers, updates and drops, announcements, "
        "suggestions, the guide, and the info board. Every builder (guide, "
        "greeting, info board) takes a JSON upload and offers a template to start "
        "from.\n"
        "\n"
        "**Info board** - `/board post [channel]`, `/board refresh`, `/board info`\n"
        "Post the board, update the posted copy in place, or check its status and "
        "whether the saved layout is valid.\n"
        "\n"
        "**Greetings** - `/greeting test [member]`, `/greeting info`\n"
        "Send the greeting for a member to check how it looks, or review the "
        "greeting channel, the account age requirement, and who can run these.\n"
        "\n"
        "**Member screening** - `/whitelist add <user>`, `/whitelist remove <user>`, "
        "`/whitelist list`, `/whitelist check <user>`\n"
        "New accounts below the age requirement are removed on join unless they are "
        "whitelisted. All four are admin-only. Take a user ID rather than a username "
        "where you can - usernames are case sensitive.\n"
        "\n"
        "**Would You Rather** - `/wyr post [category] [random_pick]`, "
        "`/wyr reset_stats <user>`, `/wyr queue`\n"
        "Post a question by hand, clear one member's voting stats, or see the "
        "member suggestions waiting for review. Add your own questions - one at a "
        "time or a whole file at once - under **WYR Settings -> Question Bank** in "
        "`/admin panel`.\n"
        "\n"
        "**Clone Embed** (right-click a message -> Apps)\n"
        "Re-post that message's embeds cleanly, here or in another channel.\n"
        "\n"
        "**Web dashboard**\n"
        f"Everything above is also configurable in the browser at {DASHBOARD_URL} - "
        "sign in with Discord.\n"
        "\n"
        "Access is Manage Server or a configured Panel Access role - nothing else "
        "opens the panel or the dashboard. Set those roles first under Panel Access "
        "Roles."
    ),
)


CATEGORIES: dict[str, HelpCategory] = {
    c.key: c
    for c in (OVERVIEW, GUIDE, SUGGESTIONS, WYR, BOOSTS_DROPS, EMBEDS, ADMIN)
}
CATEGORY_ORDER: list[str] = list(CATEGORIES)
DEFAULT_CATEGORY = OVERVIEW.key
