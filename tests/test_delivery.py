"""Delivery outcomes: a batch the phone didn't take waits, with its screenshot, in a pending file
that survives a restart, and is retried a bounded number of times. Mocks only: nothing is sent
and no game is needed."""
import json
import logging
from pathlib import Path

from test_screenshot_transport import qr_image

from companion import app, notify, outbox
from companion.app import Watcher
from companion.chatlog import Signal
from companion.outbox import Outbox
from companion.screenshots import Shot

WHISPER = Signal("Yizzity", "whisper", "Bob: hi")
OK, FAILED = "Pushover answered 200", "Pushover send failed: offline"


class Clock:
    now = 1_800_000_000.0

    def __call__(self):
        return self.now


class OneShot:
    """A Screenshots folder that turns up one decoded Lookout screenshot, once."""

    def __init__(self, path, *signals):
        self.found = [(path, Shot("Yizzity", 1, signals))]

    def poll(self):
        found, self.found = self.found, []
        return found


class Phone:
    """A scripted deliver(): each call takes the next outcome, True for a push Pushover accepted.
    A call beyond the script fails the test, so a repeated send can't go unnoticed."""

    def __init__(self, *outcomes, screenshot=None):
        self.outcomes, self.screenshot, self.calls = list(outcomes), screenshot, []

    def __call__(self, signals, dropped=0, retry=False):
        there = self.screenshot.exists() if self.screenshot else None
        self.calls.append((list(signals), retry, there))
        sent = self.outcomes.pop(0)
        return sent, OK if sent else FAILED


class Icon:
    """pystray's Icon, as far as notifications go."""

    def __init__(self):
        self.shown = []

    def notify(self, message, title):
        self.shown.append((title, message))


def pending(tmp_path):
    return tmp_path / "state" / outbox.FILENAME


def saved(tmp_path):
    return json.loads(pending(tmp_path).read_text(encoding="utf-8"))["alerts"]


def watcher(tmp_path, deliver, clock, folder=None, **config):
    """A Watcher on the pending file, reading a fake folder or the Screenshots folders in config."""
    w = Watcher({"chat_log": str(tmp_path / "none.txt"), "screenshot_dirs": [], **config}, deliver,
                outbox=Outbox(pending(tmp_path), clock))
    if folder:
        w.folders = [folder]
    return w


def screenshot(tmp_path):
    path = tmp_path / "WoWScrnShot_1.jpg"
    path.write_bytes(b"never decoded: the folder is a fake")
    return path


def test_a_failed_send_keeps_the_screenshot_and_saves_the_alert(tmp_path):
    shot, clock, phone = screenshot(tmp_path), Clock(), Phone(False)
    w = watcher(tmp_path, phone, clock, OneShot(shot, WHISPER))
    w.step()
    assert len(phone.calls) == 1 and shot.exists()
    [entry] = saved(tmp_path)
    assert entry["signals"] == [{"char": "Yizzity", "kind": "whisper", "text": "Bob: hi"}]
    assert entry["screenshot"] == str(shot) and entry["attempts"] == 1 and entry["detail"] == FAILED
    clock.now += outbox.WAITS[0] - 1
    w.step()                                   # not before its wait is over
    assert len(phone.calls) == 1


def test_a_later_retry_delivers_and_only_then_deletes_the_screenshot(tmp_path):
    shot, clock = screenshot(tmp_path), Clock()
    phone = Phone(False, True, screenshot=shot)
    w = watcher(tmp_path, phone, clock, OneShot(shot, WHISPER))
    w.step()
    clock.now += outbox.WAITS[0]
    w.step()
    assert phone.calls == [([WHISPER], False, True), ([WHISPER], True, True)]
    assert not shot.exists() and saved(tmp_path) == []


def test_retries_stop_at_the_bound_keep_the_screenshot_and_say_so(tmp_path, caplog):
    shot, clock, icon = screenshot(tmp_path), Clock(), Icon()
    phone = Phone(*[False] * outbox.ATTEMPTS)
    w = watcher(tmp_path, phone, clock, OneShot(shot, WHISPER))
    tray = app.Toast(icon)
    logging.getLogger("lookout").addHandler(tray)
    try:
        w.step()
        for wait in outbox.WAITS:
            clock.now += wait
            w.step()
        clock.now += 24 * 3600
        w.step()
    finally:
        logging.getLogger("lookout").removeHandler(tray)
    assert len(phone.calls) == outbox.ATTEMPTS == 5
    assert saved(tmp_path) == [] and shot.exists()
    gave_up = f"Gave up on Whisper (Yizzity) after 5 tries: {FAILED}; its screenshot is kept at {shot}"
    assert gave_up in caplog.text
    assert icon.shown == [("Lookout", gave_up[:250])]   # the tray hears about the give-up, not each retry


