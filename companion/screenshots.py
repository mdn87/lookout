"""Read Lookout alerts out of game screenshots.

The addon draws its queued alerts as a QR code in the bottom-left corner and takes a
screenshot (see addon/Lookout/Screenshot.lua). The payload is UTF-8, one field per line:

    LOOKOUT-2 <sequence number>
    <character>
    <kind>\\t<text>        one line per alert
    dropped\\t<count>      only when the addon's queue overflowed
"""
import glob
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import zxingcpp

from .chatlog import GAME_ROOTS, Signal

HEADER = "LOOKOUT-2"
CROP = 512                  # the addon's code fits in the bottom-left 502 pixels
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".tga"}
RETRIES = 10                # polls to wait for a screenshot the game is still writing


@dataclass(frozen=True)
class Shot:
    char: str
    seq: int
    signals: tuple
    dropped: int = 0


def parse(payload):
    """A Shot from a decoded payload, or None when it isn't a Lookout alert."""
    lines = payload.split("\n")
    head = lines[0].split(" ")
    if len(lines) < 3 or head[0] != HEADER or len(head) != 2 or not head[1].isdigit():
        return None
    char, signals, dropped = lines[1], [], 0
    for line in lines[2:]:
        kind, _, text = line.partition("\t")
        if kind == "dropped" and text.isdigit():
            dropped = int(text)
        elif kind:
            signals.append(Signal(char, kind, text))
    return Shot(char, int(head[1]), tuple(signals), dropped) if signals else None


def decode(path):
    """The Lookout alerts in one screenshot, or None. Raises OSError while the file is incomplete."""
    with Image.open(path) as image:
        width, height = image.size
        crop = image.crop((0, max(0, height - CROP), min(width, CROP), height)).convert("RGB")
    for result in zxingcpp.read_barcodes(crop, formats=zxingcpp.BarcodeFormat.QRCode):
        # The raw bytes, because zxing guesses a text encoding for byte-mode codes.
        shot = parse(result.bytes.decode("utf-8", errors="replace"))
        if shot:
            return shot
    return None


def find_screenshot_dirs(roots=GAME_ROOTS):
    """<game>/<version>/Screenshots for every installed version. The game makes the folder at
    the first screenshot, so it may not exist yet."""
    found = {Path(p).parent.parent / "Screenshots"
             for root in roots for p in glob.glob(os.path.join(root, "*", "Interface", "AddOns"))}
    return sorted(found)


class Folder:
    """New image files in one Screenshots folder. Files there at startup are left alone."""

    def __init__(self, path):
        self.path = Path(path)
        self.seen = set(self.listing())
        self.tries = {}

    def listing(self):
        try:
            return [entry.name for entry in os.scandir(self.path)
                    if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_TYPES]
        except OSError:
            return []

    def poll(self):
        """(path, Shot or None) for each new screenshot the game has finished writing."""
        out = []
        for name in sorted(set(self.listing()) - self.seen):
            path = self.path / name
            try:
                shot = decode(path)
            except (OSError, SyntaxError):   # still being written, or locked by the game
                self.tries[name] = self.tries.get(name, 0) + 1
                if self.tries[name] < RETRIES:
                    continue
                shot = None
            self.seen.add(name)
            self.tries.pop(name, None)
            out.append((path, shot))
        return out
