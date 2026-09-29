"""Settings and Pushover delivery."""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"

TITLES = {
    "whisper": "Whisper", "seen": "Player online", "keyword": "Keyword", "invite": "Group invite",
    "queue": "Queue ready", "readycheck": "Ready check", "afk": "While you were away",
    "quest": "Quest", "test": "Lookout test",
}
URGENT = {"queue", "readycheck", "invite"}   # these time out in game, so they buzz harder


def load_config(path=CONFIG):
    """config.json: {"pushover": {"token": ..., "user": ...}, "chat_log": optional path}."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def pushover_keys(config):
    keys = config.get("pushover") or {}
    return keys.get("token"), keys.get("user")


def send(config, signal):
    """Send one alert. Returns (sent, detail)."""
    token, user = pushover_keys(config)
    if not token or not user or token.startswith("your-") or user.startswith("your-"):
        return False, f"no Pushover keys yet: paste your token and user key into {CONFIG}"
    body = urllib.parse.urlencode({
        "token": token, "user": user,
        "title": f"{TITLES.get(signal.kind, signal.kind)} ({signal.char})",
        "message": signal.text or "(no text)",
        "priority": 1 if signal.kind in URGENT else 0,
    }).encode()
    try:
        with urllib.request.urlopen("https://api.pushover.net/1/messages.json", body, timeout=15) as reply:
            return reply.status == 200, f"Pushover answered {reply.status}"
    except urllib.error.HTTPError as error:   # Pushover explains a rejection in the reply body
        try:
            reasons = "; ".join(json.loads(error.read()).get("errors", []))
        except ValueError:
            reasons = ""
        return False, f"Pushover rejected the alert ({error.code}): {reasons or error.reason}"
    except OSError as error:
        return False, f"Pushover send failed: {error}"
