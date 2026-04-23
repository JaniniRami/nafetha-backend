"""Ollama-backed keyword extraction for community events from title + description."""

from __future__ import annotations

from typing import Any

from app.company_display_ai import parse_display_ai_model_json
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_TITLE_CHARS = 255
_MAX_DESCRIPTION_CHARS = 4000

_SYSTEM_INSTRUCTION = """You are a keyword extractor for a student internship and career platform.

You will receive an event title and description. Output JSON only, no explanation.

Return format (STRICT, exactly two fields, nothing else):
{"success": true|false, "keywords": ["k1","k2","k3","k4","k5"]}

RULES:
- Output ONLY {"success": ..., "keywords": [...]}. No other fields.
- If input is empty, gibberish, or not a real event: {"success": false, "keywords": []}
- If success=true, return exactly 5 keywords.
- Keywords must be lowercase, singular form (e.g. "engineer" not "engineers").
- Keywords must reflect the technical field, required skill, job role, or academic discipline — the kind of words a student would use to describe their own background and interests.
- Do NOT generate descriptive or narrative keywords like "opportunity", "growth", "community", "jordan", "event", "session".
- Do NOT use full sentences or long phrases.
- Input may be in Arabic or English. Always output keywords in English regardless.

Examples:
Input: "AI Career Night — meet companies hiring for ML and data roles" -> {"success": true, "keywords": ["machine learning", "data science", "computer vision", "python", "software engineer"]}
Input: "Embedded Systems Workshop for EE students" -> {"success": true, "keywords": ["embedded systems", "electrical engineering", "c programming", "microcontroller", "firmware"]}
Input: "Frontend Bootcamp — React and UI design" -> {"success": true, "keywords": ["frontend", "react", "javascript", "ui design", "web development"]}
Input: "asdfgh" -> {"success": false, "keywords": []}"""


def _coerce_event_keywords_payload(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        msg = "model JSON root must be an object"
        raise ValueError(msg)
    if "success" not in data:
        msg = "model JSON missing success"
        raise ValueError(msg)
    if "keywords" not in data:
        msg = "model JSON missing keywords"
        raise ValueError(msg)

    success = bool(data["success"])
    raw_kw = data.get("keywords", [])
    if raw_kw is None:
        raw_kw = []
    if not isinstance(raw_kw, list):
        msg = "keywords must be an array"
        raise ValueError(msg)

    keywords = [str(x).strip() for x in raw_kw if str(x).strip()]
    if success and len(keywords) < 3:
        msg = "keywords must contain 3 items when success=true"
        raise ValueError(msg)

    return {
        "success": success,
        "keywords": keywords,
    }


def generate_keywords_from_event(title: str, description: str) -> dict[str, Any]:
    if not (OLLAMA_MODEL or "").strip():
        msg = "OLLAMA_MODEL is not set"
        raise RuntimeError(msg)

    t = (title or "").strip()
    d = (description or "").strip()
    if not t and not d:
        msg = "event title and description are both empty"
        raise ValueError(msg)

    if len(t) > _MAX_TITLE_CHARS:
        t = t[:_MAX_TITLE_CHARS]
    if len(d) > _MAX_DESCRIPTION_CHARS:
        d = d[:_MAX_DESCRIPTION_CHARS]

    user_block = f"Event title:\n{t}\n\nEvent description:\n{d}"
    raw_text = ollama_display_chat_raw(
        system=_SYSTEM_INSTRUCTION,
        user=user_block,
        model=OLLAMA_MODEL.strip(),
    )
    data = parse_display_ai_model_json(raw_text)
    out = _coerce_event_keywords_payload(data)
    if out["success"] and out["keywords"]:
        out["keywords"] = out["keywords"][:3]
    return out

