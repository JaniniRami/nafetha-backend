"""Ollama-backed single-keyword classification for volunteering events."""

from __future__ import annotations

from typing import Any

from app.company_display_ai import parse_display_ai_model_json
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_EVENT_TEXT_CHARS = 2500
_KEYWORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "keyword": {"type": "string"},
    },
    "required": ["success", "keyword"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = """You are an assistant for classifying volunteering events.

You will receive event metadata and text. Output JSON only, no explanation.

Return format (STRICT, exactly two fields, nothing else):
{"success": true|false, "keyword": "<single_keyword_or_empty>"}

STEP 1 — Check if the event has any environmental angle (nature, trees, recycling, pollution, conservation, sustainability, cleaning, animals, green, eco, water, etc). If yes, keyword = "environmental". Stop here.

STEP 2 — Only if there is absolutely no environmental angle, pick ONE keyword from: social, health, animal_welfare, education, cultural, digital, sports, legal, economic. Or another single word if none fit.

RULES:
- Output ONLY {"success": ..., "keyword": ...}. No other fields. No arrays. No "description". No "keywords" array.
- keyword is always a single string.
- keyword is lowercase with underscores, never spaces.
- Do not use "jordan" as a keyword.
- If the event is empty, gibberish, or unclassifiable: {"success": false, "keyword": ""}

Examples:
Input: tree planting event → {"success": true, "keyword": "environmental"}
Input: blood donation drive → {"success": true, "keyword": "health"}
Input: asdfgh → {"success": false, "keyword": ""}"""



def _normalize_keyword(value: str) -> str:
    s = " ".join((value or "").strip().lower().split())
    if not s:
        return ""
    return s.replace("-", "_").replace(" ", "_")


def classify_volunteering_keyword(event_text: str) -> dict[str, Any]:
    """Classify a volunteering event into one stored keyword."""
    if not (OLLAMA_MODEL or "").strip():
        msg = "OLLAMA_MODEL is not set"
        raise RuntimeError(msg)

    text = (event_text or "").strip()
    if not text:
        msg = "event text is empty"
        raise ValueError(msg)
    if len(text) > _MAX_EVENT_TEXT_CHARS:
        text = text[:_MAX_EVENT_TEXT_CHARS]

    raw_text = ollama_display_chat_raw(
        system=_SYSTEM_INSTRUCTION,
        user=f"Volunteering event content:\n\n{text}",
        model=OLLAMA_MODEL.strip(),
        response_schema=_KEYWORD_SCHEMA,
    )
    print(f"[volunteering-ai] raw model response: {raw_text}", flush=True)
    data = parse_display_ai_model_json(raw_text)
    if not isinstance(data, dict):
        msg = "model JSON root must be an object"
        raise ValueError(msg)
    if "success" not in data:
        msg = "model JSON missing success"
        raise ValueError(msg)

    success = bool(data["success"])
    keyword_raw = data.get("keyword", "")
    if keyword_raw is None:
        keyword_raw = ""
    if not isinstance(keyword_raw, str):
        msg = "keyword must be a string"
        raise ValueError(msg)
    keyword = _normalize_keyword(keyword_raw)

    if success and not keyword:
        msg = "keyword is empty while success=true"
        raise ValueError(msg)

    return {
        "success": success,
        "keyword": keyword,
    }
