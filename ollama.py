import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

URL: str = "http://localhost:11434"
MODEL: str = "codestral:latest"
TIMEOUT_PING: int = 3
TIMEOUT_INFER: int = 240


def reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=TIMEOUT_PING) as r:
            return r.status == 200
    except Exception:
        return False


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    format: str = "json",
) -> str:
    """Send a chat request to Ollama. Returns the content string.

    Raises urllib.error.HTTPError or OSError on failure.
    """
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
