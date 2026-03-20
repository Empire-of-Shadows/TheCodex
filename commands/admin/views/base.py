"""
Base utilities for Admin Panel Components v2 views.

Provides shared builders and utilities for creating consistent LayoutView layouts.
"""

import time
import discord
from typing import Optional, Callable, Awaitable

from utils.logger import get_logger

logger = get_logger("AdminViews")


def create_unique_id() -> int:
    """Generate a unique ID using microsecond timestamp."""
    return int(time.time() * 1000000)


def build_header(title: str, description: Optional[str] = None) -> list[discord.ui.Item]:
    """
    Build a standard header section with title and optional description.

    Args:
        title: Header title (supports markdown like ## for h2)
        description: Optional description text below title

    Returns:
        List of items to add to LayoutView
    """
    items = [discord.ui.TextDisplay(title)]
    if description:
        items.append(discord.ui.TextDisplay(description))
    return items


def build_status_display(status: str) -> discord.ui.TextDisplay:
    """Build a status message display."""
    return discord.ui.TextDisplay(status)


def build_config_display(config_lines: list[str], header: str = "**Current Configuration:**") -> discord.ui.TextDisplay:
    """Build a configuration list display."""
    content = header + "\n" + "\n".join(config_lines)
    return discord.ui.TextDisplay(content)


def build_action_buttons(
    save_callback: Callable[[discord.Interaction], Awaitable[None]],
    cancel_callback: Callable[[discord.Interaction], Awaitable[None]],
    save_label: str = "Save",
    cancel_label: str = "Cancel",
    save_style: discord.ButtonStyle = discord.ButtonStyle.green,
    cancel_style: discord.ButtonStyle = discord.ButtonStyle.secondary
) -> discord.ui.ActionRow:
    """Build standard Save/Cancel action buttons in an ActionRow."""
    unique_id = create_unique_id()

    save_btn = discord.ui.Button(
        label=save_label,
        style=save_style,
        custom_id=f"save_{unique_id}"
    )
    save_btn.callback = save_callback

    cancel_btn = discord.ui.Button(
        label=cancel_label,
        style=cancel_style,
        custom_id=f"cancel_{unique_id}"
    )
    cancel_btn.callback = cancel_callback

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(save_btn)
    btn_row.add_item(cancel_btn)

    return btn_row


def build_confirmation_buttons(
    confirm_callback: Callable[[discord.Interaction], Awaitable[None]],
    cancel_callback: Callable[[discord.Interaction], Awaitable[None]],
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    confirm_style: discord.ButtonStyle = discord.ButtonStyle.danger
) -> discord.ui.ActionRow:
    """Build confirmation buttons for destructive actions."""
    return build_action_buttons(
        save_callback=confirm_callback,
        cancel_callback=cancel_callback,
        save_label=confirm_label,
        cancel_label=cancel_label,
        save_style=confirm_style,
        cancel_style=discord.ButtonStyle.secondary
    )


def build_back_button(
    callback: Callable[[discord.Interaction], Awaitable[None]],
    label: str = "Back"
) -> discord.ui.ActionRow:
    """Build a back navigation button."""
    unique_id = create_unique_id()

    back_btn = discord.ui.Button(
        label=label,
        style=discord.ButtonStyle.secondary,
        custom_id=f"back_{unique_id}"
    )
    back_btn.callback = callback

    btn_row = discord.ui.ActionRow()
    btn_row.add_item(back_btn)

    return btn_row


def build_select_row(select: discord.ui.Select) -> discord.ui.ActionRow:
    """Wrap a Select component in an ActionRow."""
    row = discord.ui.ActionRow()
    row.add_item(select)
    return row


def create_empty_layout(message: str = "Operation cancelled.") -> discord.ui.LayoutView:
    """Create an empty layout with a simple message."""
    layout = discord.ui.LayoutView()
    layout.add_item(discord.ui.TextDisplay(message))
    return layout


def create_error_layout(error_message: str) -> discord.ui.LayoutView:
    """Create a layout for displaying errors."""
    layout = discord.ui.LayoutView()
    layout.add_item(discord.ui.TextDisplay("## Error"))
    layout.add_item(discord.ui.TextDisplay(error_message))
    return layout


def create_success_layout(title: str, message: str) -> discord.ui.LayoutView:
    """Create a layout for displaying success messages."""
    layout = discord.ui.LayoutView()
    layout.add_item(discord.ui.TextDisplay(f"## {title}"))
    layout.add_item(discord.ui.TextDisplay(message))
    return layout


class AdminLayoutBuilder:
    """
    Helper class for building admin panel layouts with consistent styling.

    Usage:
        builder = AdminLayoutBuilder(timeout=300.0)
        builder.add_header("## Panel Title", "Description here")
        builder.add_separator()
        builder.add_content("Some content")
        builder.add_action_buttons(save_callback, cancel_callback)
        layout = builder.build()
    """

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self.items: list[discord.ui.Item] = []

    def add_header(self, title: str, description: Optional[str] = None) -> 'AdminLayoutBuilder':
        """Add a header section."""
        self.items.extend(build_header(title, description))
        return self

    def add_separator(self) -> 'AdminLayoutBuilder':
        """Add a visual separator."""
        self.items.append(discord.ui.Separator())
        return self

    def add_text(self, text: str) -> 'AdminLayoutBuilder':
        """Add a text display."""
        self.items.append(discord.ui.TextDisplay(text))
        return self

    def add_status(self, status: str) -> 'AdminLayoutBuilder':
        """Add a status display."""
        self.items.append(build_status_display(status))
        return self

    def add_config_display(self, config_lines: list[str], header: str = "**Current Configuration:**") -> 'AdminLayoutBuilder':
        """Add a configuration display."""
        self.items.append(build_config_display(config_lines, header))
        return self

    def add_select(self, select: discord.ui.Select) -> 'AdminLayoutBuilder':
        """Add a select component in an ActionRow."""
        self.items.append(build_select_row(select))
        return self

    def add_action_buttons(
        self,
        save_callback: Callable[[discord.Interaction], Awaitable[None]],
        cancel_callback: Callable[[discord.Interaction], Awaitable[None]],
        save_label: str = "Save",
        cancel_label: str = "Cancel"
    ) -> 'AdminLayoutBuilder':
        """Add save/cancel action buttons."""
        self.items.append(build_action_buttons(
            save_callback, cancel_callback, save_label, cancel_label
        ))
        return self

    def add_confirmation_buttons(
        self,
        confirm_callback: Callable[[discord.Interaction], Awaitable[None]],
        cancel_callback: Callable[[discord.Interaction], Awaitable[None]],
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel"
    ) -> 'AdminLayoutBuilder':
        """Add confirmation buttons."""
        self.items.append(build_confirmation_buttons(
            confirm_callback, cancel_callback, confirm_label, cancel_label
        ))
        return self

    def add_item(self, item: discord.ui.Item) -> 'AdminLayoutBuilder':
        """Add any UI item directly."""
        self.items.append(item)
        return self

    def add_action_row(self, *items: discord.ui.Item) -> 'AdminLayoutBuilder':
        """Add items wrapped in an ActionRow."""
        row = discord.ui.ActionRow()
        for item in items:
            row.add_item(item)
        self.items.append(row)
        return self

    def build(self) -> discord.ui.LayoutView:
        """Build and return the LayoutView."""
        layout = discord.ui.LayoutView(timeout=self.timeout)
        for item in self.items:
            layout.add_item(item)
        return layout
