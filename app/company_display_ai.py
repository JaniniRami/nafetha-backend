"""Ollama-backed extraction of displayed_description / displayed_keywords from company about text."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_MAX_ABOUT_CHARS = 2000

_SYSTEM_INSTRUCTION = """You are a business directory assistant. Your job is to extract structured information about a company from scraped website text.

The input you receive is raw scraped content from a company's about page or website. It may contain noise such as: navigation menus, cookie banners, legal boilerplate, ads, unrelated sidebar content, or other web artifacts — ignore all of that.

Sometimes the scraped content is not actually about a company at all. This happens when the page failed to load and instead returned an error, a CAPTCHA challenge, a bot-detection page, a Google search result page, or any other non-company content. Common signs of this include phrases like "unusual traffic", "not a robot", "IP address:", "Time:", "URL:", "Our systems have detected", or any generic error/verification page.

Rules:
- If the content is clearly not about a real company (bot check, CAPTCHA, error page, search result, empty/gibberish content), return: {"success": false, "description": "", "keywords": []}
- If the content is about a real company but is noisy, extract what you can from the relevant parts and return success: true with a one-sentence description of what the company does and exactly 3 relevant keywords.
- Be concise and factual. Do not invent or infer details not present in the text.
- Keywords should reflect the company's industry, services, or domain (e.g. "fintech", "logistics", "B2B software").
- Jordan is not a keyword, because all internship descriptions are about Jordan, do not include it in the keywords."""


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
