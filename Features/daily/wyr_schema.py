"""
Daily question import schema.

Validates the JSON file an admin uploads to fill their server's question bank in
one go. All validation is synchronous and returns the first error, in language
an admin can act on.

The accepted file is either a bare list of questions or an object with a
``questions`` list::

    [
      {"question": "Would you rather fly or be invisible?",
       "options": ["Fly", "Be invisible"]},
      {"question": "What is the best season?",
       "options": ["Spring", "Summer", "Autumn", "Winter"], "tags": ["casual"]},
      {"question": "What is a hill you will die on?"}
    ]

``format`` is optional. When it is missing it is inferred, which is what makes a
two-hundred-question file writable by hand:

  * no options                          -> ``open``
  * text starting "would you rather"    -> ``wyr``
  * anything else with options          -> ``poll``

Per-question validation (lengths, option counts, duplicate options, tags) is
delegated to :func:`Features.daily.wyr_bank.validate_question`, so an imported
question and one typed into the panel are held to exactly the same rules.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from Features.daily.wyr_bank import (
    FORMAT_OPEN,
    FORMAT_POLL,
    FORMAT_WYR,
    FORMATS,
    MAX_OPTIONS,
    validate_question,
)
from utils.safe_content import check_no_dangerous_content

# Hard ceiling on the uploaded payload. The per-question limits already bound a
# well-formed file; this stops a caller smuggling megabytes through a field we
# do not read.
_MAX_IMPORT_BYTES = 512 * 1024

#: Questions per file. High enough to seed a bank in one upload, low enough that
#: the insert stays a single bulk write and the summary stays readable.
MAX_IMPORT_QUESTIONS = 500

_ALLOWED_TOP_LEVEL = {"questions"}
_ALLOWED_ITEM_KEYS = (
    {"format", "question", "original", "options", "nsfw", "tags"}
    | {f"option_{n}" for n in range(1, MAX_OPTIONS + 1)}
)

_WYR_PREFIX = "would you rather"


def _extract_items(data: Any) -> Tuple[bool, List[Any], str]:
    """Unwrap the two accepted top-level shapes into a list of questions."""
    if isinstance(data, list):
        return True, data, ""
    if isinstance(data, dict):
        unknown = set(data) - _ALLOWED_TOP_LEVEL
        if unknown:
            return False, [], (
                f"Unknown field(s) at the top of the file: {', '.join(sorted(unknown))}. "
                f"Expected a list of questions, or an object with a \"questions\" list."
            )
        items = data.get("questions")
        if not isinstance(items, list):
            return False, [], "\"questions\" must be a list."
        return True, items, ""
    return False, [], (
        "The file must contain a list of questions, or an object with a "
        "\"questions\" list."
    )


def _item_options(item: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    """Read a question's options from either an ``options`` list or ``option_N`` keys."""
    if "options" in item:
        raw = item["options"]
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            return False, [], "\"options\" must be a list."
        numbered = [k for k in item if k.startswith("option_")]
        if numbered:
            return False, [], (
                "Use either \"options\" or \"option_1\"/\"option_2\", not both."
            )
        return True, [str(o) for o in raw], ""

    options: List[str] = []
    for n in range(1, MAX_OPTIONS + 1):
        value = item.get(f"option_{n}")
        if value is None:
            continue
        # A gap (option_1 and option_3 with no option_2) means the file is not
        # saying what the author thinks it is saying.
        if len(options) != n - 1:
            return False, [], f"\"option_{n}\" is set but an earlier option is missing."
        options.append(str(value))
    return True, options, ""


def infer_format(text: str, options: List[str]) -> str:
    """Guess a question's format from its shape. Explicit ``format`` always wins."""
    if not options:
        return FORMAT_OPEN
    if str(text or "").strip().lower().startswith(_WYR_PREFIX):
        return FORMAT_WYR
    return FORMAT_POLL


