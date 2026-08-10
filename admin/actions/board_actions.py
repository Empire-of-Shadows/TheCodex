"""
Info Board Actions - business logic for the Info Board admin panel group.

The board layout itself is edited in the dashboard's Board builder; this group
covers the in-Discord half: upload a JSON layout, push it live, and see where it
currently sits.

The channel picker is NOT a ``channel_select`` leaf. Choosing a channel has to be
able to *relocate* a live board (delete the old message, post a new one), and a
``set_values(guild_id, values)`` hook has no guild object to do that with. So the
picker lives inside the publish action instead, where it has the guild in hand.
That is what let the `/board` slash commands be retired.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import discord

from Features.Board.board_publisher import fetch_posted_message, publish
from Features.Board.board_schema import validate_board_schema
from Features.Board.board_store import board_store
from storage.log import get_logger

from ..views.panel_engine import PanelNode, ActionContext
from ..views.base import AdminLayoutBuilder, build_notice_layout, cid, readonly_container
from ..actions.structure import info_action

logger = get_logger("BoardActions")


class BoardActions:
    """Static methods for info board admin panel operations."""

    # ── Board layout JSON ────────────────────────────────────────────────────

    @staticmethod
    async def get_board_json_raw(guild_id: int) -> list:
        """Get the raw board JSON as a list (for the file_upload panel node)."""
        data = await board_store.get_board(guild_id)
        if data:
            return [json.dumps(data, indent=2, ensure_ascii=False)]
        return []

    @staticmethod
    async def set_board_json_from_list(guild_id: int, values: list) -> bool:
        """Upload a board layout. values[0] is the JSON string.

        The engine has already parsed and schema-validated the payload via the
        node's ``schema_validator``; this re-parses the text it hands back.
        """
        if not values:
            return False

        raw = values[0]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid board JSON uploaded for guild {guild_id}: {e}")
            return False

        ok, msg = validate_board_schema(data)
        if not ok:
            logger.warning(f"Board schema validation failed for guild {guild_id}: {msg}")
            return False

        return await board_store.save_board(guild_id, data, updated_by=0)

    @staticmethod
    async def clear_board_json(guild_id: int) -> bool:
        """Delete the guild's board layout.

        Leaves any already-posted message in place: removing a saved layout should
        not silently make a message in a public channel disappear.
        """
        return await board_store.delete_board(guild_id)

    # ── Status ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_status(guild_id: int) -> Dict[str, Any]:
        """Collect board status for the admin panel."""
        doc = await board_store.get_document(guild_id)
        board_data = (doc or {}).get("board_data")

        status: Dict[str, Any] = {
            "has_board": bool(board_data),
            "component_count": 0,
            "response_count": 0,
            "valid": False,
            "error": None,
            "channel_id": (doc or {}).get("channel_id"),
            "message_id": (doc or {}).get("message_id"),
            "updated_at": (doc or {}).get("updated_at"),
            "updated_by": (doc or {}).get("updated_by"),
        }

        if board_data:
            status["component_count"] = len(board_data.get("components", []))
            status["response_count"] = len(board_store.list_responses(board_data))
            valid, msg = validate_board_schema(board_data)
            status["valid"] = valid
            status["error"] = None if valid else msg

        return status


# ─────────────────────────────────────────────────────────────────────────────
# Panel node factories
# ─────────────────────────────────────────────────────────────────────────────

def _back_row(cog, guild, ctx: ActionContext, node_key: str) -> discord.ui.ActionRow:
    """A Back button returning to the parent menu (mirrors the vendored factories)."""

    async def _back(ci: discord.Interaction):
        if ctx.parent_node is not None:
            await cog._navigate_to(
                ci, ctx.parent_node, guild, parent_node=ctx.grandparent_node,
                edit=True, refresh_parent=ctx.refresh_parent, session=ctx.session,
            )
        else:
            await ci.response.edit_message(
                view=AdminLayoutBuilder().add_text("Closed.").build()
            )

    back_btn = discord.ui.Button(
        label=ctx.back_label or "Back",
        style=discord.ButtonStyle.secondary,
        custom_id=cid("board", "back", node_key),
    )
    back_btn.callback = _back
    row = discord.ui.ActionRow()
    row.add_item(back_btn)
    return row


def build_board_publish_node() -> PanelNode:
    """An ``action`` node that pushes the saved layout live.

    Two jobs on one screen: the button refreshes the board where it already
    lives, and the channel picker puts it up for the first time or moves it.
    The picker is what let ``/board post``, ``/board refresh`` and ``/board info``
    be retired - all three were doing what this screen and the status node
    already do, at the cost of a whole top-level entry in everyone's command list.
    """

    async def _on_run(cog, interaction, guild, ctx: ActionContext):
        doc = await board_store.get_document(guild.id)
        existing = await fetch_posted_message(guild, doc)

        builder = AdminLayoutBuilder()
        builder.add_header("## Post / Update Board")
        if existing is not None:
            where = (
                f"The board is live in {existing.channel.mention}.\n"
                f"**Post / Update** pushes the saved layout to it. Picking a "
                f"different channel below moves it there, removing the old copy."
            )
        else:
            where = (
                "The board is not posted anywhere yet.\n"
                "Pick a channel below to put it up."
            )
        builder.add_item(readonly_container(discord.ui.TextDisplay(where)))

        async def _publish_to(bi: discord.Interaction, channel) -> None:
            """Shared publish path for the button and the channel picker."""
            if not cog._check_cooldown(bi.user.id, "board_publish", guild.id):
                await bi.response.send_message(
                    view=build_notice_layout(
                        "Slow Down", "Please wait a moment before trying again."
                    ),
                    ephemeral=True,
                )
                return

            await bi.response.defer(ephemeral=True)
            result = await publish(guild, channel)

            if not result.ok:
                await bi.followup.send(
                    view=build_notice_layout("Board not published", result.error),
                    ephemeral=True,
                )
                return

            logger.info(
                f"Board {result.action} from the admin panel by {bi.user} "
                f"({bi.user.id}) in guild {guild.id}"
            )
            summary = result.summary
            if result.message is not None:
                summary += f"\n[Jump to it]({result.message.jump_url})"
            await bi.followup.send(
                view=build_notice_layout(f"Board {result.action}", summary),
                ephemeral=True,
            )

        async def _run(bi: discord.Interaction):
            # No channel: refresh wherever the board already lives.
            await _publish_to(bi, None)

        async def _on_pick_channel(bi: discord.Interaction):
            picked = bi.data.get("values") or []
            channel = guild.get_channel(int(picked[0])) if picked else None
            if channel is None:
                await bi.response.send_message(
                    view=build_notice_layout(
                        "Channel not found", "Pick a channel I can still see."
                    ),
                    ephemeral=True,
                )
                return
            await _publish_to(bi, channel)

        if existing is not None:
            run_btn = discord.ui.Button(
                label="Post / Update Board",
                style=discord.ButtonStyle.success,
                custom_id=cid("board", "publish", "board_publish"),
            )
            run_btn.callback = _run
            row = discord.ui.ActionRow()
            row.add_item(run_btn)
            builder.add_item(row)

        picker = discord.ui.ChannelSelect(
            placeholder=("Move the board to..." if existing is not None
                         else "Post the board in..."),
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
            custom_id=cid("board", "publish_channel", "board_publish"),
        )
        picker.callback = _on_pick_channel
        builder.add_item(discord.ui.ActionRow(picker))

        builder.add_item(_back_row(cog, guild, ctx, "board_publish"))

        # Bound to the panel session so the screen keeps the author lock and the
        # session's shared idle timer rather than running on its own timeout.
        await cog._send_or_edit(
            interaction, cog._rebind_session_view(ctx.session, builder.build()), ctx.edit
        )

    return PanelNode(
        key="board_publish",
        label="Post / Update Board",
        kind="action",
        description="Push the saved board layout live, or choose which channel it lives in.",
        on_run=_on_run,
    )


def build_board_status_node() -> PanelNode:
    """A read-only ``action`` node showing board status (via the shared info_action)."""

    async def _render(cog, guild, ctx) -> str:
        status = await BoardActions.get_status(guild.id)

        if not status["has_board"]:
            return (
                "**No board configured.**\n\n"
                "Build one in the dashboard's Board builder, or upload a JSON layout "
                "with **Board Builder** above."
            )

        lines = [
            f"**Blocks:** {status['component_count']}",
            f"**Private responses:** {status['response_count']}",
        ]

        if status["valid"]:
            lines.append("**Layout:** valid")
        else:
            lines.append(f"**Layout:** invalid - {status['error']}")

        doc = await board_store.get_document(guild.id)
        message = await fetch_posted_message(guild, doc)
        if message is not None:
            lines.append(f"**Posted in:** {message.channel.mention} - [jump]({message.jump_url})")
        elif status["message_id"]:
            lines.append(
                "**Posted:** the stored message is gone - use **Post / Update Board** "
                "to put it back."
            )
        else:
            lines.append(
                "**Posted:** not yet - pick a channel under **Post / Update Board**."
            )

        if status["updated_at"]:
            lines.append(f"**Layout last saved:** <t:{int(status['updated_at'].timestamp())}:R>")

        return "\n".join(lines)

    return info_action(
        "board_status",
        label="View Status",
        render=_render,
        description="Board layout and where it is posted.",
    )
