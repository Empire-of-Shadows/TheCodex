"""
Greeting admin-panel node.

Replaces ``/greeting test``, which was an admin-only screen sitting in the
command tree. The panel entry does what the command did - render the configured
greeting for one member and post it - and adds the two things the command was
missing: it says out loud WHERE the greeting is about to be posted, and it
refuses before sending when the greeting could not possibly arrive.

That second part matters. ``GuildEventHandler.send_greeting_message`` logs and
returns when there is no greeting channel, when the saved channel is gone, or
when the send itself fails, so ``/greeting test`` reported "Test Complete" for
sends that never happened. Everything is checked here first instead.

``/greeting info`` is deliberately NOT rebuilt. The New Members group already
carries ``NM_STATUS_NODE`` ("View Status"), which shows the greeting channel,
the account-age requirement, whether greeting messages are on, the whitelist
role and the whitelist counts - a superset of the command's config fields. What
is left of ``/greeting info`` is a list of the greeting commands and a list of
who may run them, neither of which is worth a screen inside a panel that only
those people can already open. A second status node would be a duplicate entry
in the same menu.

The flow subclasses ``PanelFlow`` so the render goes through
``cog._rebind_session_view``: a LayoutView built here and shown directly would
lose the panel's author lock and run on its own 300s timeout instead of the
session's shared idle timer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import discord

from storage.log import get_logger
from storage.settings.config_manager import get_config

from Features.NewMembers.greeting_schema import validate_greeting_schema

from ..permission_checks import check_channel_permissions
from ..setup_notice import setup_notice_text
from ..views.base import AdminLayoutBuilder, editable_container, readonly_container
from ..views.panel_engine import ActionContext, PanelNode
from .panel_flow import PanelFlow

logger = get_logger("GreetingNodes")

NODE_KEY = "nm_greeting_test"
NODE_LABEL = "Send a Test Greeting"

# Only what is strictly required to post at all. The live join greeting does no
# permission check whatsoever, so demanding more here would refuse to test a
# greeting that Discord would in fact deliver - a wrong answer is worse than no
# answer on a screen whose whole job is telling an admin whether this works.
_GREETING_CHANNEL_PERMS = ["view_channel", "send_messages"]


class _GreetingTestFlow(PanelFlow):
    """One admin's walk through sending a test greeting.

    Instantiated per ``on_run``, so the chosen target member lives on the
    instance rather than being threaded through every callback signature.
    """

    node_key = NODE_KEY
    audit_section = "new_members"

    def __init__(self, cog, guild: discord.Guild, ctx: ActionContext, node: PanelNode):
        super().__init__(cog, guild, ctx, node)
        # Who is being greeted. Defaults to whoever opened the screen, matching
        # `/greeting test` with no member argument. Set in open().
        self._target_id: Optional[int] = None
        # Who is reading the screen. Tracked separately from the target, because
        # picking someone else to greet must not change who the setup notices
        # are addressed to. Held as the object the interaction carried, so the
        # default "greet me" case works even on a member-cache miss.
        self._opener: Optional[discord.Member] = None

    # -- entry point --------------------------------------------------------

    async def open(self, interaction: discord.Interaction) -> None:
        self._opener = interaction.user
        self._target_id = interaction.user.id
        await self._render(interaction, await self._build_layout())

    # -- preflight ----------------------------------------------------------

    async def _preflight(self) -> Tuple[Dict[str, Any], Optional[Any], str]:
        """Resolve the greeting setup and report the first blocking problem.

        Returns ``(new_members_config, channel, problem)``. ``problem`` is "" when
        a test greeting would actually land; otherwise it is the text to show
        instead of the Send button. Re-run on every render AND again on the click,
        because an admin can sit on this screen while somebody else changes the
        greeting settings.
        """
        config = await get_config(self.guild.id)
        settings = config.new_members
        channel_id = settings.get("greeting_channel_id")

        if not channel_id:
            return settings, None, await setup_notice_text(
                self.guild,
                what="a greeting channel",
                path="New Members -> Greeting Channel",
                viewer=self._viewer(),
                detail="A test greeting has nowhere to go until one is chosen.",
            )

        channel = self.guild.get_channel(int(channel_id))
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return settings, None, (
                f"The saved greeting channel (`{channel_id}`) is gone, or is not a "
                f"channel the bot can post in.\n\n"
                f"Pick a new one under **New Members -> Greeting Channel**."
            )

        allowed, error = check_channel_permissions(self.node, self.guild, channel.id)
        if not allowed:
            return settings, channel, error or (
                f"The bot cannot post in {channel.mention}."
            )

        components = settings.get("greeting_components")
        if not components:
            return settings, channel, await setup_notice_text(
                self.guild,
                what="a greeting message",
                path="New Members -> Greeting Message Builder",
                viewer=self._viewer(),
                detail="There is no greeting to test yet.",
            )

        valid, message = validate_greeting_schema(components)
        if not valid:
            return settings, channel, (
                f"The greeting layout saved for this server cannot be built:\n"
                f"```{message}```\n"
                f"Fix it under **New Members -> Greeting Message Builder**."
            )

        return settings, channel, ""

    def _viewer(self) -> Optional[discord.Member]:
        """The admin reading this screen.

        ``setup_notice_text`` tailors its closing line to whoever is reading, and
        the reader here always holds panel access, so it resolves to "you can set
        this up yourself" rather than telling an admin to go find an admin.
        """
        return self._opener

    def _target_member(self) -> Optional[discord.Member]:
        """The member the test greeting is rendered for.

        The greeting renderer needs a real Member (display name, avatar, guild),
        so a target who has since left resolves to None and the send is refused
        rather than crashing mid-render.
        """
        if self._target_id is None:
            return None
        member = self.guild.get_member(self._target_id)
        if member is not None:
            return member
        # Default case: the admin greeting themselves. They are demonstrably
        # present - they just clicked - so trust the interaction over the cache.
        if self._opener is not None and getattr(self._opener, "id", None) == self._target_id:
            return self._opener
        return None

    # -- screen -------------------------------------------------------------

    async def _build_layout(self) -> discord.ui.LayoutView:
        settings, channel, problem = await self._preflight()

        builder = AdminLayoutBuilder()
        builder.add_header(f"## {NODE_LABEL}")

        if channel is not None:
            where = (
                f"The test greeting is posted in {channel.mention}, exactly as a new "
                f"member sees it. It is a real message in a real channel - everyone "
                f"who can read {channel.mention} will see it, and its buttons work."
            )
        else:
            where = (
                "A test greeting is posted in this server's greeting channel, exactly "
                "as a new member sees it."
            )
        builder.add_item(readonly_container(discord.ui.TextDisplay(where)))

        if problem:
            builder.add_item(readonly_container(discord.ui.TextDisplay(problem)))
            builder.add_item(self._button_row())
            return builder.build()

        member = self._target_member()
        greeted = member.mention if member is not None else "*nobody selected*"
        on_join = (
            "On" if settings.get("greeting_enabled", True)
            else "Off - real joins are not greeted, but this test still sends"
        )
        builder.add_item(editable_container(
            discord.ui.TextDisplay(
                f"**Posting in:** {channel.mention}\n"
                f"**Greeting:** {greeted}\n"
                f"**Greetings on join:** {on_join}"
            ),
            self._member_select_row(),
        ))
        builder.add_item(self._button_row(with_send=True))
        return builder.build()

    def _member_select_row(self) -> discord.ui.ActionRow:
        select = discord.ui.UserSelect(
            placeholder="Greet someone else in the test...",
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_pick_member
        row = discord.ui.ActionRow()
        row.add_item(select)
        return row

    def _button_row(self, *, with_send: bool = False) -> discord.ui.ActionRow:
        row = discord.ui.ActionRow()
        if with_send:
            send = discord.ui.Button(
                label="Send Test Greeting", style=discord.ButtonStyle.primary
            )
            send.callback = self._on_send
            row.add_item(send)
        back = discord.ui.Button(
            label=self.ctx.back_label or "Back", style=discord.ButtonStyle.secondary
        )
        back.callback = self._on_back
        row.add_item(back)
        return row

    # -- handlers -----------------------------------------------------------

    async def _on_pick_member(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values") or []
        if values:
            try:
                self._target_id = int(values[0])
            except (TypeError, ValueError):
                logger.warning(f"Ignoring an unreadable member id from the panel: {values[0]!r}")
        await self._render(interaction, await self._build_layout())

    async def _on_send(self, interaction: discord.Interaction) -> None:
        """Post the greeting. Rate limited, because this writes to a public channel."""
        if not self._allowed(interaction):
            await self._too_fast(interaction)
            return

        settings, channel, problem = await self._preflight()
        if problem:
            await self._refresh_then_notice(
                interaction, "Nothing was sent", problem, await self._build_layout(),
            )
            return

        member = self._target_member()
        if member is None:
            await self._refresh_then_notice(
                interaction, "Nothing was sent",
                "That member is not in this server any more. Pick someone else.",
                await self._build_layout(),
            )
            return

        try:
            # Imported lazily: the handler owns the gateway client, and the panel
            # tree should not pull that in just to be imported.
            from Features.NewMembers.joining import guild_handler

            await guild_handler.send_greeting_message(member)
        except Exception as exc:
            logger.error(
                f"Test greeting failed for {member} in guild {self.guild.id}: {exc}",
                exc_info=True,
            )
            await self._refresh_then_notice(
                interaction, "The test greeting failed",
                f"Discord refused the message:\n```{str(exc)[:500]}```",
                await self._build_layout(),
            )
            return

        logger.info(
            f"Test greeting sent for {member} ({member.id}) into "
            f"{channel.id} in guild {self.guild.id}"
        )
        await self._refresh_then_notice(
            interaction, "Test greeting sent",
            f"Posted in {channel.mention} for {member.mention}. Anyone who can read "
            f"that channel can see it, so delete it if you do not want it left there.",
            await self._build_layout(),
        )

    async def _on_back(self, interaction: discord.Interaction) -> None:
        await self._back_to_parent(interaction)


def build_greeting_test_node() -> PanelNode:
    """The ``action`` node behind New Members -> Send a Test Greeting.

    A stateless one-shot, so it deliberately supplies no ``get_values`` and no
    ``summary_builder`` and leaves ``counts_as_setting`` unset: it stores nothing,
    it could never read as "configured", and counting it would permanently
    understate the New Members category badge. The engine renders an ``action``
    row as a bare label with no summary, which is what this should look like.

    ``required_channel_perms`` is declared for ``check_channel_permissions``,
    which the flow calls itself - an ``action`` node gets none of the engine's
    automatic permission pre-checks.
    """

    async def _on_run(cog, interaction, guild, ctx: ActionContext) -> None:
        await _GreetingTestFlow(cog, guild, ctx, node).open(interaction)

    node = PanelNode(
        key=NODE_KEY,
        label=NODE_LABEL,
        kind="action",
        description=(
            "Post this server's greeting into the greeting channel to see how it "
            "looks, without waiting for somebody to join."
        ),
        on_run=_on_run,
        required_channel_perms=_GREETING_CHANNEL_PERMS,
    )
    return node