def test_a_waiting_alert_survives_a_restart(tmp_path):
    shots, clock, first = tmp_path / "Screenshots", Clock(), Phone(False)
    shots.mkdir()
    before = watcher(tmp_path, first, clock, screenshot_dirs=[str(shots)])
    before.step()
    shot = qr_image("LOOKOUT-2 1\nYizzity\nwhisper\tBob: hi", shots / "WoWScrnShot_1.jpg")
    before.step()
    assert len(first.calls) == 1 and shot.exists()
    # Restart: a new watcher on the same pending file and Screenshots folder.
    phone = Phone(True, screenshot=shot)
    after = watcher(tmp_path, phone, clock, screenshot_dirs=[str(shots)])
    after.step()
    assert phone.calls == []                   # the image itself isn't read again, and the wait isn't over
    clock.now += outbox.WAITS[0]
    after.step()
    assert phone.calls == [([WHISPER], True, True)]
    assert not shot.exists() and saved(tmp_path) == []


def test_a_delivered_alert_is_not_sent_again_after_a_restart(tmp_path):
    shots, clock, first = tmp_path / "Screenshots", Clock(), Phone(True)
    shots.mkdir()
    before = watcher(tmp_path, first, clock, screenshot_dirs=[str(shots)], keep_screenshots=True)
    before.step()
    shot = qr_image("LOOKOUT-2 1\nYizzity\nwhisper\tBob: hi", shots / "WoWScrnShot_1.jpg")
    before.step()
    assert len(first.calls) == 1 and saved(tmp_path) == [] and shot.exists()
    phone = Phone()
    after = watcher(tmp_path, phone, clock, screenshot_dirs=[str(shots)], keep_screenshots=True)
    for _ in range(3):
        clock.now += outbox.WAITS[-1]
        after.step()
    assert phone.calls == []


def test_a_retry_resends_only_the_alerts_and_never_asks_the_assistant_again(tmp_path, monkeypatch):
    asked, pushed, shown, outcomes = [], [], [], [False, False, True]
    monkeypatch.setattr(app, "start_answers", lambda questions, show: asked.extend(questions))
    monkeypatch.setattr(notify, "load_config", dict)

    def send(config, *signals, dropped=0):
        pushed.append(signals)
        sent = outcomes.pop(0)
        return sent, OK if sent else FAILED

    monkeypatch.setattr(notify, "send", send)
    question, shot, clock = Signal("Yizzity", "help", "which realm?"), screenshot(tmp_path), Clock()
    deliver = app.deliverer(lambda signals, sent, detail, dropped=0: shown.append((signals, sent)))
    w = watcher(tmp_path, deliver, clock, OneShot(shot, question, WHISPER))
    w.step()
    for wait in outbox.WAITS[:2]:
        clock.now += wait
        w.step()
    assert asked == [question] and pushed == [(WHISPER,)] * 3
    assert shown == [([WHISPER], False), ([WHISPER], True)]   # a retry that fails again isn't shown
    assert not shot.exists() and saved(tmp_path) == []


def test_pause_holds_retries_without_using_them_up(tmp_path):
    shot, clock, phone = screenshot(tmp_path), Clock(), Phone(False, True)
    w = watcher(tmp_path, phone, clock, OneShot(shot, WHISPER))
    w.step()
    w.paused = True
    clock.now += outbox.WAITS[-1]
    w.step()
    assert len(phone.calls) == 1 and saved(tmp_path)[0]["attempts"] == 1
    w.paused = False
    w.step()
    assert len(phone.calls) == 2 and not shot.exists()


def test_the_pending_file_lives_outside_the_checkout():
    local = outbox.default_path({"LOCALAPPDATA": "C:/Users/me/AppData/Local"})
    assert local == Path("C:/Users/me/AppData/Local/Lookout/pending-alerts.json")
    xdg = outbox.default_path({"XDG_STATE_HOME": "/home/me/.local/state"})
    assert xdg == Path("/home/me/.local/state/lookout/pending-alerts.json")


def test_an_unreadable_pending_file_is_reported_and_not_fatal(tmp_path, caplog):
    path = tmp_path / outbox.FILENAME
    path.write_text("{not json", encoding="utf-8")
    assert len(Outbox(path)) == 0 and "Could not read pending alerts" in caplog.text
