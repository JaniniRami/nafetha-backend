"""OpenRouter-backed personalized learning roadmap generation."""

from __future__ import annotations

import json
import re
from typing import Any

from openrouter import OpenRouter

from app.config import OPENROUTER_API_KEY

_ROADMAP_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "main": {"type": "string"},
            "technicalComplement": {"type": "string"},
            "toolOrSoftSkill": {"type": "string"},
        },
        "required": ["main", "technicalComplement", "toolOrSoftSkill"],
    },
}
_ROADMAP_MODEL = "google/gemini-2.5-flash-lite"

_SYSTEM_PROMPT = """You are a career advisor. Generate a personalized learning roadmap for a student learning a complex skill as a skill tree output.

Student profile:
- Major: [MAJOR]
- Graduation year: [YEAR]
- Interests: [INTERESTS]
- Goal skill: [SKILL]
- Skills they already have: [CHECKED PREREQUISITES]
You now know the user profile so return a customzied ordered roadmap roadmap of 4-10 while keeping in mind what they already know and skipping it.
Each step:
{
  "main": "skill name",
  "technicalComplement": "skill name",
  "toolOrSoftSkill": "skill name"
}

Return ONLY a valid JSON array, no preamble, no markdown.
"""


def _parse_json_array_response(text: str) -> list[dict[str, str]]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty model response")
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("model response must be a JSON array")
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        main = str(item.get("main", "")).strip()
        technical = str(item.get("technicalComplement", "")).strip()
        tool = str(item.get("toolOrSoftSkill", "")).strip()
        if not main or not technical or not tool:
            continue
        out.append(
            {
                "main": main,
                "technicalComplement": technical,
                "toolOrSoftSkill": tool,
            }
        )
    return out


def _clean_prompt_text(text: str) -> str:
    """Trim token-heavy punctuation while preserving letters and numbers."""
    value = str(text or "").strip().replace("-", " ")
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _clean_prompt_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _clean_prompt_text(raw)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _extract_openrouter_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts).strip()
    return str(content or "")


def generate_personalized_roadmap(
    *,
    major: str,
    graduation_year: int,
    interests: list[str],
    goal_skill: str,
    checked_prerequisites: list[str],
) -> list[dict[str, str]]:
    if not (OPENROUTER_API_KEY or "").strip():
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    cleaned_interests = _clean_prompt_list(interests)
    cleaned_prerequisites = _clean_prompt_list(checked_prerequisites)
    cleaned_goal_skill = _clean_prompt_text(goal_skill)

    user_prompt = (
        f"Student profile:\n"
        f"- Major: {major}\n"
        f"- Graduation year: {graduation_year}\n"
        f"- Interests: {', '.join(cleaned_interests) if cleaned_interests else 'None'}\n"
        f"- Goal skill: {cleaned_goal_skill or goal_skill}\n"
        f"- Skills they already have: {', '.join(cleaned_prerequisites) if cleaned_prerequisites else 'None'}"
    )
    with OpenRouter(api_key=OPENROUTER_API_KEY.strip()) as client:
        response = client.chat.send(
            model=_ROADMAP_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "roadmap_steps", "schema": _ROADMAP_SCHEMA}},
        )
    raw_text = _extract_openrouter_text_content(response.choices[0].message.content)
    print(f"[roadmap-openrouter] raw_output={raw_text}", flush=True)
    steps = _parse_json_array_response(raw_text)
    if not steps:
        raise ValueError("roadmap generation returned no valid steps")
    if len(steps) > 10:
        steps = steps[:10]
    return steps
