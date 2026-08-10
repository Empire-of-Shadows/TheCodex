import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timezone

from storage.settings.collections import db_manager
from storage.log import get_logger
from storage.settings.config_manager import get_config
from admin.setup_notice import permission_notice_embed
from admin.actions.whitelist_nodes import WhitelistPanelActions

logger = get_logger("WhitelistManager")

# Configuration
WHITELIST_ROLE_NAME = "Whitelisted New Member"
WHITELIST_ROLE_COLOR = discord.Color.blue()
ACCOUNT_AGE_REQUIREMENT_DAYS = 90  # Must match the age check in joining.py


def has_whitelist_admin_app():
    """App command check for every whitelist command (read and mutation).

    Admin-only: Administrator permission or a configured Panel Access role.
    There is no moderator tier, so viewing and changing the screening whitelist
    are gated the same way.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False

        user = interaction.user

        perms = getattr(user, "guild_permissions", None)
        if perms and perms.administrator:
            return True

        guild_config = await get_config(interaction.guild.id)
        user_role_ids = {role.id for role in getattr(user, "roles", [])}
        admin_set = set(guild_config.roles["admin_role_ids"])

        return bool(user_role_ids & admin_set)

    return app_commands.check(predicate)


class WhitelistReasonModal(discord.ui.Modal, title="Whitelist Member"):
    """Modal for collecting the reason for whitelisting a member.

    Opened from the ``/whitelist`` state card, for a first-time add and for a
    reactivation alike - ``_add_to_whitelist_internal`` decides which of the two
    it is from what is already stored.
    """

    reason = discord.ui.TextInput(
        label="Reason for whitelisting",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this member being whitelisted? (e.g., Friend of active member, known from another community)",
        required=True,
        min_length=10,
        max_length=500
    )

    def __init__(self, cog, user_identifier: str, resolved_member: Optional[discord.Member] = None,
                 *, card: "WhitelistStateCard"):
        super().__init__()
        self.cog = cog
        self.user_identifier = user_identifier
        self.resolved_member = resolved_member
        self.card = card

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # If we already resolved the member, use it; otherwise resolve now
        if self.resolved_member:
            result = await self.cog._add_to_whitelist_internal(
                interaction,
                self.resolved_member,
                str(self.reason)
            )
        else:
            result = await self.cog._add_to_whitelist_internal(
                interaction,
                self.user_identifier,
                str(self.reason)
            )

        if result['success']:
            embed = discord.Embed(
                title="✅ Member Whitelisted",
                description=result['message'],
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            if 'details' in result:
                embed.add_field(name="Details", value=result['details'], inline=False)
        else:
            embed = discord.Embed(
                title="❌ Whitelist Failed",
                description=result['message'],
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )

        embed.set_footer(text=f"Action by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        # One response per interaction. The response is spent re-rendering the
        # card so it never sits on the state it had before the write; the
        # outcome of the write arrives as a followup.
        await self.card.refresh(interaction)
        await interaction.followup.send(embed=embed, ephemeral=True)


class WhitelistStateCard(discord.ui.LayoutView):
    """The one screen behind ``/whitelist``.

    It answers "where does this person stand with the screening whitelist?" and
    then offers only the action that state allows, so there is no way to press
    Add on somebody who is already on the list or Remove on somebody who is not.

    Three states, read off the ``serverdata_whitelist`` document:

    * no document          -> Add to Whitelist
    * document, active     -> Remove from Whitelist (behind a confirm step)
    * document, not active -> Reactivate

    The account-age block on the first state is the old ``/whitelist check``
    capability: it says how old the account is, what this server requires, and
    whether that person is actually being screened out today.

    Ephemeral, author-locked and short-lived, like every other one-off card in
    the bot.
    """

    def __init__(
        self,
        cog: "WhitelistGroup",
        *,
        author_id: int,
        guild: discord.Guild,
        user_id: int,
        username: str,
        in_guild: bool,
        created_at: datetime,
        entry: Optional[dict],
        new_members: dict,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.guild = guild
        self.user_id = user_id
        self.username = username
        self.in_guild = in_guild
        self.created_at = created_at
        self.entry = entry
        self.new_members = dict(new_members)
        self.confirming_removal = False
        self.render()

    # ---- state ---------------------------------------------------------

    @property
    def state(self) -> str:
        """"absent", "active" or "removed" - the three cards this can be."""
        if not self.entry:
            return "absent"
        if self.entry.get("is_active", True):
            return "active"
        return "removed"

    @property
    def account_age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.created_at).days

    @property
    def age_requirement_days(self) -> int:
        return self.new_members.get("account_age_requirement_days", ACCOUNT_AGE_REQUIREMENT_DAYS)

    @property
    def role_name(self) -> str:
        return self.new_members.get("whitelist_role_name") or WHITELIST_ROLE_NAME

    def _resolve_whitelist_role(self) -> Optional[discord.Role]:
        """The configured whitelist role, if it exists. Read-only.

        Same lookup order as ``_ensure_whitelist_role`` - configured id first,
        then name - but this one never creates the role: "there is no such role"
        is a legitimate answer here, and creating one while reporting on a
        removal would be absurd.
        """
        role_id = self.new_members.get("whitelist_role_id")
        if role_id:
            role = self.guild.get_role(role_id)
            if role is not None:
                return role
        return discord.utils.get(self.guild.roles, name=self.role_name)

    @property
    def _accent(self) -> discord.Color:
        return {
            "absent": discord.Color.blurple(),
            "active": discord.Color.green(),
            "removed": discord.Color.orange(),
        }[self.state]

    # ---- state -> text ---------------------------------------------------

    def _header_text(self) -> str:
        presence = (
            "In this server" if self.in_guild else "Not in this server yet"
        )
        return (
            "## Screening Whitelist\n"
            f"**{self.username}** - <@{self.user_id}> (`{self.user_id}`)\n"
            f"**Where they are:** {presence}"
        )

    def _age_text(self) -> str:
        """How old the account is against what this server asks for."""
        age = self.account_age_days
        required = self.age_requirement_days
        lines = [
            f"**Account age:** {age} day(s); this server asks for {required}."
        ]

        if age >= required:
            lines.append(
                "They already clear the account-age check, so they do not need "
                "a whitelist entry to get in."
            )
        elif not self.new_members.get("enabled", False):
            lines.append(
                "Their account is under that, but new member screening is "
                "switched off here, so nobody is being turned away right now."
            )
        elif not self.new_members.get("auto_kick", True):
            lines.append(
                "Their account is under that, but auto-kick is switched off "
                "here, so nobody is being turned away right now."
            )
        else:
            lines.append(
                "Their account is under that, so without a whitelist entry they "
                "are turned away by the account-age check."
            )
            if not self.new_members.get("whitelist_enabled", True):
                lines.append(
                    "Note: the whitelist itself is switched off on this server, "
                    "so an entry will not let them past until it is switched "
                    "back on."
                )
        return "\n".join(lines)

    def _role_forecast_text(self) -> str:
        """Whether whitelisting this person would hand them the role."""
        if self.account_age_days >= self.age_requirement_days:
            return f"**{self.role_name}:** not needed at their account age."
        if self.in_guild:
            return (
                f"**{self.role_name}:** whitelisting them now also gives them "
                f"this role."
            )
        return (
            f"**{self.role_name}:** handed to them when they join, not now."
        )

    def _absent_text(self) -> str:
        return (
            "**Not on the whitelist.**\n\n"
            f"{self._age_text()}\n\n"
            f"{self._role_forecast_text()}"
        )

    def _active_text(self) -> str:
        entry = self.entry or {}
        added_at = entry.get("added_at")
        when = (
            f"<t:{int(added_at.timestamp())}:F>"
            if isinstance(added_at, datetime)
            else "at an unrecorded time"
        )
        added_by = entry.get("added_by")
        who = f"<@{added_by}>" if added_by else (
            entry.get("added_by_username") or "someone no longer recorded"
        )
        role_state = (
            f"Yes, they hold **{self.role_name}**"
            if entry.get("role_assigned")
            else "No"
        )
        return (
            "**On the whitelist.** They are allowed past the account-age check.\n\n"
            f"**Added by:** {who}\n"
            f"**Added:** {when}\n"
            f"**Reason:** {entry.get('reason') or 'No reason recorded'}\n"
            f"**Whitelist role assigned:** {role_state}"
        )

    def _removed_text(self) -> str:
        entry = self.entry or {}
        removed_at = entry.get("removed_at")
        when = (
            f"<t:{int(removed_at.timestamp())}:F>"
            if isinstance(removed_at, datetime)
            else "at an unrecorded time"
        )
        removed_by = entry.get("removed_by")
        by = f" by <@{removed_by}>" if removed_by else ""
        return (
            "**Was on the whitelist, and was taken off.** They are screened on "
            "account age like anybody else.\n\n"
            f"**Taken off:** {when}{by}\n"
            f"**Original reason for whitelisting:** "
            f"{entry.get('reason') or 'No reason recorded'}\n\n"
            f"{self._age_text()}"
        )

    def _body_text(self) -> str:
        if self.state == "active":
            return self._active_text()
        if self.state == "removed":
            return self._removed_text()
        return self._absent_text()

    # ---- rendering -------------------------------------------------------

    def render(self):
        """Rebuild the layout for the state the card is currently in."""
        self.clear_items()

        container = discord.ui.Container(accent_color=self._accent)
        container.add_item(discord.ui.TextDisplay(self._header_text()))
        container.add_item(discord.ui.Separator())

        if self.confirming_removal:
            container.add_item(
                discord.ui.TextDisplay(
                    WhitelistPanelActions.confirm_line(self.entry or {})
                )
            )
        else:
            container.add_item(discord.ui.TextDisplay(self._body_text()))

        container.add_item(discord.ui.Separator())
        container.add_item(self._controls_row())
        self.add_item(container)

    def _controls_row(self) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()

        if self.state == "active" and self.confirming_removal:
            confirm_btn = discord.ui.Button(
                label="Confirm Removal",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
            )
            confirm_btn.callback = self._on_remove_confirm
            back_btn = discord.ui.Button(
                label="Cancel",
                style=discord.ButtonStyle.secondary,
            )
            back_btn.callback = self._on_remove_cancel
            row.add_item(confirm_btn)
            row.add_item(back_btn)
            return row

        if self.state == "active":
            remove_btn = discord.ui.Button(
                label="Remove from Whitelist",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
            )
            remove_btn.callback = self._on_remove_request
            row.add_item(remove_btn)
        elif self.state == "removed":
            reactivate_btn = discord.ui.Button(
                label="Reactivate",
                style=discord.ButtonStyle.success,
                emoji="♻️",
            )
            reactivate_btn.callback = self._on_add
            row.add_item(reactivate_btn)
        else:
            add_btn = discord.ui.Button(
                label="Add to Whitelist",
                style=discord.ButtonStyle.success,
                emoji="✅",
            )
            add_btn.callback = self._on_add
            row.add_item(add_btn)

        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary)
        close_btn.callback = self._on_close
        row.add_item(close_btn)
        return row

    async def refresh(self, interaction: discord.Interaction):
        """Re-read the document and re-render, spending this interaction's response."""
        self.confirming_removal = False
        self.entry = await self.cog._fetch_whitelist_entry(self.guild.id, self.user_id)
        self.render()
        await interaction.response.edit_message(view=self)

    # ---- guards ----------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This whitelist card belongs to someone else. Run `/whitelist` "
                "to open your own.",
                ephemeral=True,
            )
            return False
        return True

    # ---- component callbacks --------------------------------------------

    async def _on_add(self, interaction: discord.Interaction):
        member = self.guild.get_member(self.user_id) if self.in_guild else None
        modal = WhitelistReasonModal(
            self.cog,
            str(self.user_id),
            resolved_member=member or self.user_id,
            card=self,
        )
        await interaction.response.send_modal(modal)

    async def _on_remove_request(self, interaction: discord.Interaction):
        """Step in front of the destructive action, same as the panel's."""
        self.confirming_removal = True
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_remove_cancel(self, interaction: discord.Interaction):
        self.confirming_removal = False
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_remove_confirm(self, interaction: discord.Interaction):
        entry = self.entry or {}
        role_was_assigned = bool(entry.get("role_assigned"))
        member = self.guild.get_member(self.user_id)

        # Whether they are actually wearing the role has to be read BEFORE the
        # removal: discord.py only drops it from the member cache when the
        # MEMBER_UPDATE event lands, so reading it afterwards proves nothing.
        role = self._resolve_whitelist_role()
        held_the_role = bool(
            role_was_assigned
            and member is not None
            and role is not None
            and role in getattr(member, "roles", [])
        )

        removed = await WhitelistPanelActions.remove_entry(
            self.guild.id,
            self.user_id,
            actor_id=interaction.user.id,
            role_reason=f"Removed from whitelist by {interaction.user} using /whitelist",
        )

        # Re-read before saying anything about the role. _strip_whitelist_role
        # swallows every failure, and clears the stored ``role_assigned`` flag
        # only on the path where ``remove_roles`` actually went through - so the
        # refreshed document is the one honest signal about whether the role came
        # off. refresh() spends this interaction's response on the re-render,
        # which is why the outcome embed has to follow it as a followup.
        await self.refresh(interaction)
        refreshed = self.entry or {}

        if removed:
            details = f"**User:** {self.username} (`{self.user_id}`)"
            if role_was_assigned and member is not None:
                if not refreshed.get("role_assigned"):
                    details += "\n**Whitelist Role:** taken back off them as well"
                elif held_the_role:
                    details += (
                        f"\n⚠️ **Whitelist Role:** could not be taken off "
                        f"automatically. They still hold **{self.role_name}**, so "
                        f"it needs removing by hand."
                    )
                    logger.warning(
                        f"Whitelist role left on {self.username} ({self.user_id}) in "
                        f"guild {self.guild.name} after removal by {interaction.user}"
                    )
                else:
                    details += (
                        f"\n**Whitelist Role:** nothing to take off - they were "
                        f"not holding **{self.role_name}**."
                    )
            embed = discord.Embed(
                title="✅ Removed from Whitelist",
                description=f"Successfully removed **{self.username}** from the whitelist.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Details", value=details, inline=False)
            logger.info(
                f"User {self.username} ({self.user_id}) removed from whitelist by "
                f"{interaction.user} in guild {self.guild.name}"
            )
        else:
            embed = discord.Embed(
                title="❌ Removal Failed",
                description=(
                    f"**{self.username}** (`{self.user_id}`) could not be taken off "
                    "the whitelist. They may already have been removed by someone "
                    "else - the card below shows where they stand now."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
        embed.set_footer(
            text=f"Action by {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        # The re-render already spent the response, above.
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _on_close(self, interaction: discord.Interaction):
        closed = discord.ui.LayoutView()
        closed.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("Whitelist card closed."),
                accent_color=discord.Color.dark_grey(),
            )
        )
        await interaction.response.edit_message(view=closed)
        self.stop()


class WhitelistGroup(commands.Cog):
    """
    Cog providing one command:
    - /whitelist <user> - look one person up and act on where they stand

    It replaced the old `add` and `remove` subcommands, which made an admin know
    the answer before asking the question: pick `add` on somebody already on the
    list and you got an error, pick `remove` on somebody who was never on it and
    you got another. One command resolves the person, shows the state, and
    offers only the action that state allows. The account-age block on that card
    is the old `check` command's job, back again.

    Browsing the whole list is still the admin panel's (New Members ->
    Whitelisted Members); it replaced the old `list` command, which capped out
    at 25 entries with no way past it.

    ``default_permissions`` on the command is what stops Discord listing it for
    every member. The real gate is still ``has_whitelist_admin_app`` below,
    which also honours Panel Access roles; that only sets the DEFAULT
    visibility. A server that grants Panel Access to a role without Manage
    Server can hand that role the command under Server Settings ->
    Integrations.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("WhitelistGroup initialized")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Explain a denied whitelist command instead of a bare "unavailable".

        The whitelist command is admin-tier, so the notice names the Panel
        Access role and where it is granted. One command now both reads the
        state and changes it, so the wording covers both.
        """
        if not isinstance(error, app_commands.CheckFailure):
            raise error

        embed = await permission_notice_embed(
            interaction.guild,
            action="view or change the screening whitelist",
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.debug(f"Could not deliver whitelist permission notice: {e}")

    async def _ensure_whitelist_role(self, guild: discord.Guild) -> discord.Role:
        """Ensure the whitelist role exists, create if needed."""
        guild_config = await get_config(guild.id)
        role_name = guild_config.new_members["whitelist_role_name"]

        # Check by ID first, then by name
        if guild_config.new_members["whitelist_role_id"]:
            existing_role = guild.get_role(guild_config.new_members["whitelist_role_id"])
            if existing_role:
                return existing_role
        existing_role = discord.utils.get(guild.roles, name=role_name)
        if existing_role:
            return existing_role

        # Create the role
        try:
            role = await guild.create_role(
                name=role_name,
                color=WHITELIST_ROLE_COLOR,
                reason="Whitelist role for new members with new accounts",
                mentionable=False,
                hoist=True  # Display separately in member list
            )
            logger.info(f"Created whitelist role '{role_name}' in guild {guild.name}")
            return role
        except Exception as e:
            logger.error(f"Failed to create whitelist role: {e}")
            raise

    async def _resolve_user_identifier(self, guild: discord.Guild, identifier: str) -> Optional[tuple[int, str, bool]]:
        """
        Resolve a user identifier (ID or username) to (user_id, username, in_guild).

        Args:
            guild: The Discord guild
            identifier: User ID or username (case-sensitive)

        Returns:
            Tuple of (user_id, username, in_guild) or None if not found
        """
        # Try to parse as user ID
        try:
            user_id = int(identifier)
            # Try to find member in guild
            member = guild.get_member(user_id)
            if member:
                return (user_id, member.name, True)

            # Try to fetch user from Discord API
            try:
                user = await self.bot.fetch_user(user_id)
                return (user_id, user.name, False)
            except discord.NotFound:
                return None
            except Exception as e:
                logger.error(f"Error fetching user {user_id}: {e}")
                return None

        except ValueError:
            # Not a valid ID, treat as username (case-sensitive)
            username = identifier

            # Search in guild members first (case-sensitive)
            for member in guild.members:
                if member.name == username:  # Case-sensitive comparison
                    return (member.id, member.name, True)

            # Username not found in guild
            return None

    async def _add_to_whitelist_internal(self, interaction: discord.Interaction, user_or_id, reason: str) -> dict:
        """
        Internal method to add a user to the whitelist.

        Args:
            interaction: The interaction object
            user_or_id: Either a discord.Member, discord.User, user ID string, or username
            reason: The reason for whitelisting

        Returns:
            Dict with 'success', 'message', and optionally 'details'
        """
        guild = interaction.guild

        try:
            # Resolve the user
            if isinstance(user_or_id, (discord.Member, discord.User)):
                user_id = user_or_id.id
                username = user_or_id.name
                in_guild = isinstance(user_or_id, discord.Member)
                member = user_or_id if in_guild else None
            else:
                # String identifier (ID or username)
                resolution = await self._resolve_user_identifier(guild, str(user_or_id))
                if not resolution:
                    return {
                        'success': False,
                        'message': f"Could not find user: `{user_or_id}`\n\n"
                                   "**Tip:** Usernames are case-sensitive. Make sure you're using the exact username, "
                                   "or use the user ID instead."
                    }

                user_id, username, in_guild = resolution
                member = guild.get_member(user_id) if in_guild else None

            # Check if user is a bot
            if member and member.bot:
                return {
                    'success': False,
                    'message': "Cannot whitelist bot accounts."
                }

            # Get whitelist collection
            whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')

            # Check if already whitelisted (snowflake IDs are stored as strings)
            existing = await whitelist_collection.find_one({
                'guild_id': str(guild.id),
                'user_id': str(user_id)
            })

            if existing:
                if existing.get('is_active', True):
                    return {
                        'success': False,
                        'message': f"**{username}** (`{user_id}`) is already whitelisted.\n\n"
                                   f"Added by: <@{existing.get('added_by')}>\n"
                                   f"Date: <t:{int(existing.get('added_at').timestamp())}:F>\n"
                                   f"Reason: {existing.get('reason', 'No reason provided')}"
                    }
                else:
                    # Reactivate
                    await whitelist_collection.update_one(
                        {'guild_id': str(guild.id), 'user_id': str(user_id)},
                        {'$set': {
                            'is_active': True,
                            'reactivated_at': datetime.now(timezone.utc),
                            'reactivated_by': str(interaction.user.id),
                            'reactivated_reason': reason
                        }}
                    )
                    return {
                        'success': True,
                        'message': f"**{username}** (`{user_id}`) has been reactivated on the whitelist.",
                        'details': f"**Reason:** {reason}"
                    }

            # Add to whitelist
            whitelist_entry = {
                'guild_id': str(guild.id),
                'user_id': str(user_id),
                'username': username,
                'added_by': str(interaction.user.id),
                'added_by_username': interaction.user.name,
                'added_at': datetime.now(timezone.utc),
                'reason': reason,
                'is_active': True,
                'role_assigned': False,
                'role_assigned_at': None
            }

            await whitelist_collection.create_one(whitelist_entry)

            # If member is in guild and has a new account, assign the role
            role_assigned = False
            if member:
                guild_config = await get_config(guild.id)
                account_age = (datetime.now(timezone.utc) - member.created_at).days
                if account_age < guild_config.new_members["account_age_requirement_days"]:
                    try:
                        role = await self._ensure_whitelist_role(guild)
                        await member.add_roles(role, reason=f"Whitelisted by {interaction.user}")
                        role_assigned = True

                        # Update database with role info
                        await whitelist_collection.update_one(
                            {'guild_id': str(guild.id), 'user_id': str(user_id)},
                            {'$set': {
                                'role_assigned': True,
                                'role_assigned_at': datetime.now(timezone.utc),
                                'account_age_at_whitelist': account_age
                            }}
                        )
                        logger.info(f"Assigned whitelist role to {member} (account age: {account_age} days)")
                    except Exception as e:
                        logger.error(f"Failed to assign whitelist role: {e}")

            details = f"**User:** {username} (`{user_id}`)\n**Reason:** {reason}"
            if role_assigned:
                details += f"\n**Role Assigned:** Yes (account age: {account_age} days)"
            elif member:
                details += f"\n**Role Assigned:** No (account age: {(datetime.now(timezone.utc) - member.created_at).days} days - no role needed)"
            else:
                details += "\n**Role Assigned:** N/A (user not in server yet)"

            logger.info(f"User {username} ({user_id}) added to whitelist by {interaction.user} in guild {guild.name}")

            return {
                'success': True,
                'message': f"Successfully added **{username}** to the whitelist!",
                'details': details
            }

        except Exception as e:
            logger.error(f"Error adding to whitelist: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"An error occurred: {str(e)}"
            }

    async def _fetch_whitelist_entry(self, guild_id: int, user_id: int) -> Optional[dict]:
        """The whitelist document for one member in one guild, active or not.

        Snowflakes are stored as strings; an int filter matches nothing and
        reports a silent "never whitelisted", so both sides are cast.
        """
        whitelist_collection = db_manager.get_collection_manager('serverdata_whitelist')
        return await whitelist_collection.find_one({
            'guild_id': str(guild_id),
            'user_id': str(user_id)
        })

    @app_commands.command(
        name="whitelist",
        description="Look up one member's screening whitelist status and act on it",
    )
    @app_commands.describe(user="The member to look up (User ID or exact username - case sensitive)")
    @app_commands.default_permissions(manage_guild=True)
    @has_whitelist_admin_app()
    @app_commands.guild_only()
    async def whitelist(self, interaction: discord.Interaction, user: str):
        """Resolve one person and show the card for where they stand."""
        guild = interaction.guild

        resolution = await self._resolve_user_identifier(guild, user)

        if not resolution:
            embed = discord.Embed(
                title="❌ User Not Found",
                description=f"Could not find user: `{user}`\n\n"
                            "**Tips:**\n"
                            "• Usernames are case-sensitive\n"
                            "• Use the exact username or user ID\n"
                            "• User ID is more reliable than username",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id, username, in_guild = resolution
        member = guild.get_member(user_id) if in_guild else None

        try:
            entry = await self._fetch_whitelist_entry(guild.id, user_id)
            guild_config = await get_config(guild.id)
        except Exception as e:
            logger.error(f"Error opening the whitelist card: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # A member carries created_at; somebody who is not in the server does
        # not. discord.User.created_at is derived from the snowflake, and
        # snowflake_time is that same derivation without a second API call.
        created_at = member.created_at if member else discord.utils.snowflake_time(user_id)

        card = WhitelistStateCard(
            self,
            author_id=interaction.user.id,
            guild=guild,
            user_id=user_id,
            username=username,
            in_guild=in_guild,
            created_at=created_at,
            entry=entry,
            new_members=guild_config.new_members,
        )

        logger.info(
            f"Whitelist card opened for {username} ({user_id}) by {interaction.user} "
            f"in guild {guild.name}"
        )
        await interaction.response.send_message(view=card, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WhitelistGroup(bot))
