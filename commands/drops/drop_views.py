"""
Drop Panel Views using Discord Components v2.

View builders for the /drop command panel:
- Browse sent drops (paginated)
- Manager-only: unsent drops view, test button
"""

from datetime import datetime
from typing import Any, Callable, Awaitable, Dict, List

import discord

from admin.views.base import create_unique_id, AdminLayoutBuilder, build_notice_layout

DROPS_PER_PAGE = 5


def attach_timeout_expiry_msg(
    view: discord.ui.LayoutView,
    message: discord.Message,
) -> discord.ui.LayoutView:
    """When ``view`` times out, edit ``message`` to show a session-expired notice.

    The drops panel is a bespoke per-feature view, not part of the PanelNode admin
    panel, so it manages its own timeout expiry rather than using ``PanelSession``.
    Replaces the admin engine's removed legacy helper of the same name.
    """

    async def on_timeout() -> None:
        try:
            await message.edit(view=build_notice_layout(
                "Drops Panel - Session Expired",
                "This panel timed out after 5 minutes of inactivity.\n"
                "Use `/drop` to open a new one.",
            ))
        except Exception:
            pass  # Message may have been deleted or the interaction expired.

    view.on_timeout = on_timeout
    return view


def _format_drop_entry(drop: Dict[str, Any]) -> str:
    """Format a single drop as a text block."""
    label = drop.get("label", "Unknown Game")
    description = drop.get("description", "No description")
    if len(description) > 100:
        description = description[:97] + "..."

    expires = drop.get("expires", "Unknown")
    if isinstance(expires, datetime):
        expires = expires.strftime("%Y-%m-%d")

    short_href = drop.get("short_href")
    link = f"[Claim]({short_href})" if short_href else "No link"

    return f"**{label}**\n{description} | Expires: {expires} | {link}"


def build_drops_browse_view(
    drops: List[Dict[str, Any]],
    page: int,
    total_pages: int,
    is_manager: bool,
    on_prev: Callable[[discord.Interaction], Awaitable[None]],
    on_next: Callable[[discord.Interaction], Awaitable[None]],
    on_test: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    on_unsent: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    setup_hint: str = "",
) -> discord.ui.LayoutView:
    """Build the main browse panel with paginated sent drops.

    ``setup_hint`` is shown in place of the bare empty state when the server has
    no drops channel yet, so "nothing here" reads as "not switched on" rather
    than "nothing was released".
    """
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header("## Prime Gaming Drops")

    if not drops:
        builder.add_text(setup_hint or "No sent drops found.")
    else:
        entries = []
        for drop in drops:
            entries.append(_format_drop_entry(drop))
        builder.add_text("\n\n".join(entries))

        builder.add_separator()
        builder.add_text(f"Page {page + 1} / {total_pages}")

    # Navigation buttons
    nav_row = discord.ui.ActionRow()

    prev_btn = discord.ui.Button(
        label="Prev",
        style=discord.ButtonStyle.secondary,
        custom_id=f"drop_prev_{unique_id}",
        disabled=(page <= 0),
    )
    prev_btn.callback = on_prev
    nav_row.add_item(prev_btn)

    next_btn = discord.ui.Button(
        label="Next",
        style=discord.ButtonStyle.secondary,
        custom_id=f"drop_next_{unique_id}",
        disabled=(page >= total_pages - 1),
    )
    next_btn.callback = on_next
    nav_row.add_item(next_btn)

    # Manager-only buttons in the same row
    if is_manager:
        if on_test:
            test_btn = discord.ui.Button(
                label="Test Drops",
                style=discord.ButtonStyle.danger,
                custom_id=f"drop_test_{unique_id}",
            )
            test_btn.callback = on_test
            nav_row.add_item(test_btn)

        if on_unsent:
            unsent_btn = discord.ui.Button(
                label="View Unsent",
                style=discord.ButtonStyle.primary,
                custom_id=f"drop_unsent_{unique_id}",
            )
            unsent_btn.callback = on_unsent
            nav_row.add_item(unsent_btn)

    builder.add_item(nav_row)

    return builder.build()


def build_unsent_drops_view(
    drops: List[Dict[str, Any]],
    page: int,
    total_pages: int,
    on_prev: Callable[[discord.Interaction], Awaitable[None]],
    on_next: Callable[[discord.Interaction], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
) -> discord.ui.LayoutView:
    """Build the unsent drops list with Back button to return to browse."""
    unique_id = create_unique_id()
    builder = AdminLayoutBuilder()

    builder.add_header("## Unsent Prime Gaming Drops")

    if not drops:
        builder.add_text("No unsent drops found.")
    else:
        entries = []
        for drop in drops:
            entries.append(_format_drop_entry(drop))
        builder.add_text("\n\n".join(entries))

        builder.add_separator()
        builder.add_text(f"Page {page + 1} / {total_pages}")

    nav_row = discord.ui.ActionRow()

    prev_btn = discord.ui.Button(
        label="Prev",
        style=discord.ButtonStyle.secondary,
        custom_id=f"unsent_prev_{unique_id}",
        disabled=(page <= 0),
    )
    prev_btn.callback = on_prev
    nav_row.add_item(prev_btn)

    next_btn = discord.ui.Button(
        label="Next",
        style=discord.ButtonStyle.secondary,
        custom_id=f"unsent_next_{unique_id}",
        disabled=(page >= total_pages - 1),
    )
    next_btn.callback = on_next
    nav_row.add_item(next_btn)

    back_btn = discord.ui.Button(
        label="Back",
        style=discord.ButtonStyle.secondary,
        custom_id=f"unsent_back_{unique_id}",
    )
    back_btn.callback = on_back
    nav_row.add_item(back_btn)

    builder.add_item(nav_row)

    return builder.build()
