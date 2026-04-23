"""Ollama-backed one-sentence community description and keywords from name + description text."""

from __future__ import annotations

from typing import Any

from app.company_display_ai import coerce_display_ai_payload, parse_display_ai_model_json
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_NAME_CHARS = 255
_MAX_DESCRIPTION_CHARS = 4000

_SYSTEM_INSTRUCTION = """You are a keyword extractor for a student internship and career platform.

You will receive a community name and description. Output JSON only, no explanation.

Return format (STRICT, exactly three fields, nothing else):
{"success": true|false, "description": "one sentence", "keywords": ["k1","k2","k3"]}

RULES:
- Output ONLY {"success": ..., "description": ..., "keywords": [...]}. No other fields.
- If input is empty, gibberish, an error page, or not a real community: {"success": false, "description": "", "keywords": []}
- If success=true, return exactly 3 keywords and one short plain-English sentence describing what the community is and who it is for.
- Keywords must be lowercase, no hyphens, singular form (e.g. "engineer" not "engineers").
- Keywords must reflect the technical field, discipline, or activity a student would use to describe their own interests — the same words they would type to find this community.
- Do NOT use: "jordan", "community", "club", "member", "chapter", "event", "networking", "opportunity", "students", or any generic organizational language.
- Input may be in Arabic or English. Always output keywords and description in English.

Examples:
Input: "IEEE — a global community for electrical and electronics engineering students and professionals" -> {"success": true, "description": "A professional community for students interested in electrical, electronics, and computing fields.", "keywords": ["electrical engineering", "electronics", "computer engineering"]}
Input: "GDG — Google Developer Group for students building with Google technologies" -> {"success": true, "description": "A developer community for students building web and mobile apps using Google technologies.", "keywords": ["software engineering", "mobile development", "cloud"]}
Input: "ASME — mechanical engineering students focused on design and manufacturing" -> {"success": true, "description": "A community for mechanical engineering students interested in design, manufacturing, and applied mechanics.", "keywords": ["mechanical engineering", "cad", "manufacturing"]}
Input: "asdfgh" -> {"success": false, "description": "", "keywords": []}"""

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
