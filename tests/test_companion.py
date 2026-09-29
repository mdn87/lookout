from companion import chatlog, notify
from companion.app import Watcher

SELF_IN = "9/28 20:10:06.612  [Yizzity] whispers: LOOKOUT :: Yizzity :: whisper :: Saalora-Zephras: hi"
SELF_OUT = "9/28 20:10:06.612  To [Yizzity]: LOOKOUT :: Yizzity :: whisper :: Saalora-Zephras: hi"


def test_parse_signal_lines_only():
    assert chatlog.parse(SELF_IN) == chatlog.Signal("Yizzity", "whisper", "Saalora-Zephras: hi")
    assert chatlog.parse(SELF_OUT) == chatlog.parse(SELF_IN)
    assert chatlog.parse("9/28 20:10:07.000  [Bob] whispers: hello") is None
    assert chatlog.parse("LOOKOUT :: Yizzity :: queue :: Dungeon group found - accept now").kind == "queue"


def test_dedupe_drops_the_echo_but_not_a_later_repeat():
    now = [0.0]
    dedupe = chatlog.Deduper(window=10, clock=lambda: now[0])
    signal = chatlog.parse(SELF_IN)
    assert dedupe.fresh(signal) and not dedupe.fresh(chatlog.parse(SELF_OUT))
    now[0] = 11
    assert dedupe.fresh(signal)


def test_follower_reads_appends_and_survives_truncation(tmp_path):
    log = tmp_path / "WoWChatLog.txt"
    log.write_text("old line\n", encoding="utf-8")
    follower = chatlog.Follower(log)
    assert follower.poll() == []
    with log.open("a", encoding="utf-8") as handle:
        handle.write("new one\nhalf")
    assert follower.poll() == ["new one"]
    with log.open("a", encoding="utf-8") as handle:
        handle.write(" done\n")
    assert follower.poll() == ["half done"]
    log.write_text("fresh\n", encoding="utf-8")
    assert follower.poll() == ["fresh"]


def test_missing_log_is_waited_for(tmp_path):
    follower = chatlog.Follower(tmp_path / "WoWChatLog.txt")
    assert follower.poll() == []


def test_find_chat_logs_lists_each_game_version(tmp_path):
    for flavor in ("_retail_", "_classic_beta_"):
        (tmp_path / flavor / "Logs").mkdir(parents=True)
    (tmp_path / "_classic_beta_" / "Logs" / "WoWChatLog.txt").write_text("x\n")
    found = chatlog.find_chat_logs([str(tmp_path)])
    assert {path.parent.parent.name for path in found} == {"_retail_", "_classic_beta_"}


def test_watcher_delivers_once_and_respects_pause(tmp_path):
    log = tmp_path / "WoWChatLog.txt"
    log.write_text("", encoding="utf-8")
    got = []
    watcher = Watcher({"chat_log": str(log)}, got.append)
    watcher.step()
    assert watcher.status == "watching"
    with log.open("a", encoding="utf-8") as handle:
        handle.write(SELF_OUT + "\n" + SELF_IN + "\n")
    watcher.step()
    assert [signal.kind for signal in got] == ["whisper"]
    watcher.paused = True
    with log.open("a", encoding="utf-8") as handle:
        handle.write("LOOKOUT :: Yizzity :: invite :: Tank invited you to a group\n")
    watcher.step()
    assert len(got) == 1 and watcher.status == "paused" and "invite" in watcher.last


def test_watcher_waits_for_a_log_that_does_not_exist_yet(tmp_path):
    watcher = Watcher({"chat_log": str(tmp_path / "WoWChatLog.txt")}, lambda signal: None)
    watcher.step()
    assert watcher.status.startswith("waiting for the chat log")


def test_send_without_keys_says_so():
    sent, detail = notify.send({}, chatlog.Signal("x", "test", "t"))
    assert not sent and detail.startswith("no Pushover keys yet")


def test_send_treats_example_placeholders_as_missing():
    placeholders = {"pushover": {"token": "your-pushover-application-token", "user": "your-pushover-user-key"}}
    sent, detail = notify.send(placeholders, chatlog.Signal("x", "test", "t"))
    assert not sent and detail.startswith("no Pushover keys yet")


def test_tray_image_builds():
    from companion.app import make_icon_image
    assert make_icon_image((1, 2, 3, 255)).size == (64, 64)
