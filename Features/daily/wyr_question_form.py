"""
The question entry form, shared by everyone who writes a question.

An admin adding one from the panel and a member submitting one for review are
filling in the same thing, so they fill in the same form. Keeping one modal
means the two cannot drift into accepting different shapes, and a member never
meets a form that behaves unlike the one their moderator sees.

Lives under ``Features/daily`` rather than ``admin/views`` because the member
flow must not have to import from the admin seam to ask someone a question.
"""

from __future__ import annotations

from typing import Awaitable, Callable, List

import discord

from Features.daily.wyr_bank import (
    FORMAT_LABELS,
    FORMAT_OPEN,
    FORMAT_OPTION_RANGE,
    FORMAT_POLL,
    FORMAT_WYR,
    MAX_OPTION_LENGTH,
    MAX_QUESTION_LENGTH,
)

#: Emoji per format, used anywhere a format is named to a human.
FORMAT_EMOJI = {FORMAT_WYR: "🎲", FORMAT_POLL: "📊", FORMAT_OPEN: "💬"}

_PLACEHOLDERS = {
    FORMAT_WYR: "Would you rather be able to fly or be invisible?",
    FORMAT_POLL: "Which season is the best one?",
    FORMAT_OPEN: "What is a hill you are willing to die on?",
}

_OPTION_PLACEHOLDERS = {
    FORMAT_WYR: "Be able to fly\nBe invisible",
    FORMAT_POLL: "Spring\nSummer\nAutumn\nWinter",
}


class QuestionFormModal(discord.ui.Modal):
    """Write one question.

    Answers are one field with a line each rather than one field per answer.
    Discord allows five components in a modal, and a five-answer question plus
    its text plus tags would not fit - and the line-per-answer shape is the same
    for every format, so there is only one thing to learn.

    The callback receives ``(interaction, text, options, tags)`` and owns
    validation; nothing here decides whether a question is acceptable.
    """

    def __init__(
        self,
        question_format: str,
        callback: Callable[[discord.Interaction, str, List[str], List[str]], Awaitable[None]],
        *,
        title: str | None = None,
    ):
        label = FORMAT_LABELS.get(question_format, "Question")
        super().__init__(title=(title or f"Add a {label}")[:45])
        self.question_format = question_format
        self._callback = callback

        self.question_input = discord.ui.TextInput(
            label="Question",
            placeholder=_PLACEHOLDERS.get(question_format, ""),
            required=True,
            max_length=MAX_QUESTION_LENGTH,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.question_input)

        # An open-ended question has no answers, so it is not asked for any.
        self.options_input = None
        if question_format != FORMAT_OPEN:
            low, high = FORMAT_OPTION_RANGE[question_format]
            self.options_input = discord.ui.TextInput(
                label=f"Answers, one per line ({low} to {high})",
                placeholder=_OPTION_PLACEHOLDERS.get(question_format, ""),
                required=True,
                max_length=(MAX_OPTION_LENGTH + 1) * high,
                style=discord.TextStyle.paragraph,
            )
            self.add_item(self.options_input)

        self.tags_input = discord.ui.TextInput(
            label="Tags (optional, comma separated)",
            placeholder="casual, deep",
            required=False,
            max_length=200,
        )
        self.add_item(self.tags_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        options: List[str] = []
        if self.options_input is not None:
            options = [
                line.strip()
                for line in self.options_input.value.splitlines()
                if line.strip()
            ]
        tags = [t.strip() for t in (self.tags_input.value or "").split(",") if t.strip()]
        await self._callback(
            interaction, self.question_input.value.strip(), options, tags
        )
