"""Ollama-backed one-sentence community description and keywords from name + description text."""

from __future__ import annotations

from typing import Any

from app.company_display_ai import coerce_display_ai_payload, parse_display_ai_model_json
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_NAME_CHARS = 255
_MAX_DESCRIPTION_CHARS = 4000

_SYSTEM_INSTRUCTION = """You are an assistant for a student communities directory. Each community has a name and a longer description that may be messy, repetitive, or marketing-heavy.

Your task:
- Produce exactly one clear, candidate-facing sentence that captures what the community is and who it is for. It must be a single sentence (no bullet lists, no multiple paragraphs).
- Produce exactly 3 short keywords that reflect the community's focus, based on both the name and the description (e.g. topic, activity type, audience). Use lowercase or Title Case consistently; no full sentences as keywords.

Rules:
- If the name and description together are empty, gibberish, or clearly not about a real community (error page, CAPTCHA text, etc.), return: {"success": false, "description": "", "keywords": []}
- Otherwise return success: true with the one-sentence description and exactly 3 keywords (array of 3 strings).
- Be factual; do not invent events, sponsors, or details not supported by the text.
- Jordan is not a keyword; do not use "Jordan" as a keyword."""


def generate_display_fields_from_community(name: str, description: str) -> dict[str, Any]:
    """
    Call local Ollama with community name and description. Returns dict keys:
    success, description, keywords (list[str], at most 3 entries when success).
    """
    if not (OLLAMA_MODEL or "").strip():
        msg = "OLLAMA_MODEL is not set"
        raise RuntimeError(msg)

    n = (name or "").strip()
    d = (description or "").strip()
    if not n and not d:
        msg = "community name and description are both empty"
        raise ValueError(msg)

    if len(n) > _MAX_NAME_CHARS:
        n = n[:_MAX_NAME_CHARS]
    if len(d) > _MAX_DESCRIPTION_CHARS:
        d = d[:_MAX_DESCRIPTION_CHARS]

    user_block = f"Community name:\n{n}\n\nCommunity description:\n{d}"
    raw_text = ollama_display_chat_raw(
        system=_SYSTEM_INSTRUCTION,
        user=user_block,
        model=OLLAMA_MODEL.strip(),
    )
    data = parse_display_ai_model_json(raw_text)
    out = coerce_display_ai_payload(data)
    if out["success"] and out["keywords"]:
        out["keywords"] = out["keywords"][:3]
    return out
