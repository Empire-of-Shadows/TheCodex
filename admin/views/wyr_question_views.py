"""
Question Bank views - the add-a-question modal and the screens around it.

Pure presentation. Nothing here reads or writes storage; the flow in
``admin/actions/wyr_question_nodes.py`` owns that and hands results in.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

import discord

from Features.daily.wyr_bank import (
    FORMAT_LABELS,
    FORMAT_OPEN,
    FORMAT_OPTION_RANGE,
    FORMAT_POLL,
    FORMAT_WYR,
    question_options,
)
# The entry form lives with the feature, not in the admin seam: an admin adding
# a question and a member submitting one fill in the same thing, and the member
# flow must not have to import from admin/ to ask someone a question.
from Features.daily.wyr_question_form import FORMAT_EMOJI

from .base import AdminLayoutBuilder, readonly_container, editable_container


def build_add_question_view(
    *,
    nsfw: bool,
    enabled_formats: List[str],
    on_pick: Callable[[str], Callable[[discord.Interaction], Awaitable[None]]],
    on_toggle_nsfw: Callable[[discord.Interaction], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """The pick-a-type screen that precedes the add modal.

    Every format is offered, not just the enabled ones - an admin filling a bank
    ahead of turning a type on is a reasonable thing to do. A type the server is
    not posting is labelled as such rather than hidden, and adding one shows the
    one-click offer to turn it on.
    """
    builder = AdminLayoutBuilder()
    builder.add_header("## Add a Question")
    builder.add_item(readonly_container(discord.ui.TextDisplay(
        "Pick the kind of question you want to add. It goes straight into this "
        "server's own bank - nobody else's server will ever post it."
    )))

    lines = []
    for fmt in (FORMAT_WYR, FORMAT_POLL, FORMAT_OPEN):
        low, high = FORMAT_OPTION_RANGE[fmt]
        shape = "no answers" if fmt == FORMAT_OPEN else f"{low} to {high} answers"
        mark = "" if fmt in enabled_formats else "  *(not posted right now)*"
        lines.append(f"{FORMAT_EMOJI[fmt]} **{FORMAT_LABELS[fmt]}** - {shape}{mark}")
    builder.add_item(editable_container(discord.ui.TextDisplay("\n".join(lines))))

    row = discord.ui.ActionRow()
    for fmt in (FORMAT_WYR, FORMAT_POLL, FORMAT_OPEN):
        button = discord.ui.Button(
            label=FORMAT_LABELS[fmt],
            emoji=FORMAT_EMOJI[fmt],
            style=discord.ButtonStyle.primary,
        )
        button.callback = on_pick(fmt)
        row.add_item(button)
    builder.add_item(row)

    controls = discord.ui.ActionRow()
    nsfw_button = discord.ui.Button(
        label=f"Age-restricted: {'On' if nsfw else 'Off'}",
        emoji="🔞",
        style=discord.ButtonStyle.danger if nsfw else discord.ButtonStyle.secondary,
    )
    nsfw_button.callback = on_toggle_nsfw
    controls.add_item(nsfw_button)

    back_button = discord.ui.Button(label=back_label, style=discord.ButtonStyle.secondary)
    back_button.callback = on_back
    controls.add_item(back_button)
    builder.add_item(controls)

    return builder.build()


def build_add_result_view(
    *,
    message: str,
    warning: str,
    offer_format: str | None,
    on_add_another: Callable[[discord.Interaction], Awaitable[None]],
    on_enable_format: Callable[[discord.Interaction], Awaitable[None]] | None,
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """Result screen after adding a question.

    When the question is in a format the server does not post, the warning comes
    with a button that turns that format on. The text alone would not close the
    gap - it is the same "I approved it and nothing happened" dead end that
    started this feature.
    """
    builder = AdminLayoutBuilder()
    builder.add_header("## Add a Question")
    builder.add_item(readonly_container(discord.ui.TextDisplay(message)))
    if warning:
        builder.add_item(editable_container(discord.ui.TextDisplay(warning)))

    row = discord.ui.ActionRow()
    another = discord.ui.Button(label="Add Another", style=discord.ButtonStyle.primary)
    another.callback = on_add_another
    row.add_item(another)

    if warning and offer_format and on_enable_format is not None:
        enable = discord.ui.Button(
            label=f"Turn on {FORMAT_LABELS.get(offer_format, offer_format)}",
            style=discord.ButtonStyle.success,
        )
        enable.callback = on_enable_format
        row.add_item(enable)

    back_button = discord.ui.Button(label=back_label, style=discord.ButtonStyle.secondary)
    back_button.callback = on_back
    row.add_item(back_button)
    builder.add_item(row)

    return builder.build()


def build_review_queue_view(
    *,
    pending: List[Dict[str, Any]],
    index: int,
    guild,
    on_prev: Callable[[discord.Interaction], Awaitable[None]],
    on_next: Callable[[discord.Interaction], Awaitable[None]],
    on_approve: Callable[[discord.Interaction], Awaitable[None]],
    on_decline: Callable[[discord.Interaction], Awaitable[None]],
    on_back: Callable[[discord.Interaction], Awaitable[None]],
    back_label: str = "Back",
) -> discord.ui.LayoutView:
    """One suggestion at a time, with Approve, Decline and paging.

    Shows a single suggestion rather than a list because a decision needs the
    whole question in front of you - the text, every answer, and who sent it.
    """
    builder = AdminLayoutBuilder()
    builder.add_header("## Review Suggestions")

    if not pending:
        builder.add_item(readonly_container(discord.ui.TextDisplay(
            "Nothing is waiting for review.\n\n"
            "Members send suggestions with `/wyr submit` once **Member "
            "Suggestions** is turned on."
        )))
        row = discord.ui.ActionRow()
        back = discord.ui.Button(label=back_label, style=discord.ButtonStyle.secondary)
        back.callback = on_back
        row.add_item(back)
        builder.add_item(row)
        return builder.build()

    index = max(0, min(index, len(pending) - 1))
    submission = pending[index]
    fmt = submission.get("format") or "wyr"

    lines = [
        f"**{index + 1} of {len(pending)}** waiting",
        "",
        f"{FORMAT_EMOJI.get(fmt, '•')} **{FORMAT_LABELS.get(fmt, fmt)}**",
        f"> {submission.get('original', '')}",
    ]
    options = question_options(submission)
    if options:
        # No blank lines around the numbered list - Discord's list block
        # carries its own margins, and explicit blanks stack into double gaps.
        lines.extend(f"{number}. {text}" for number, text in options)
    else:
        lines.append("")
    lines.append(f"Suggested by <@{submission.get('user_id')}>")
    if submission.get("tags"):
        lines.append(f"Tags: {', '.join(submission['tags'])}")
    if submission.get("status") == "reviewing":
        lines.append("\n*Someone else opened this one recently.*")

    builder.add_item(editable_container(discord.ui.TextDisplay("\n".join(lines))))

    decide = discord.ui.ActionRow()
    approve = discord.ui.Button(label="Approve", emoji="✅",
                                style=discord.ButtonStyle.success)
    approve.callback = on_approve
    decide.add_item(approve)

    decline = discord.ui.Button(label="Decline", emoji="❌",
                                style=discord.ButtonStyle.danger)
    decline.callback = on_decline
    decide.add_item(decline)
    builder.add_item(decide)

    nav = discord.ui.ActionRow()
    prev_button = discord.ui.Button(label="Previous",
                                    style=discord.ButtonStyle.secondary,
                                    disabled=index == 0)
    prev_button.callback = on_prev
    nav.add_item(prev_button)

    next_button = discord.ui.Button(label="Next",
                                    style=discord.ButtonStyle.secondary,
                                    disabled=index >= len(pending) - 1)
    next_button.callback = on_next
    nav.add_item(next_button)

    back = discord.ui.Button(label=back_label, style=discord.ButtonStyle.secondary)
    back.callback = on_back
    nav.add_item(back)
    builder.add_item(nav)

    return builder.build()


def format_question_bank_status(overview: Dict[str, Any]) -> str:
    """Markdown body for the question-content part of the WYR status screen."""
    source_labels = {
        "both": "The shared bank plus this server's own questions",
        "guild_only": "Only this server's own questions",
        "global_only": "Only the shared bank",
    }
    formats = overview.get("question_formats") or ["wyr"]
    lines = [
        f"**Question types posted:** "
        f"{', '.join(FORMAT_LABELS.get(f, f) for f in formats)}",
        f"**Questions come from:** "
        f"{source_labels.get(overview.get('question_source'), 'Unknown')}",
        f"**This server's own questions:** {overview.get('bank_total', 0)}",
    ]

    by_format = overview.get("bank_by_format") or {}
    breakdown = [f"{FORMAT_LABELS[fmt]}: {n}" for fmt, n in by_format.items() if n]
    if breakdown:
        lines.append(f"> {' · '.join(breakdown)}")

    unposted = overview.get("unposted") or {}
    if unposted:
        stranded = " and ".join(
            f"{n} {FORMAT_LABELS[fmt].lower()}" for fmt, n in sorted(unposted.items())
        )
        lines.append(
            f"\n⚠️ **{stranded}** in your bank are not being posted, because this "
            f"server does not have that question type turned on."
        )
    return "\n".join(lines)
