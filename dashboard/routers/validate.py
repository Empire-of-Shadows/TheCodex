"""Validation-only endpoints — check JSON without saving."""

import sys
import os

from fastapi import APIRouter, Depends

from dashboard.auth.dependencies import get_current_user

# Add project root to path for validator imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter(tags=["validate"])


@router.post("/validate/guide")
async def validate_guide(body: dict, _: dict = Depends(get_current_user)):
    """Validate guide JSON and return result."""
    from Features.Guide.guide_schema import validate_guide_schema, normalize_pages

    data = body.get("data", body)
    data = normalize_pages(data)
    ok, error = validate_guide_schema(data)
    return {"valid": ok, "error": error if not ok else None}


@router.post("/validate/welcome")
async def validate_welcome(body: dict, _: dict = Depends(get_current_user)):
    """Validate welcome JSON and return result."""
    from Features.NewMembers.welcome_schema import validate_welcome_schema

    data = body.get("data", body)
    ok, error = validate_welcome_schema(data)
    return {"valid": ok, "error": error if not ok else None}
