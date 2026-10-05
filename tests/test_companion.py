import json

from companion import assistant, chatlog, notify
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
    watcher = Watcher({"chat_log": str(log), "screenshot_dirs": []}, lambda signals, dropped=0: got.extend(signals))
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
    watcher = Watcher({"chat_log": str(tmp_path / "WoWChatLog.txt"), "screenshot_dirs": []}, lambda *_: None)
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


def test_one_push_carries_a_batch_and_buzzes_for_urgent_kinds():
    one = notify.compose([chatlog.Signal("Yizzity", "whisper", "Bob: hi")])
    assert one == ("Whisper (Yizzity)", "Bob: hi", 0)
    title, message, priority = notify.compose(
        [chatlog.Signal("Yizzity", "whisper", "Bob: hi"), chatlog.Signal("Yizzity", "queue", "Dungeon ready")], dropped=3)
    assert title == "2 alerts (Yizzity)" and priority == 1
    assert message.splitlines() == ["Whisper: Bob: hi", "Queue ready: Dungeon ready", "(+3 older alerts dropped by the rate limit)"]


class FakeReply:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_assistant_needs_an_endpoint_and_a_model():
    text, detail = assistant.ask({}, "where am I", environ={})
    assert text is None and detail.startswith("no assistant yet")


def test_assistant_posts_the_question_and_returns_the_answer():
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return FakeReply({"choices": [{"message": {"content": "  Type /script print(GetRealmName())  "}}]})

    config = {"assistant": {"url": "http://gw/v1/", "key": "k", "model": "m", "timeout": 7}}
    text, detail = assistant.ask(config, "which realm? [Yizzity, Whitemane]", opener=opener, environ={})
    assert text == "Type /script print(GetRealmName())" and detail == "m answered"
    assert seen["url"] == "http://gw/v1/chat/completions" and seen["auth"] == "Bearer k" and seen["timeout"] == 7
    assert seen["body"]["model"] == "m" and seen["body"]["messages"][1]["content"] == "which realm? [Yizzity, Whitemane]"


def test_assistant_falls_back_to_the_environment():
    env = {"OMNIROUTE_BASE_URL": "http://gw/v1", "OMNIROUTE_API_KEY": "k", "LOOKOUT_AI_MODEL": "m"}
    assert assistant.settings({}, env) == ("http://gw/v1", "k", "m", 60)
    assert assistant.settings({"assistant": {"url": "http://mine"}}, env)[0] == "http://mine"


def test_assistant_reports_a_rejection_and_a_dead_endpoint():
    import io
    import urllib.error

    def rejects(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"error": {"message": "key not allowed"}}'))

    def dead(request, timeout):
        raise OSError("connection refused")

    config = {"assistant": {"url": "http://gw/v1", "model": "m"}}
    assert assistant.ask(config, "q", opener=rejects, environ={}) == (None, "assistant rejected the question (403): key not allowed")
    assert assistant.ask(config, "q", opener=dead, environ={}) == (None, "assistant request failed: connection refused")


def test_answer_delivers_the_reply_as_an_alert(monkeypatch):
    from companion import app
    pushed, shown = [], []
    monkeypatch.setattr(notify, "send", lambda config, *signals, dropped=0: (pushed.append(signals) or True, "ok"))
    question = chatlog.Signal("Yizzity", "help", "which realm? [..]")
    app.answer(question, lambda signals, sent, detail: shown.append((signals, sent, detail)),
               config_loader=dict, ask=lambda config, text: ("Use /script print(GetRealmName())", "m answered"))
    reply = chatlog.Signal("Yizzity", "answer", "Use /script print(GetRealmName())")
    assert pushed == [(reply,)] and shown == [([reply], True, "ok")]

    app.answer(question, lambda signals, sent, detail: shown.append(signals[0].text),
               config_loader=dict, ask=lambda config, text: (None, "assistant request failed: x"))
    assert shown[-1] == "No answer. assistant request failed: x"


def test_questions_are_split_from_ordinary_alerts():
    from companion.app import split_questions
    q, w = chatlog.Signal("Y", "help", "?"), chatlog.Signal("Y", "whisper", "hi")
    assert split_questions([w, q]) == ([q], [w])
