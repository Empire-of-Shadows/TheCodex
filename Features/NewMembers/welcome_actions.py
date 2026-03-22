"""
Welcome Action Registry & Dispatcher

Named action system for welcome message component interactions.
Replaces freeform custom_id strings with a discoverable, multi-guild-safe registry.
"""

from utils.logger import get_logger

logger = get_logger("WelcomeActions")

# ─────────────────────────────────────────────────────────────────────────────
# Action Registry
# ─────────────────────────────────────────────────────────────────────────────

VALID_ACTIONS = {
    "open_guide":      {"description": "Opens the server guide menu",           "params": []},
    "server_info":     {"description": "Shows server statistics",               "params": []},
    "channel_list":    {"description": "Shows channel overview",                "params": []},
    "getting_started": {"description": "Shows getting started tips",            "params": []},
    "suggest":         {"description": "Opens the suggestion submission form",  "params": []},
    "browse_drops":    {"description": "Browse available free gaming drops",    "params": []},
    "server_rules":    {"description": "Shows link to server rules channel",    "params": []},
    "role_info":       {"description": "Shows server roles overview",           "params": []},
}

_PREFIX = "w"


# ─────────────────────────────────────────────────────────────────────────────
# Custom ID Encoding / Decoding
# ─────────────────────────────────────────────────────────────────────────────

def encode_custom_id(action: str, params: dict | None = None) -> str:
    """Encode an action name into a Discord custom_id string.

    Format: ``w:<action_name>``
    """
    return f"{_PREFIX}:{action}"


def decode_custom_id(raw: str) -> tuple[str | None, dict]:
    """Decode a custom_id string back into (action_name, params).

    Returns (None, {}) if the string doesn't match our prefix.
    """
    if not raw.startswith(f"{_PREFIX}:"):
        return None, {}
    rest = raw[len(_PREFIX) + 1:]
    # For now all actions are parameterless
    action = rest
    if action not in VALID_ACTIONS:
        return None, {}
    return action, {}


# ─────────────────────────────────────────────────────────────────────────────
# Handler Functions
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_open_guide(interaction, params: dict):
    from Features.Guide.guide import get_help_menu
    layout = await get_help_menu(interaction.user.id, guild_id=interaction.guild.id, interaction=interaction)
    await interaction.response.send_message(view=layout, ephemeral=True)


async def _handle_server_info(interaction, params: dict):
    import discord
    guild = interaction.guild
    embed = discord.Embed(
        title=f"{guild.name} Server Information",
        color=discord.Color.blue(),
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="Statistics",
        value=(
            f"**Members:** {guild.member_count:,}\n"
            f"**Created:** <t:{int(guild.created_at.timestamp())}:F>\n"
            f"**Server ID:** {guild.id}"
        ),
        inline=False,
    )

    text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
    voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])

    embed.add_field(name="Channels", value=f"**Text:** {text_channels}\n**Voice:** {voice_channels}", inline=True)
    embed.add_field(name="Roles", value=f"**Total:** {len(guild.roles) - 1}", inline=True)

    if guild.premium_tier > 0:
        embed.add_field(
            name="Nitro Boost",
            value=f"**Level {guild.premium_tier}**\n**Boosts:** {guild.premium_subscription_count}",
            inline=True,
        )

    embed.set_footer(text="Welcome to our community!")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _handle_channel_list(interaction, params: dict):
    import discord
    guild = interaction.guild
    embed = discord.Embed(
        title=f"{guild.name} - All Channels",
        color=discord.Color.green(),
    )

    categories = guild.categories
    text_channels = [c for c in guild.text_channels if c.category is None]
    voice_channels = [c for c in guild.voice_channels if c.category is None]

    if categories:
        category_info = []
        for category in categories[:10]:
            category_info.append(f"**{category.name}** ({len(category.channels)} channels)")
        embed.add_field(name="Channel Categories", value="\n".join(category_info) or "None", inline=False)

    if text_channels:
        embed.add_field(name="Uncategorized Text Channels", value=f"{len(text_channels)} channels", inline=True)

    if voice_channels:
        embed.add_field(name="Uncategorized Voice Channels", value=f"{len(voice_channels)} channels", inline=True)

    embed.add_field(
        name="Channel Summary",
        value=(
            f"**Total Categories:** {len(categories)}\n"
            f"**Total Text Channels:** {len([c for c in guild.channels if isinstance(c, discord.TextChannel)])}\n"
            f"**Total Voice Channels:** {len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])}"
        ),
        inline=False,
    )

    embed.set_footer(text="Explore all our channels!")
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _handle_getting_started(interaction, params: dict):
    import discord
    guild = interaction.guild
    embed = discord.Embed(
        title="Getting Started Guide",
        description="Here's how to make the most of your time in our server!",
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="Gaming Features",
        value=(
            "- Use `/uno` to start a UNO game\n"
            "- Try `/tictactoe` for quick matches\n"
            "- Play `/hangman` with friends\n"
            "- Check leaderboards with `/stats`"
        ),
        inline=False,
    )

    embed.add_field(
        name="Community Features",
        value=(
            "- Share suggestions with `/suggest`\n"
            "- Get help by mentioning our bot\n"
            "- Join voice channels for events\n"
            "- Participate in community discussions"
        ),
        inline=False,
    )

    rules_ch = discord.utils.find(
        lambda c: 'rules' in c.name.lower() and isinstance(c, discord.TextChannel),
        guild.channels,
    )
    rules_mention = f"<#{rules_ch.id}>" if rules_ch else "the rules channel"

    embed.add_field(
        name="Quick Tips",
        value=(
            f"- Read the rules in {rules_mention}\n"
            "- Introduce yourself in chat\n"
            "- Join voice channels when active\n"
            "- Have fun and be respectful!"
        ),
        inline=False,
    )

    embed.set_footer(text="Welcome to the community!")
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _handle_suggest(interaction, params: dict):
    from Features.suggestion.suggest import SuggestionModal
    await interaction.response.send_modal(SuggestionModal("Bot Feature"))


