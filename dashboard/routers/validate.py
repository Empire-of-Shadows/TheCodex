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
from Features.NewMembers.welcome_schema import validate_welcome_schema  # noqa: E402

router = APIRouter(tags=["validate"])


class GuideValidateBody(BaseModel):
    data: dict = Field(..., description="Guide payload to validate")


class WelcomeValidateBody(BaseModel):
    data: dict = Field(..., description="Welcome payload to validate")


@router.post("/validate/guide")
async def validate_guide(
    body: GuideValidateBody,
    _: dict = Depends(get_current_user),
):
    """Validate guide JSON and return result."""
    data = normalize_pages(body.data)
    ok, error = validate_guide_schema(data)
    return {"valid": ok, "error": error if not ok else None}


@router.post("/validate/welcome")
async def validate_welcome(
    body: WelcomeValidateBody,
    _: dict = Depends(get_current_user),
):
    """Validate welcome JSON and return result."""
    ok, error = validate_welcome_schema(body.data)
    return {"valid": ok, "error": error if not ok else None}
