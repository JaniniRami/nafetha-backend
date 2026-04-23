from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure `app` package imports work when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

INPUT_PATH = ROOT / "data" / "skills" / "demand_by_major.json"
OUTPUT_PATH = ROOT / "data" / "skills" / "reason_per_skill.json"

_REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
    },
    "required": ["reason"],
}

_SYSTEM_PROMPT = """You are writing concise learning-value reasons for skills.

You will receive a university major and a skill.
Return JSON only with this exact format:
{"reason":"..."}

Rules:
- reason must be exactly one sentence.
- keep it practical and career-focused for students.
- 12 to 30 words.
- no markdown, no bullet points, no extra keys.
"""


def _to_one_sentence(text: str) -> str:
    s = " ".join((text or "").strip().split())
    if not s:
        return "Learning this skill strengthens your employability and prepares you for real-world project requirements in this major."
    if s[-1] not in ".!?":
        s += "."
    return s


def _generate_reason_for_skill(major: str, skill: str, model: str) -> str:
    user_prompt = f"Major: {major}\nSkill: {skill}"
    raw_text = ollama_display_chat_raw(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        model=model,
        response_schema=_REASON_SCHEMA,
    )
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from Ollama for skill={skill!r}: {raw_text}") from exc
    reason = str(parsed.get("reason", "")).strip()
    return _to_one_sentence(reason)


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    model = (OLLAMA_MODEL or "").strip()
    if not model:
        raise RuntimeError("OLLAMA_MODEL is not set")

    with INPUT_PATH.open("r", encoding="utf-8") as f:
        demand_by_major = json.load(f)

    if not isinstance(demand_by_major, dict):
        raise ValueError("demand_by_major.json must be an object mapping major -> list[skills]")

    output: dict[str, dict[str, str | None]] = {}
    total = sum(len(skills or []) for skills in demand_by_major.values())
    done = 0

    print(f"[reason-per-skill] start model={model} total_skills={total}", flush=True)
    for major, skills in demand_by_major.items():
        if not isinstance(skills, list):
            print(f"[reason-per-skill] skip major={major} reason=skills_not_list", flush=True)
            continue
        major_key = str(major).strip()
        output[major_key] = {}
        for skill in skills:
            skill_text = str(skill).strip()
            if not skill_text:
                continue
            done += 1
            try:
                reason = _generate_reason_for_skill(major_key, skill_text, model)
                output[major_key][skill_text] = reason
                print(
                    f"[reason-per-skill] ok progress={done}/{total} major={major_key} skill={skill_text}",
                    flush=True,
                )
                print(f"[reason-per-skill] reason={reason}", flush=True)
                print("", flush=True)
            except Exception as exc:
                output[major_key][skill_text] = None
                print(
                    f"[reason-per-skill] fail progress={done}/{total} major={major_key} skill={skill_text} error={exc}",
                    flush=True,
                )
                print("", flush=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[reason-per-skill] wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
