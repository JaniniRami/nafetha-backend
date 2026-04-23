"""Call local Ollama for structured display-field JSON (companies, jobs, communities)."""

from __future__ import annotations

import json
from typing import Any

# JSON schema passed to Ollama so the model returns a single object (see `ollama` Python `chat(..., format=...)`).
_DISPLAY_FIELDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "description": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["success", "description", "keywords"],
}


def ollama_display_chat_raw(
    *,
    system: str,
    user: str,
    model: str,
    response_schema: dict[str, Any] | None = None,
) -> str:
    """
    Run ``ollama.chat`` with JSON-schema output. Returns assistant message text (JSON string).

    Set ``OLLAMA_HOST`` in the environment if Ollama is not on the default (``http://127.0.0.1:11434``).
    """
    try:
        from ollama import chat
    except ImportError as exc:
        msg = "ollama package is not installed (pip install ollama)"
        raise RuntimeError(msg) from exc

    schema = response_schema or _DISPLAY_FIELDS_SCHEMA

    try:
        response = chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format=schema,
            options={"temperature": 0.2, "num_predict": 512},
        )
    except Exception as exc:
        msg = (
            f"Ollama request failed (model={model!r}). Is the server running (`ollama serve`) "
            f"and is the model pulled (`ollama pull {model}`)? {exc}"
        )
        raise RuntimeError(msg) from exc

    content = getattr(getattr(response, "message", None), "content", None)
    if content is None:
        msg = "Ollama returned no message content"
        raise RuntimeError(msg)
    if isinstance(content, dict):
        return json.dumps(content)
    return str(content)
