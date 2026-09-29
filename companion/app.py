"""Lookout companion: a tray icon that watches the chat log and sends alerts to your phone.

    pythonw -m companion.app            tray icon (start-companion.cmd does this)
    python -m companion.app --console   print alerts in a terminal instead, no tray
    python -m companion.app --test-push send one test alert to your phone and exit
"""
import argparse
import os
import threading
import time
from pathlib import Path

from . import chatlog, notify


class Watcher:
    """Polls the chat log on a thread and hands each new signal to deliver()."""

    def __init__(self, config, deliver, poll=1.0):
        self.config, self.deliver, self.poll = config, deliver, poll
        self.paused = False
        self.status = "starting"
        self.last = "nothing yet"
        self.path = None
        self.follower = None
        self.dedupe = chatlog.Deduper()
        self.stopping = threading.Event()

    def choose_log(self):
        if self.config.get("chat_log"):
            return Path(self.config["chat_log"])
        logs = chatlog.find_chat_logs()
        return logs[0] if logs else None

    def step(self):
        """One poll: find the log if needed, read new lines, deliver signals."""
        path = self.choose_log()
        if path != self.path:
            self.path, self.follower = path, chatlog.Follower(path) if path else None
        if not self.follower:
            self.status = "no WoW install found"
            return
        if not self.path.exists():
            self.status = "waiting for the chat log (log in with the addon, or type /chatlog)"
            return
        self.status = "paused" if self.paused else "watching"
        for line in self.follower.poll():
            signal = chatlog.parse(line)
            if not signal or not self.dedupe.fresh(signal):
                continue
            self.last = f"{time.strftime('%H:%M')} {signal.kind}: {signal.text[:60]}"
            if not self.paused:
                self.deliver(signal)

    def run(self):
        while not self.stopping.is_set():
            try:
                self.step()
            except OSError as error:
                self.status = f"error reading the chat log: {error}"
            self.stopping.wait(self.poll)


def make_icon_image(color):
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=color)
    draw.ellipse((20, 20, 44, 44), fill=(255, 255, 255, 255))
    draw.ellipse((27, 27, 37, 37), fill=(20, 20, 20, 255))
    return image


def run_tray(config):
    import pystray

    watching = make_icon_image((40, 160, 90, 255))
    idle = make_icon_image((120, 120, 120, 255))
    icon = pystray.Icon("Lookout", idle, "Lookout")

    def deliver(signal):
        sent, detail = notify.send(config, signal)
        icon.notify(signal.text[:200] + ("" if sent else f"\n(phone: {detail})"), notify.TITLES.get(signal.kind, "Lookout"))

    watcher = Watcher(config, deliver)

    def refresh():
        while not watcher.stopping.is_set():
            icon.icon = watching if watcher.status == "watching" else idle
            icon.title = f"Lookout: {watcher.status}"[:127]
            icon.update_menu()
            watcher.stopping.wait(2)

    def toggle_pause(_icon, _item):
        watcher.paused = not watcher.paused

    def test_alert(_icon, _item):
        deliver(chatlog.Signal("companion", "test", "Phone alerts from the Lookout companion work."))

    def open_logs(_icon, _item):
        if watcher.path:
            os.startfile(watcher.path.parent)

    def quit_app(_icon, _item):
        watcher.stopping.set()
        icon.stop()

    icon.menu = pystray.Menu(
        pystray.MenuItem(lambda _item: f"Status: {watcher.status}", None, enabled=False),
        pystray.MenuItem(lambda _item: f"Last: {watcher.last}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Pause alerts", toggle_pause, checked=lambda _item: watcher.paused),
        pystray.MenuItem("Send test alert", test_alert),
        pystray.MenuItem("Open chat log folder", open_logs),
        pystray.MenuItem("Quit", quit_app),
    )
    threading.Thread(target=watcher.run, daemon=True).start()
    threading.Thread(target=refresh, daemon=True).start()
    icon.run()


def run_console(config):
    def deliver(signal):
        sent, detail = notify.send(config, signal)
        print(f"{signal.kind}: {signal.text}  [{detail}]", flush=True)

    watcher = Watcher(config, deliver)
    shown = None
    try:
        while True:
            watcher.step()
            if watcher.status != shown:
                shown = watcher.status
                print(f"{shown}: {watcher.path}", flush=True)
            time.sleep(watcher.poll)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lookout companion")
    parser.add_argument("--console", action="store_true", help="print alerts in a terminal, no tray icon")
    parser.add_argument("--test-push", action="store_true", help="send one test alert to your phone and exit")
    args = parser.parse_args(argv)
    config = notify.load_config()
    if args.test_push:
        sent, detail = notify.send(config, chatlog.Signal("companion", "test", "Phone alerts from the Lookout companion work."))
        print(detail)
        return 0 if sent else 1
    if args.console:
        run_console(config)
    else:
        run_tray(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
