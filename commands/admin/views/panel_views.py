"""
Admin Panel session + legacy timeout helpers.

The dashboard (Message 1) is built from MAIN_PANEL via `build_overview_view`
in panel_engine.py. This module only carries the shared 5-minute
PanelSession (synced timeout across both messages) and the legacy
`attach_timeout_expiry*` helpers used by bespoke per-feature views that
haven't been ported to the engine yet.

Subcategory routing tables used to live here as PANEL_GROUPS /
PANEL_SUBCATEGORIES. Both were replaced by the MAIN_PANEL PanelNode tree
in commands/admin/panel_configs.py.
"""

import asyncio

import discord

from .base import build_notice_layout, notice_container


# ── Session-expired notice ───────────────────────────────────────────────────

def _build_expired_layout() -> discord.ui.LayoutView:
    """Build the session-expired LayoutView (orange notice container)."""
    expired = discord.ui.LayoutView()
    expired.add_item(notice_container(
        discord.ui.TextDisplay(
            "## Admin Panel — Session Expired\n"
            "This panel timed out after 5 minutes of inactivity.\n"
            "Use `/admin panel` to open a new session."
        ),
    ))
    return expired


# ── PanelSession ─────────────────────────────────────────────────────────────

class PanelSession:
    """Shared 5-minute session bound to all admin-panel messages.

    Any valid interaction on any registered view calls `touch()` and resets
    the timer; on expiry, both msg1 (original interaction) and msg2 (followup
    message) are edited to the "Session Expired" notice layout and their
    views stopped.
    """

    def __init__(self, original_interaction: discord.Interaction, timeout: float = 300.0):
        self.original_interaction = original_interaction
        self.admin_id = original_interaction.user.id
        self.msg2_message: discord.Message | None = None
        self.msg2_view: discord.ui.LayoutView | None = None
        self._timeout = timeout
        self._timer_task: asyncio.Task | None = None

    def register_view(self, view: discord.ui.LayoutView) -> discord.ui.LayoutView:
        """Disable built-in timeout + enforce author lock + touch this session.

        Per ADMIN_PANEL_STANDARD.md §2.2, every registered view rejects
        non-admin interactions with an orange "Access Denied" notice and
        touches the shared 5-minute timer on every valid interaction.
        """
        view.timeout = None
        original_check = getattr(view, 'interaction_check', None)
        session = self

        async def synced_check(interaction: discord.Interaction) -> bool:
            if interaction.user.id != session.admin_id:
                try:
                    await interaction.response.send_message(
                        view=build_notice_layout(
                            "Access Denied",
                            "Only the admin who opened this panel can interact with it.",
                        ),
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
                return False
            session.touch()
            if original_check and callable(original_check):
                return await discord.utils.maybe_coroutine(original_check, interaction)
            return True

        view.interaction_check = synced_check
        return view

    def set_msg2(self, view: discord.ui.LayoutView, message: discord.Message) -> None:
        self.msg2_view = view
        self.msg2_message = message

    def clear_msg2(self) -> None:
        if self.msg2_view:
            self.msg2_view.stop()
        self.msg2_view = None
        self.msg2_message = None

    def touch(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.create_task(self._run_timeout())

    async def _run_timeout(self) -> None:
        try:
            await asyncio.sleep(self._timeout)
        except asyncio.CancelledError:
            return
        await self._expire()

    async def _expire(self) -> None:
        try:
            await self.original_interaction.edit_original_response(view=_build_expired_layout())
        except Exception:
            pass
        if self.msg2_message is not None:
            try:
                await self.msg2_message.edit(view=_build_expired_layout())
            except Exception:
                pass
        if self.msg2_view:
            self.msg2_view.stop()
        self.msg2_view = None
        self.msg2_message = None


# ── Legacy timeout-attach helpers (kept for bespoke per-feature views) ───────

def attach_timeout_expiry(
    view: discord.ui.LayoutView,
    original_interaction: discord.Interaction,
) -> discord.ui.LayoutView:
    """Legacy: prefer PanelSession.register_view instead."""
    async def on_timeout() -> None:
        try:
            await original_interaction.edit_original_response(view=_build_expired_layout())
        except Exception:
            pass

    view.on_timeout = on_timeout
    return view


def attach_timeout_expiry_msg(
    view: discord.ui.LayoutView,
    message,
) -> discord.ui.LayoutView:
    """Legacy: prefer PanelSession.set_msg2 + register_view instead."""
    async def on_timeout() -> None:
        try:
            await message.edit(view=_build_expired_layout())
        except Exception:
            pass

    view.on_timeout = on_timeout
    return view
