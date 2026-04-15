import json
import logging
import urllib.error
import urllib.request
from typing import Any

import bpy

logger = logging.getLogger(__name__)

URL: str = "http://localhost:11434"
MODEL: str = "codestral:latest"
TIMEOUT_PING: int = 3
TIMEOUT_INFER: int = 240


def reachable() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=TIMEOUT_PING) as r:
            return r.status == 200
    except Exception:
        return False


def model_available(model: str | None = None) -> bool:
    """Return True if the given model is already pulled locally."""
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=TIMEOUT_PING) as r:
            data = json.loads(r.read())
        names = [entry.get("name", "") for entry in data.get("models", [])]
        return (model or MODEL) in names
    except Exception:
        return False


def pull_model(model: str | None = None) -> None:
    """Pull a model from the Ollama registry if it is not available locally."""
    target = model or MODEL
    logger.info("Pulling Ollama model %s …", target)
    window_manager = bpy.context.window_manager
    window_manager.progress_begin(0, 1)
    window_manager.progress_update(0)
    bpy.context.workspace.status_text_set(
        f"Pulling Ollama model '{target}', this may take several minutes…"
    )
    try:
        payload = json.dumps({"name": target, "stream": False}).encode()
        request = urllib.request.Request(
            f"{URL}/api/pull",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_INFER) as r:
            result = json.loads(r.read())
        logger.info("Pull result: %s", result.get("status"))
    finally:
        bpy.context.workspace.status_text_set(None)
        window_manager.progress_end()


def ensure_model(model: str | None = None) -> None:
    """Pull the model if it is not already available locally."""
    if not model_available(model):
        pull_model(model)


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    format: str = "json",
) -> str:
    """Send a chat request to Ollama. Returns the content string.

    Pulls the model automatically if it is not available locally.
    Raises urllib.error.HTTPError or OSError on failure.
    """
    ensure_model(model)
    payload = json.dumps(
        {
            "model": model or MODEL,
            "messages": messages,
            "stream": False,
            "format": format,
            "options": {"temperature": temperature},
        }
    ).encode()
    req = urllib.request.Request(
        f"{URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_INFER) as r:
        result = json.loads(r.read())
    content = result.get("message", {}).get("content", "")
    logger.info("Response: %s", content)
    return content
