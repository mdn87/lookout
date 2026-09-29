"""One-shot screenshot experiment; not the normal companion transport."""
import argparse
import re
from pathlib import Path

from PIL import Image
import zxingcpp

from companion import notify
from companion.chatlog import Signal


def decode(path, expected):
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,32}", expected):
        raise ValueError("invalid test code")
    with Image.open(path) as image:
        width, height = image.size
        # WoW saves a full frame; only this local corner goes to the QR decoder.
        crop = image.crop((0, max(0, height - 512), min(width, 512), height)).convert("RGB")
    results = zxingcpp.read_barcodes(crop, formats=zxingcpp.BarcodeFormat.QRCode)
    matches = [r for r in results if r.text == f"LOOKOUT-PROBE-1:{expected}"]
    if len(matches) != 1:
        raise ValueError("expected test code not found exactly once in bottom-left crop")
    return Signal("screenshot probe", "test", f"In-game screenshot decoded without logging out. Test code: {expected}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--code", required=True)
    parser.add_argument("--send", action="store_true", help="Send decoded test text to your configured Pushover account")
    args = parser.parse_args()
    try:
        signal = decode(args.image, args.code)
    except (OSError, ValueError) as error:
        print(f"Screenshot probe failed: {error}")
        return 1
    print(signal.text)
    if args.send:
        sent, detail = notify.send(notify.load_config(), signal)
        print(detail)
        return 0 if sent else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
