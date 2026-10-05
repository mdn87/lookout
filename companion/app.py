"""Lookout companion: a tray icon that reads alerts from the addon's screenshots (or the chat
log) and sends them to your phone.

    pythonw -m companion.app            tray icon (start-companion.cmd does this)
    python -m companion.app --console   print alerts in a terminal instead, no tray
    python -m companion.app --test-push send one test alert to your phone and exit
    python -m companion.app --ask "..." ask the assistant one question, push the answer, exit
"""
import argparse
import os
import threading
import time
from pathlib import Path

from . import assistant, chatlog, notify


def answer(question, show, config_loader=notify.load_config, ask=assistant.ask):
    """Ask the assistant one "help" question and deliver the reply like any other alert.
    show(signals, sent, detail) presents it locally. Runs on its own thread, since an answer
    can take a minute and the watcher must keep reading screenshots meanwhile."""
    config = config_loader()
    text, detail = ask(config, question.text)
    reply = chatlog.Signal(question.char, "answer", text or f"No answer. {detail}")
    sent, detail = notify.send(config, reply)
    show([reply], sent, detail)


def split_questions(signals):
    """(questions, the rest): "help" alerts go to the assistant instead of straight to the phone."""
    questions = [s for s in signals if s.kind == "help"]
    return questions, [s for s in signals if s.kind != "help"]


def start_answers(questions, show):
    for question in questions:
        threading.Thread(target=answer, args=(question, show), daemon=True).start()


class Watcher:
    """Polls the Screenshots folders and the chat log on a thread and hands each batch of new
    alerts to deliver(signals, dropped)."""

    def __init__(self, config, deliver, poll=1.0):
        self.config, self.deliver, self.poll = config, deliver, poll
        self.paused = False
        self.status = "starting"
        self.last = "nothing yet"
        self.path = None
        self.follower = None
        self.dedupe = chatlog.Deduper()
        self.folders = None
        self.stopping = threading.Event()

    def choose_log(self):
        if self.config.get("chat_log"):
            return Path(self.config["chat_log"])
        logs = chatlog.find_chat_logs()
        return logs[0] if logs else None

    def hand_over(self, signals, dropped=0):
        first = signals[0]
        more = f" (+{len(signals) - 1})" if len(signals) > 1 else ""
        self.last = f"{time.strftime('%H:%M')} {first.kind}: {first.text[:60]}{more}"
        if not self.paused:
            self.deliver(signals, dropped)

    def step_screenshots(self):
        """Read new screenshots; a decoded Lookout screenshot is deleted unless keep_screenshots."""
        from . import screenshots   # needs zxing-cpp, which the chat-log route doesn't
        if self.folders is None:
            dirs = self.config.get("screenshot_dirs")
            dirs = [Path(d) for d in dirs] if dirs is not None else screenshots.find_screenshot_dirs()
            self.folders = [screenshots.Folder(d) for d in dirs]
        for folder in self.folders:
            for path, shot in folder.poll():
                if not shot:
                    continue
                self.hand_over(list(shot.signals), shot.dropped)
                if not self.config.get("keep_screenshots"):
                    try:
                        path.unlink()
                    except OSError:
                        pass
        return bool(self.folders)

    def step_chat_log(self):
        """Find the log if needed, read new lines, deliver signals. Returns a problem or None."""
        path = self.choose_log()
        if path != self.path:
            self.path, self.follower = path, chatlog.Follower(path) if path else None
        if not self.follower:
            return "no WoW install found"
        if not self.path.exists():
            return "waiting for the chat log (log in with the addon, or type /chatlog)"
        for line in self.follower.poll():
            signal = chatlog.parse(line)
            if signal and self.dedupe.fresh(signal):
                self.hand_over([signal])
        return None

    def step(self):
        """One poll of every source."""
        watching_shots = self.step_screenshots()
        problem = self.step_chat_log()
        if self.paused:
            self.status = "paused"
        elif watching_shots or not problem:
            self.status = "watching"
        else:
            self.status = problem

    def run(self):
        while not self.stopping.is_set():
            try:
                self.step()
            except OSError as error:
                self.status = f"error reading game files: {error}"
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

    def show(signals, sent, detail, dropped=0):
        title, message, _ = notify.compose(signals, dropped)
        icon.notify(message[:200] + ("" if sent else f"\n(phone: {detail})"), title)

    def deliver(signals, dropped=0):
        questions, signals = split_questions(signals)
        start_answers(questions, show)
        if not signals:
            return
        sent, detail = notify.send(notify.load_config(), *signals, dropped=dropped)   # re-read so new keys apply without a restart
        show(signals, sent, detail, dropped)

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
        deliver([chatlog.Signal("companion", "test", "Phone alerts from the Lookout companion work.")])

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
    def show(signals, sent, detail):
        for signal in signals:
            print(f"{signal.kind}: {signal.text}", flush=True)
        print(f"  [{detail}]", flush=True)

    def deliver(signals, dropped=0):
        questions, signals = split_questions(signals)
        start_answers(questions, show)
        if not signals:
            return
        sent, detail = notify.send(notify.load_config(), *signals, dropped=dropped)   # re-read so new keys apply without a restart
        show(signals, sent, detail)

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
    parser.add_argument("--ask", metavar="QUESTION", help="ask the assistant one question, push the answer, and exit")
    args = parser.parse_args(argv)
    config = notify.load_config()
    if args.test_push:
        sent, detail = notify.send(config, chatlog.Signal("companion", "test", "Phone alerts from the Lookout companion work."))
        print(detail)
        return 0 if sent else 1
    if args.ask:
        outcome = {}

        def show(signals, sent, detail):
            print(f"{signals[0].text}\n  [{detail}]")
            outcome["sent"] = sent

        answer(chatlog.Signal("companion", "help", args.ask), show)
        return 0 if outcome.get("sent") else 1
    if args.console:
        run_console(config)
    else:
        run_tray(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
