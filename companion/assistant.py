"""Answer "/lo help <question>" through an OpenAI-compatible chat endpoint.

The addon sends the question as a "help" alert with the character's whereabouts in square
brackets. The answer goes back to the phone as an "answer" alert. Settings come from the
"assistant" block in config.json supplies nonsecret settings. GLAS supplies the
LOOKOUT_AI_KEY or OMNIROUTE_API_KEY through the child process environment.
"""
import json
import os
import urllib.error
import urllib.request

SYSTEM = (
    "You help a World of Warcraft Classic player who is in game right now and will read your "
    "answer on a phone. Plain text only, no markdown, under 500 characters. Give the exact slash "
    "command, macro or menu path when one exists. The question ends with the character's level, "
    "class, faction, realm and zone in square brackets; use that, don't repeat it."
)
MAX_ANSWER = 1000   # Pushover takes 1024


def settings(config, environ=os.environ):
    """Return endpoint settings and the injected key for this launch."""
    block = config.get("assistant") or {}
    url = block.get("url") or environ.get("LOOKOUT_AI_URL") or environ.get("OMNIROUTE_BASE_URL")
    key = environ.get("LOOKOUT_AI_KEY") or environ.get("OMNIROUTE_API_KEY")
    model = block.get("model") or environ.get("LOOKOUT_AI_MODEL")
    return url, key, model, block.get("timeout") or 60


def ask(config, question, opener=urllib.request.urlopen, environ=os.environ):
    """The assistant's answer to one question. Returns (text or None, detail)."""
    url, key, model, timeout = settings(config, environ)
    if not url or not model:
        return None, 'no assistant yet: set "assistant": {"url", "model"} in config.json'
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
        "max_tokens": 300,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url.rstrip("/") + "/chat/completions", body, headers)
    try:
        with opener(request, timeout=timeout) as reply:
            data = json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as error:   # a gateway explains a rejection in the body
        try:
            reason = json.loads(error.read()).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            reason = ""
        return None, f"assistant rejected the question ({error.code}): {reason or error.reason}"
    except (OSError, ValueError) as error:
        return None, f"assistant request failed: {error}"
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None, "assistant reply had no text"
    return (text[:MAX_ANSWER] or None), f"{model} answered"
