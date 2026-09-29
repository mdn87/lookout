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
    """config.json: {"pushover": {"token": ..., "user": ...}, optional "chat_log",
    "screenshot_dirs" and "keep_screenshots"}."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def pushover_keys(config):
    keys = config.get("pushover") or {}
    return keys.get("token"), keys.get("user")


def compose(signals, dropped=0):
    """Title, message and priority for one push carrying one or more alerts."""
    first = signals[0]
    if len(signals) == 1:
        title = f"{TITLES.get(first.kind, first.kind)} ({first.char})"
        message = first.text or "(no text)"
    else:
        title = f"{len(signals)} alerts ({first.char})"
        message = "\n".join(f"{TITLES.get(s.kind, s.kind)}: {s.text}" for s in signals)
    if dropped:
        message += f"\n(+{dropped} older alerts dropped by the rate limit)"
    return title, message[:1024], 1 if any(s.kind in URGENT for s in signals) else 0


def send(config, *signals, dropped=0):
    """Send one push for these alerts. Returns (sent, detail)."""
    token, user = pushover_keys(config)
    if not token or not user or token.startswith("your-") or user.startswith("your-"):
        return False, f"no Pushover keys yet: paste your token and user key into {CONFIG}"
    title, message, priority = compose(signals, dropped)
    body = urllib.parse.urlencode({
        "token": token, "user": user, "title": title, "message": message, "priority": priority,
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
