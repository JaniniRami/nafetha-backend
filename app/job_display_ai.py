"""Ollama-backed extraction of displayed_description / displayed_keywords from job description text."""

from __future__ import annotations

from typing import Any
import re

from app.company_display_ai import (
    coerce_display_ai_payload,
    parse_display_ai_model_json,
)
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_JOB_DESC_CHARS = 2000
_FORBIDDEN_TERMS = {"internship", "jordan"}

_DEFAULT_JOB_SYSTEM_INSTRUCTION = """You are a keyword extractor for a student internship and career platform.

You will receive a job posting. Output JSON only, no explanation.

Return format (STRICT, exactly three fields, nothing else):
{"success": true|false, "description": "one sentence", "keywords": ["k1","k2","k3"]}

RULES:
- Output ONLY {"success": ..., "description": ..., "keywords": [...]}. No other fields.
- If input is empty, gibberish, a CAPTCHA, or not a real job posting: {"success": false, "description": "", "keywords": []}
- If success=true, return exactly 3 keywords and exactly one short candidate-facing sentence in description.
- Description should tell a student what the role is about in plain language, one sentence, no fluff.
- Keywords must be lowercase, no hyphens, singular form (e.g. "engineer" not "engineers").
- Keywords must reflect the technical field, required skill, or academic discipline — the kind of words a student would use to describe their own background and interests.
- Do NOT use: "internship", "jordan", "opportunity", "training", "applicant", "hiring", "job", "position", "candidate", or any other generic recruitment language.
- Do NOT use full sentences or long phrases for keywords.
- Input may be in Arabic or English. Always output keywords and description in English.
- DO NOT USE internship as a keyword or description.

Examples:
Input: "We are looking for a backend developer comfortable with Node.js and REST APIs" -> {"success": true, "description": "Build and maintain server-side services using Node.js and REST APIs.", "keywords": ["backend", "node.js", "api development"]}
Input: "Embedded firmware role working with STM32 and FreeRTOS" -> {"success": true, "description": "Develop low-level firmware for STM32 microcontrollers running FreeRTOS.", "keywords": ["embedded systems", "firmware", "c programming"]}
Input: "Error 404 page not found" -> {"success": false, "description": "", "keywords": []}"""

def generate_display_fields_from_job_description(job_description: str) -> dict[str, Any]:
    """
    Call local Ollama with job description text. Returns dict keys:
    success, description, keywords (list[str]).
    """
    if not (OLLAMA_MODEL or "").strip():
        msg = "OLLAMA_MODEL is not set"
        raise RuntimeError(msg)

    trimmed = (job_description or "").strip()
    if not trimmed:
        msg = "job description is empty"
        raise ValueError(msg)
    if len(trimmed) > _MAX_JOB_DESC_CHARS:
        trimmed = trimmed[:_MAX_JOB_DESC_CHARS]

    raw_text = ollama_display_chat_raw(
        system=_DEFAULT_JOB_SYSTEM_INSTRUCTION,
        user=f"Job posting content:\n\n{trimmed}",
        model=OLLAMA_MODEL.strip(),
    )
    data = parse_display_ai_model_json(raw_text)
    out = coerce_display_ai_payload(data)

    cleaned_keywords = [kw for kw in out["keywords"] if kw.strip().lower() not in _FORBIDDEN_TERMS]
    out["keywords"] = cleaned_keywords[:3]

    desc = out["description"]
    for term in _FORBIDDEN_TERMS:
        desc = re.sub(rf"\b{re.escape(term)}\b", "", desc, flags=re.IGNORECASE)
    out["description"] = " ".join(desc.split()).strip(" ,.-")
    return out
