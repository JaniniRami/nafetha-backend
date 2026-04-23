"""Ollama-backed extraction of displayed_description / displayed_keywords from company about text."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_ABOUT_CHARS = 2000

_SYSTEM_INSTRUCTION = """You are a keyword extractor for a student internship and career platform.

You will receive scraped text from a company website. Output JSON only, no explanation.

Return format (STRICT, exactly three fields, nothing else):
{"success": true|false, "description": "one sentence", "keywords": ["k1","k2","k3"]}

RULES:
- Output ONLY {"success": ..., "description": ..., "keywords": [...]}. No other fields.
- Ignore noise: navigation menus, cookie banners, legal boilerplate, ads, sidebars.
- If the page is an error, CAPTCHA, bot-detection, Google search result, or gibberish: {"success": false, "description": "", "keywords": []}
- Common signs of non-company pages: "unusual traffic", "not a robot", "IP address:", "Our systems have detected".
- If success=true, return exactly 3 keywords and one short plain-English sentence describing what the company does.
- Description should tell a student what kind of company this is in one sentence, no fluff.
- Keywords must be lowercase, no hyphens, singular form (e.g. "engineer" not "engineers").
- Keywords must reflect the industry, technical domain, or discipline a student would use to describe their own interests — not marketing language.
- Do NOT use: "jordan", "solution", "innovation", "excellence", "leading", "opportunity", or any other generic business language.
- Input may be in Arabic or English. Always output keywords and description in English.

Examples:
Input: company that builds ERP software for logistics firms -> {"success": true, "description": "Develops ERP software tailored for logistics and supply chain operations.", "keywords": ["software engineering", "logistics", "erp"]}
Input: cybersecurity firm offering SOC and threat intelligence services -> {"success": true, "description": "Provides managed security operations and threat intelligence for enterprise clients.", "keywords": ["cybersecurity", "network security", "cloud"]}
Input: unusual traffic detected, please verify you are not a robot -> {"success": false, "description": "", "keywords": []}"""

def _parse_json_response(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        msg = "empty model response"
        raise ValueError(msg)
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    return json.loads(raw)


def parse_display_ai_model_json(text: str) -> dict[str, Any]:
    """Parse JSON from the model response body (handles optional markdown fences)."""
    return _parse_json_response(text)


def keywords_to_stored_string(keywords: list[str], *, max_len: int = 1024) -> str:
    """Comma-separated, no spaces (matches ScrapedCompanyUpdate validation)."""
    parts: list[str] = []
    for kw in keywords:
        s = " ".join((kw or "").split())
        if not s:
            continue
        s = s.replace(" ", "-")
        if s and s not in parts:
            parts.append(s)
    out = ",".join(parts)
    if len(out) > max_len:
        out = out[:max_len]
        if "," in out:
            out = out.rsplit(",", 1)[0]
    return out


def coerce_display_ai_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate/normalize parsed JSON into success, description, keywords."""
    if not isinstance(data, dict):
        msg = "model JSON root must be an object"
        raise ValueError(msg)
    if "success" not in data:
        msg = "model JSON missing success"
        raise ValueError(msg)

    success = bool(data["success"])
    description = data.get("description", "")
    if not isinstance(description, str):
        msg = "description must be a string"
        raise ValueError(msg)

    raw_kw = data.get("keywords", [])
    if raw_kw is None:
        raw_kw = []
    if not isinstance(raw_kw, list):
        msg = "keywords must be an array"
        raise ValueError(msg)
    keywords = [str(x).strip() for x in raw_kw if str(x).strip()]

    return {
        "success": success,
        "description": description.strip(),
        "keywords": keywords,
    }


def generate_display_fields_from_about(about: str) -> dict[str, Any]:
    """
    Call local Ollama with about-page text. Returns a dict with keys:
    success, description, keywords (list[str]).
    """
    if not (OLLAMA_MODEL or "").strip():
        msg = "OLLAMA_MODEL is not set"
        raise RuntimeError(msg)

    trimmed = (about or "").strip()
    if not trimmed:
        msg = "about text is empty"
        raise ValueError(msg)
    if len(trimmed) > _MAX_ABOUT_CHARS:
        trimmed = trimmed[:_MAX_ABOUT_CHARS]

    raw_text = ollama_display_chat_raw(
        system=_SYSTEM_INSTRUCTION,
        user=f"Company about page content:\n\n{trimmed}",
        model=OLLAMA_MODEL.strip(),
    )
    data = parse_display_ai_model_json(raw_text)
    return coerce_display_ai_payload(data)
