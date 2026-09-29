"""Find and follow WoWChatLog.txt, and pick out the addon's signal lines.

The addon whispers you "LOOKOUT :: <character> :: <kind> :: <text>". The game logs that
twice, as the outgoing "To [You]: ..." and the incoming "[You] whispers: ...", so the same
signal seen again within a few seconds is dropped.
"""
import glob
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

SIGNAL = re.compile(r"LOOKOUT :: (?P<char>[^:]+?) :: (?P<kind>[a-z]+) :: (?P<text>.*?)\s*$")
GAME_ROOTS = [
    "C:/Program Files (x86)/Battle.net/World of Warcraft",
    "C:/Program Files (x86)/World of Warcraft",
    "C:/Program Files/World of Warcraft",
]


@dataclass(frozen=True)
class Signal:
    char: str
    kind: str
    text: str


def parse(line):
    found = SIGNAL.search(line)
    return Signal(found["char"], found["kind"], found["text"]) if found else None


class Deduper:
    def __init__(self, window=10.0, clock=time.monotonic):
        self.window, self.clock, self.seen = window, clock, {}

    def fresh(self, signal):
        now = self.clock()
        self.seen = {key: at for key, at in self.seen.items() if now - at < self.window}
        if signal in self.seen:
            return False
        self.seen[signal] = now
        return True


def find_chat_logs(roots=GAME_ROOTS):
    """Chat log paths for every installed game version (retail, classic, betas), newest
    first. A version that hasn't logged yet is listed by where its log will appear."""
    found = []
    for root in roots:
        for logs in glob.glob(os.path.join(root, "*", "Logs")):
            path = Path(logs) / "WoWChatLog.txt"
            found.append((path.stat().st_mtime if path.exists() else Path(logs).stat().st_mtime, path))
    return [path for _, path in sorted(found, reverse=True)]


class Follower:
    """New lines appended to a file since the last poll. Starts at the end of the file, and
    starts over if the game truncates or replaces it."""

    def __init__(self, path, from_start=False):
        self.path = Path(path)
        self.offset = None if not from_start else 0

    def poll(self):
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return []
        if self.offset is None:
            self.offset = size
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
        end = chunk.rfind(b"\n") + 1   # leave a half-written last line for the next poll
        self.offset += end
        return chunk[:end].decode("utf-8", errors="replace").splitlines()
