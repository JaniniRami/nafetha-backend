"""Ollama-backed extraction of displayed_description / displayed_keywords from job description text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.company_display_ai import (
    coerce_display_ai_payload,
    parse_display_ai_model_json,
)
from app.config import OLLAMA_MODEL
from app.ollama_display_client import ollama_display_chat_raw

_JOB_DISPLAY_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "job_display_system_instruction.txt"
)

_MAX_JOB_DESC_CHARS = 2000

_DEFAULT_JOB_SYSTEM_INSTRUCTION = """You are a job board assistant. Extract a one-sentence candidate-facing summary and exactly 3 comma-worthy keywords from job posting text. If the text is not a real job (error page, CAPTCHA, empty), return success false with empty description and keywords. Do not use Jordan as a keyword."""


def _load_job_display_system_instruction() -> str:
    try:
        text = _JOB_DISPLAY_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return _DEFAULT_JOB_SYSTEM_INSTRUCTION
    return text if text else _DEFAULT_JOB_SYSTEM_INSTRUCTION


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

    system_instruction = _load_job_display_system_instruction()
    raw_text = ollama_display_chat_raw(
        system=system_instruction,
        user=f"Job posting content:\n\n{trimmed}",
        model=OLLAMA_MODEL.strip(),
    )
    data = parse_display_ai_model_json(raw_text)
    return coerce_display_ai_payload(data)