def parse_wyr_import(text: str) -> Tuple[bool, List[Dict[str, Any]], List[bool], str]:
    """Parse and fully validate an uploaded file.

    Returns ``(ok, cleaned_items, nsfw_flags, error)``. ``cleaned_items`` are
    ready to hand to :meth:`WYRBank.insert_many_questions`; ``nsfw_flags`` lines
    up with it index for index.

    This is the single parse. The engine's ``schema_validator`` hook and the
    node's ``set_values`` both route through here, so the file that validated is
    exactly the file that gets inserted.
    """
    # The byte ceiling lives here rather than only in the panel hook, so every
    # caller is bounded before any parsing work happens.
    if len(text or "") > _MAX_IMPORT_BYTES:
        return False, [], [], (
            f"That file is too large ({len(text)} characters; the limit is "
            f"{_MAX_IMPORT_BYTES}). Split it into smaller files."
        )

    try:
        data = json.loads(text)
    except (TypeError, ValueError) as e:
        return False, [], [], f"That file is not valid JSON ({e})."

    ok, msg = check_no_dangerous_content(data, "file")
    if not ok:
        return False, [], [], msg

    ok, items, error = _extract_items(data)
    if not ok:
        return False, [], [], error

    if not items:
        return False, [], [], "The file does not contain any questions."
    if len(items) > MAX_IMPORT_QUESTIONS:
        return False, [], [], (
            f"That file holds {len(items)} questions - the limit is "
            f"{MAX_IMPORT_QUESTIONS} per upload. Split it into smaller files."
        )

    cleaned_items: List[Dict[str, Any]] = []
    nsfw_flags: List[bool] = []

    for index, item in enumerate(items):
        # Humans count from 1, and this number is the whole value of the error.
        where = f"Question {index + 1}"

        if not isinstance(item, dict):
            return False, [], [], f"{where} is not a JSON object."

        unknown = set(item) - _ALLOWED_ITEM_KEYS
        if unknown:
            return False, [], [], (
                f"{where} has unknown field(s): {', '.join(sorted(unknown))}."
            )

        if "question" in item and "original" in item:
            return False, [], [], f"{where} sets both \"question\" and \"original\"."
        question_text = item.get("question", item.get("original"))
        if question_text is None:
            return False, [], [], f"{where} is missing its \"question\" text."
        if not isinstance(question_text, str):
            return False, [], [], f"{where}: \"question\" must be text."

        ok, options, error = _item_options(item)
        if not ok:
            return False, [], [], f"{where}: {error}"

        question_format = item.get("format")
        if question_format is None:
            question_format = infer_format(question_text, options)
        elif not isinstance(question_format, str) or question_format.lower() not in FORMATS:
            return False, [], [], (
                f"{where}: \"format\" must be one of {', '.join(FORMATS)}."
            )
        else:
            question_format = question_format.lower()

        tags = item.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            return False, [], [], f"{where}: \"tags\" must be a list."

        nsfw = item.get("nsfw", False)
        if not isinstance(nsfw, bool):
            return False, [], [], f"{where}: \"nsfw\" must be true or false."

        ok, cleaned, error = validate_question(question_format, question_text, options, tags)
        if not ok:
            return False, [], [], f"{where}: {error}"

        cleaned_items.append(cleaned)
        nsfw_flags.append(nsfw)

    return True, cleaned_items, nsfw_flags, ""


def validate_wyr_import_schema(data: Any) -> Tuple[bool, str]:
    """Panel ``schema_validator`` hook - runs against the PARSED payload.

    The engine has already parsed the JSON by the time this is called, so the
    check is re-serialized and routed through :func:`parse_wyr_import` to keep
    one implementation of the rules.
    """
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        return False, "That file is not JSON-serializable."

    ok, _items, _flags, error = parse_wyr_import(text)
    return ok, error


def build_import_template() -> Tuple[bytes, str]:
    """The starter file behind the panel's Download Template button.

    Shows one question of each format, so an admin can see the shape rather
    than read a spec.
    """
    sample = {
        "questions": [
            {
                "question": "Would you rather be able to fly or be invisible?",
                "options": ["Fly", "Be invisible"],
                "tags": ["classic"],
            },
            {
                "question": "Which season is the best one?",
                "options": ["Spring", "Summer", "Autumn", "Winter"],
                "format": "poll",
            },
            {
                "question": "What is a hill you are willing to die on?",
                "format": "open",
            },
        ]
    }
    text = json.dumps(sample, indent=2, ensure_ascii=False)
    return text.encode("utf-8"), "question-bank-template.json"
