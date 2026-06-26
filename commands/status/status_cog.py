"""Bot presence admin commands.

Slash command group `/status` scoped to a single admin guild. Lets the bot
operator set the live presence and store named presets to switch between.
"""

import discord
from discord import app_commands
from discord.ext import commands

from startup.bot import bot
from utils.logger import get_logger

logger = get_logger("StatusAdmin")

# Only this guild gets the commands.
GUILD_ID = 1265120128295632926
GUILD_OBJ = discord.Object(id=GUILD_ID)

# Discord caps activity name at 128 chars.
MAX_NAME_LEN = 128
MAX_URL_LEN = 256
MAX_PRESET_NAME_LEN = 64
MAX_PRESETS_IN_SELECT = 25  # Discord select option cap.

ACTIVITY_TYPES: dict[str, discord.ActivityType | str] = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "competing": discord.ActivityType.competing,
    "streaming": "streaming",
    "custom": "custom",
}


def _build_activity(activity_type: str, name: str, url: str | None) -> discord.BaseActivity:
    if activity_type == "streaming":
        return discord.Streaming(name=name, url=url or "https://twitch.tv/")
    if activity_type == "custom":
        return discord.CustomActivity(name=name)
    return discord.Activity(type=ACTIVITY_TYPES[activity_type], name=name)


def _presets_collection():
    return bot.db_manager.get_collection_manager("bot_statuses")


async def _apply_preset(preset: dict) -> None:
    activity = _build_activity(
        preset["activity_type"], preset["name"], preset.get("url")
    )
    await bot.change_presence(activity=activity)


def _validate_type(value: str) -> str | None:
    atype = value.strip().lower()
    return atype if atype in ACTIVITY_TYPES else None


# ── Modals ──────────────────────────────────────────────────────────────────


class SetStatusModal(discord.ui.Modal, title="Set Bot Status"):
    activity_type = discord.ui.TextInput(
        label="Type",
        placeholder="playing | watching | listening | competing | streaming | custom",
        max_length=16,
        required=True,
    )
    status_text = discord.ui.TextInput(
        label=f"Status text (max {MAX_NAME_LEN})",
        max_length=MAX_NAME_LEN,
        required=True,
    )
    url = discord.ui.TextInput(
        label="URL (streaming only, optional)",
        required=False,
        max_length=MAX_URL_LEN,
    )

    async def on_submit(self, interaction: discord.Interaction):
        atype = _validate_type(self.activity_type.value)
        if atype is None:
            await interaction.response.send_message(
                f"❌ Invalid type. Valid: {', '.join(ACTIVITY_TYPES)}",
                ephemeral=True,
            )
            return

        name = self.status_text.value.strip()
        url = self.url.value.strip() or None

        try:
            await bot.change_presence(activity=_build_activity(atype, name, url))
        except Exception as e:
            logger.error(f"Failed to set status: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Failed to set status: {e}", ephemeral=True
            )
            return

        logger.info(f"{interaction.user} set status: {atype}: {name}")
        await interaction.response.send_message(
            f"✅ Status set — **{atype}**: `{name}`", ephemeral=True
        )


class SavePresetModal(discord.ui.Modal, title="Save Status Preset"):
    preset_name = discord.ui.TextInput(
        label="Preset name",
        max_length=MAX_PRESET_NAME_LEN,
        required=True,
    )
    activity_type = discord.ui.TextInput(
        label="Type",
        placeholder="playing | watching | listening | competing | streaming | custom",
        max_length=16,
        required=True,
    )
    status_text = discord.ui.TextInput(
        label=f"Status text (max {MAX_NAME_LEN})",
        max_length=MAX_NAME_LEN,
        required=True,
    )
    url = discord.ui.TextInput(
        label="URL (streaming only, optional)",
        required=False,
        max_length=MAX_URL_LEN,
    )

    def __init__(self, apply_now: bool = False):
        super().__init__()
        self._apply_now = apply_now

    async def on_submit(self, interaction: discord.Interaction):
        atype = _validate_type(self.activity_type.value)
        if atype is None:
            await interaction.response.send_message(
                f"❌ Invalid type. Valid: {', '.join(ACTIVITY_TYPES)}",
                ephemeral=True,
            )
            return

        name = self.status_text.value.strip()
        url = self.url.value.strip() or None
        pname = self.preset_name.value.strip()

        doc = {"preset_name": pname, "activity_type": atype, "name": name, "url": url}

        try:
            await _presets_collection().update_one(
                {"preset_name": pname},
                {"$set": doc},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Failed to save preset {pname!r}: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Failed to save preset: {e}", ephemeral=True
            )
            return

        msg = f"✅ Saved preset **{pname}** — {atype}: `{name}`"
        if self._apply_now:
            try:
                await _apply_preset(doc)
                msg += "\n✅ Applied as current status."
            except Exception as e:
                msg += f"\n⚠️ Saved but failed to apply: {e}"

        logger.info(f"{interaction.user} saved preset {pname!r}")
        await interaction.response.send_message(msg, ephemeral=True)


