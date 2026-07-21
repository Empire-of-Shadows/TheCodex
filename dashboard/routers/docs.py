"""Docs API - serves builder documentation markdown files."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["docs"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILDER_DIRS = {
    "guide": _PROJECT_ROOT / "markdownfiles" / "guide-builder",
    "welcome": _PROJECT_ROOT / "markdownfiles" / "welcome-builder",
}
_TOPIC_FILES = {
    "getting-started": "README.md",
    "schema": "schema.md",
    "placeholders": "placeholders.md",
    "examples": "examples.md",
}
_TOPIC_TITLES = {
    "getting-started": "Getting Started",
    "schema": "Schema Reference",
    "placeholders": "Placeholders",
    "examples": "Examples",
}


@router.get("/docs/{builder}/{topic}")
async def get_docs(builder: str, topic: str):
    """Return raw markdown content for a builder documentation topic."""
    if builder not in _BUILDER_DIRS:
        raise HTTPException(status_code=404, detail=f"Unknown builder: {builder}")
    if topic not in _TOPIC_FILES:
        raise HTTPException(status_code=404, detail=f"Unknown topic: {topic}")

    file_path = _BUILDER_DIRS[builder] / _TOPIC_FILES[topic]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Documentation file not found")

    content = file_path.read_text(encoding="utf-8")
    return {"title": _TOPIC_TITLES[topic], "content": content}
