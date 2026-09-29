"""Watch WoW's chat log and push a phone notification when a chosen player whispers you
or talks in a channel you can see.

The game only writes Logs/WoWChatLog.txt while chat logging is on. The WhisperWatch addon
turns it on at login; without the addon, type /chatlog once per session.

    python whisper_watch.py                  # watch for Saalora, notify through Pushover
    python whisper_watch.py --dry-run        # print instead of notifying
    python whisper_watch.py --test-push      # send one test notification and exit

Pushover keys come from pushover.json next to this file ({"token": ..., "user": ...}) or
from the PUSHOVER_TOKEN and PUSHOVER_USER environment variables.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LOG = "C:/Program Files (x86)/Battle.net/World of Warcraft/_classic_beta_/Logs/WoWChatLog.txt"
COOLDOWN = 300   # seconds between notifications of the same kind, so a chat doesn't flood the phone


def patterns(name):
    """Line matchers for an incoming whisper and for the player talking in any channel you
    can see (General, trade, say, yell), which shows she's online without a friend list.
    Outgoing whispers ("To [Saalora]: ...") match neither: the name must be the speaker."""
    who = re.escape(name) + r"[^\s\]:]*\]?"
    return {
        "whisper": re.compile(who + r"\s+whispers:\s*(?P<text>.*)", re.I),
        "seen": re.compile(r"(?<!To )\[" + who + r"(?::|\s+says:|\s+yells:)\s*(?P<text>.*)", re.I),
    }


def load_keys():
    path = HERE / "pushover.json"
    if path.exists():
        keys = json.loads(path.read_text(encoding="utf-8"))
        return keys.get("token"), keys.get("user")
    return os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")


def push(title, message, dry_run):
    if dry_run:
        print(f"[dry-run] {title}: {message}", flush=True)
        return True
    token, user = load_keys()
    if not token or not user:
        print("No Pushover keys: fill in pushover.json (see pushover.example.json).", file=sys.stderr)
        return False
    body = urllib.parse.urlencode({"token": token, "user": user, "title": title,
                                   "message": message, "priority": 1}).encode()
    try:
        with urllib.request.urlopen("https://api.pushover.net/1/messages.json", body, timeout=15) as reply:
            ok = reply.status == 200
    except OSError as error:
        print(f"Pushover send failed: {error}", file=sys.stderr)
        return False
    print(f"pushed: {title}: {message}" if ok else "Pushover refused the message", flush=True)
    return ok


def follow(path, from_start, poll):
    """Yield new lines appended to path. Waits for the file to appear and starts over if the
    game truncates or replaces it."""
    offset = None
    while True:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(poll)
            continue
        if offset is None:
            offset = 0 if from_start else size
        if size < offset:
            offset = 0
        if size > offset:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()
            yield from chunk.splitlines()
        time.sleep(poll)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="Saalora", help="character name to watch for")
    parser.add_argument("--log", default=DEFAULT_LOG, help="path to WoWChatLog.txt")
    parser.add_argument("--dry-run", action="store_true", help="print notifications instead of sending")
    parser.add_argument("--from-start", action="store_true", help="also scan what the log already holds")
    parser.add_argument("--poll", type=float, default=2.0, help="seconds between log checks")
    parser.add_argument("--test-push", action="store_true", help="send one test notification and exit")
    args = parser.parse_args(argv)

    if args.test_push:
        return 0 if push("WhisperWatch test", "Phone notifications work.", args.dry_run) else 1

    log = Path(args.log)
    print(f"Watching {log} for {args.name}. Ctrl+C to stop.", flush=True)
    if not log.exists():
        print("The chat log doesn't exist yet; waiting for the game to start logging (/chatlog).", flush=True)
    matchers = patterns(args.name)
    last_sent = {}
    for line in follow(log, args.from_start, args.poll):
        for kind, matcher in matchers.items():
            found = matcher.search(line)
            if not found:
                continue
            if time.time() - last_sent.get(kind, 0) < COOLDOWN:
                continue
            if kind == "whisper":
                sent = push(f"{args.name} whispered you", found.group("text")[:200] or "(empty)", args.dry_run)
            else:
                sent = push(f"{args.name} is online", "Seen in chat: " + found.group("text")[:150], args.dry_run)
            if sent:
                last_sent[kind] = time.time()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
