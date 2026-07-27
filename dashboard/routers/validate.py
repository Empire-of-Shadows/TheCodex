"""Validation-only endpoints - check JSON without saving."""

import os
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from dashboard.auth.dependencies import get_current_user

# Make project-root feature modules importable.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Features.Guide.guide_schema import (  # noqa: E402
    normalize_pages,
    validate_guide_schema,
)
from Features.NewMembers.greeting_schema import validate_greeting_schema  # noqa: E402
from Features.Board.board_schema import validate_board_schema  # noqa: E402

router = APIRouter(tags=["validate"])


class GuideValidateBody(BaseModel):
    data: dict = Field(..., description="Guide payload to validate")


class GreetingValidateBody(BaseModel):
    data: dict = Field(..., description="Greeting payload to validate")


class BoardValidateBody(BaseModel):
    data: dict = Field(..., description="Board payload to validate")


@router.post("/validate/guide")
async def validate_guide(
    body: GuideValidateBody,
    _: dict = Depends(get_current_user),
):
    """Validate guide JSON and return result."""
    data = normalize_pages(body.data)
    ok, error = validate_guide_schema(data)
    return {"valid": ok, "error": error if not ok else None}


@router.post("/validate/greeting")
async def validate_greeting(
    body: GreetingValidateBody,
    _: dict = Depends(get_current_user),
):
    """Validate greeting JSON and return result."""
    ok, error = validate_greeting_schema(body.data)
    return {"valid": ok, "error": error if not ok else None}


@router.post("/validate/board")
async def validate_board(
    body: BoardValidateBody,
    _: dict = Depends(get_current_user),
):
    """Validate board JSON and return result."""
    ok, error = validate_board_schema(body.data)
    return {"valid": ok, "error": error if not ok else None}