# ── Components V2 list view ─────────────────────────────────────────────────


class PresetSelect(discord.ui.Select):
    def __init__(self, presets: list[dict]):
        options = [
            discord.SelectOption(
                label=p["preset_name"][:100],
                description=f"{p['activity_type']}: {p['name'][:50]}",
                value=p["preset_name"],
            )
            for p in presets[:MAX_PRESETS_IN_SELECT]
        ]
        super().__init__(
            placeholder="Pick a preset…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        pname = self.values[0]
        preset = await _presets_collection().find_one({"preset_name": pname})
        if not preset:
            await interaction.response.send_message(
                f"❌ Preset `{pname}` no longer exists.", ephemeral=True
            )
            return
        try:
            await _apply_preset(preset)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to apply: {e}", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ Applied **{pname}** — {preset['activity_type']}: `{preset['name']}`",
            ephemeral=True,
        )


class DeletePresetSelect(discord.ui.Select):
    def __init__(self, presets: list[dict]):
        options = [
            discord.SelectOption(label=p["preset_name"][:100], value=p["preset_name"])
            for p in presets[:MAX_PRESETS_IN_SELECT]
        ]
        super().__init__(
            placeholder="Delete a preset…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        pname = self.values[0]
        deleted = await _presets_collection().delete_one({"preset_name": pname})
        if deleted:
            await interaction.response.send_message(
                f"🗑️ Deleted preset **{pname}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Preset `{pname}` not found.", ephemeral=True
            )


def build_preset_layout(presets: list[dict]) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=300.0)
    layout.add_item(discord.ui.TextDisplay("## Bot Status Presets"))

    if not presets:
        layout.add_item(discord.ui.TextDisplay("_No presets saved yet. Use `/status save`._"))
        return layout

    summary = "\n".join(
        f"• **{p['preset_name']}** — {p['activity_type']}: `{p['name']}`"
        for p in presets[:MAX_PRESETS_IN_SELECT]
    )
    layout.add_item(discord.ui.TextDisplay(summary))
    layout.add_item(discord.ui.Separator())

    apply_row = discord.ui.ActionRow()
    apply_row.add_item(PresetSelect(presets))
    layout.add_item(apply_row)

    delete_row = discord.ui.ActionRow()
    delete_row.add_item(DeletePresetSelect(presets))
    layout.add_item(delete_row)

    if len(presets) > MAX_PRESETS_IN_SELECT:
        layout.add_item(discord.ui.TextDisplay(
            f"_Showing first {MAX_PRESETS_IN_SELECT} of {len(presets)} presets._"
        ))
    return layout


# ── Cog ─────────────────────────────────────────────────────────────────────


class StatusAdmin(commands.Cog):
    """Admin commands for the bot's Discord presence."""

    status_group = app_commands.Group(
        name="status",
        description="Manage the bot's Discord presence",
        guild_ids=[GUILD_ID],
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @status_group.command(name="set", description="Set the bot's current status")
    async def set_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SetStatusModal())

    @status_group.command(name="save", description="Save a new status preset")
    @app_commands.describe(apply="Apply immediately after saving")
    async def save_cmd(self, interaction: discord.Interaction, apply: bool = False):
        await interaction.response.send_modal(SavePresetModal(apply_now=apply))

    @status_group.command(name="list", description="List saved status presets")
    async def list_cmd(self, interaction: discord.Interaction):
        presets = await _presets_collection().find_many(
            {}, sort=[("preset_name", 1)], limit=100
        )
        await interaction.response.send_message(
            view=build_preset_layout(presets), ephemeral=True
        )

    @status_group.command(name="clear", description="Clear the bot's current activity")
    async def clear_cmd(self, interaction: discord.Interaction):
        await self.bot.change_presence(activity=None)
        await interaction.response.send_message("✅ Activity cleared.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatusAdmin(bot))
    logger.info(f"StatusAdmin cog loaded (guild-scoped to {GUILD_ID})")