async def _handle_browse_drops(interaction, params: dict):
    cog = interaction.client.get_cog("PrimeDrops")
    if cog is None:
        await interaction.response.send_message("Drops feature is not currently available.", ephemeral=True)
        return

    try:
        drops = await cog.collection_manager.find_many(
            {"sent": {"$ne": True}},
            sort=[("expires", 1)],
        )
    except Exception:
        drops = []

    if not drops:
        await interaction.response.send_message("No free gaming drops available right now. Check back later!", ephemeral=True)
        return

    embeds = cog._create_drops_embeds(drops, "Free Gaming Drops")
    await interaction.response.send_message(embed=embeds[0], ephemeral=True)


async def _handle_server_rules(interaction, params: dict):
    import discord
    guild = interaction.guild
    rules_ch = discord.utils.find(
        lambda c: 'rules' in c.name.lower() and isinstance(c, discord.TextChannel),
        guild.channels,
    )

    if rules_ch is None:
        await interaction.response.send_message("No rules channel found in this server.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Server Rules",
        description=f"Please read the rules in <#{rules_ch.id}> to stay up to date with our community guidelines.",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Following the rules keeps our community safe!")
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def _handle_role_info(interaction, params: dict):
    import discord
    guild = interaction.guild
    roles = [r for r in guild.roles if r.name != "@everyone" and not r.is_bot_managed()]
    roles.sort(key=lambda r: r.position, reverse=True)

    if not roles:
        await interaction.response.send_message("No roles to display.", ephemeral=True)
        return

    # Cap at 20 to avoid embed limits
    displayed = roles[:20]
    role_lines = [f"{r.mention} — {r.member_count} member{'s' if r.member_count != 1 else ''}" for r in displayed]

    embed = discord.Embed(
        title=f"{guild.name} — Roles Overview",
        description="\n".join(role_lines),
        color=discord.Color.blurple(),
    )
    if len(roles) > 20:
        embed.set_footer(text=f"Showing top 20 of {len(roles)} roles")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Handler Dispatch Table
# ─────────────────────────────────────────────────────────────────────────────

_HANDLERS = {
    "open_guide":      _handle_open_guide,
    "server_info":     _handle_server_info,
    "channel_list":    _handle_channel_list,
    "getting_started": _handle_getting_started,
    "suggest":         _handle_suggest,
    "browse_drops":    _handle_browse_drops,
    "server_rules":    _handle_server_rules,
    "role_info":       _handle_role_info,
}


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def dispatch_welcome_action(interaction) -> bool:
    """Dispatch a component interaction to the matching action handler.

    Returns True if handled, False if the custom_id doesn't match our prefix.
    """
    component_type = interaction.data.get("component_type")

    if component_type == 3:  # Select menu — action is in the selected value
        values = interaction.data.get("values", [])
        if not values:
            return False
        raw_id = values[0]
    else:
        raw_id = interaction.data.get("custom_id", "")

    action_name, params = decode_custom_id(raw_id)
    if action_name is None:
        return False

    handler = _HANDLERS.get(action_name)
    if handler is None:
        logger.warning(f"Action '{action_name}' is registered but has no handler")
        return False

    try:
        await handler(interaction, params)
    except Exception as e:
        logger.error(f"Error handling welcome action '{action_name}': {e}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong. Please try again.", ephemeral=True)

    return True
