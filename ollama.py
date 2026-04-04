import json
import urllib.error
import urllib.request

URL = "http://localhost:11434"
MODEL = "mistral:latest"
TIMEOUT_PING = 3
TIMEOUT_INFER = 60


def reachable():
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=TIMEOUT_PING) as r:
            return r.status == 200
    except Exception:
        return False


def chat(messages, model=None, temperature=0.0, format="json"):
    """Send a chat request to Ollama. Returns the content string.

    Raises urllib.error.HTTPError or OSError on failure.
    """
    payload = json.dumps({
        "model": model or MODEL,
        "messages": messages,
        "stream": False,
        "format": format,
        "options": {"temperature": temperature},
    }).encode()
    req = urllib.request.Request(
        f"{URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_INFER) as r:
        result = json.loads(r.read())
    return result.get("message", {}).get("content", "")
