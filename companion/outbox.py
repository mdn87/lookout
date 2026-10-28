"""Alerts the phone hasn't taken yet, saved in a small JSON file so they survive a restart.

The watcher saves each batch before its first send and drops it once Pushover accepts the push,
so a delivered alert isn't sent again after a restart. A failed batch is tried again after a
wait, ATTEMPTS tries in all. Two cases can still repeat a push: the companion dying between
Pushover's answer and the save, and a timeout that hides a push Pushover actually accepted.
"""
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .chatlog import Signal

WAITS = (10, 60, 300, 900)     # seconds before each retry: 10 s, then 1, 5 and 15 minutes
ATTEMPTS = len(WAITS) + 1      # 5: the first send and four retries
FILENAME = "pending-alerts.json"
log = logging.getLogger("lookout")


def default_path(environ=os.environ):
    """%LOCALAPPDATA%/Lookout/pending-alerts.json, or the XDG state folder elsewhere. Outside the
    checkout, so alert text never sits in the git tree."""
    if environ.get("LOCALAPPDATA"):
        return Path(environ["LOCALAPPDATA"]) / "Lookout" / FILENAME
    return Path(environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "lookout" / FILENAME


@dataclass
class Entry:
    """One batch of alerts waiting for the phone, and the screenshot it came from."""
    signals: tuple
    dropped: int = 0
    screenshot: str | None = None
    created: float = 0.0
    attempts: int = 0          # failed tries so far
    next_try: float = 0.0
    detail: str = ""           # why the last try failed


class Outbox:
    """The waiting batches, saved to path after every change, or kept in memory without one."""

    def __init__(self, path=None, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.entries = self.load()
        if self.entries:
            log.info("%d undelivered alert batch(es) from the last run will be retried", len(self.entries))

    def __len__(self):
        return len(self.entries)

    def load(self):
        if not self.path:
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            log.warning("Could not read pending alerts from %s (%s); starting with none", self.path, error)
            return []
        entries = []
        for item in data.get("alerts", []) if isinstance(data, dict) else []:
            try:
                entry = Entry(**{**item, "signals": tuple(Signal(**s) for s in item["signals"])})
            except (KeyError, TypeError):
                entry = None
            if entry and entry.signals:
                entries.append(entry)
            else:
                log.warning("Skipped an unreadable pending alert in %s", self.path)
        return entries

    def save(self):
        if not self.path:
            return
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps({"version": 1, "alerts": [asdict(e) for e in self.entries]},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(temp, self.path)   # whole file or nothing, so a crash can't leave half of it
        except OSError as error:
            log.warning("Could not save pending alerts to %s: %s", self.path, error)

    def add(self, signals, dropped=0, screenshot=None):
        """Save a batch before its first send."""
        now = self.clock()
        entry = Entry(tuple(signals), dropped, str(screenshot) if screenshot else None, now, 0, now)
        self.entries.append(entry)
        self.save()
        return entry

    def next_due(self):
        """The longest-waiting batch whose retry time has come, or None."""
        now = self.clock()
        due = [entry for entry in self.entries if entry.next_try <= now]
        return min(due, key=lambda entry: entry.next_try) if due else None

    def delivered(self, entry):
        self.entries.remove(entry)
        self.save()

    def failed(self, entry, detail):
        """Count a failed try. Returns the seconds until the next one, or None when that was the
        last allowed try and the batch has been dropped."""
        entry.attempts += 1
        entry.detail = detail
        if entry.attempts >= ATTEMPTS:
            self.entries.remove(entry)
            self.save()
            return None
        wait = WAITS[entry.attempts - 1]
        entry.next_try = self.clock() + wait
        self.save()
        return wait
