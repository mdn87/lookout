"""Load the Lookout addon into Lua 5.1 (the game's Lua version) against a stubbed client
API and fire events at it."""
from pathlib import Path

import pytest
from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon" / "Lookout"


def files_in_toc():
    lines = (ADDON / "Lookout.toc").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("##")]


def start(transport=None):
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute((Path(__file__).parent / "wow_stub.lua").read_text(encoding="utf-8"))
    T = lua.globals().T
    ns = lua.table()
    for name in files_in_toc():
        T.load(ns, name, (ADDON / name).read_text(encoding="utf-8"))
    T.fire("ADDON_LOADED", "Lookout")
    T.fire("PLAYER_LOGIN")
    T.flush()
    if transport:
        lua.globals().LookoutDB.transport = transport
    return lua, T


@pytest.fixture
def game():
    """The chat-log route, where each phone alert is one whisper these tests can read."""
    return start("chat")


@pytest.fixture
def shot_game():
    """The default screenshot route."""
    return start()


def sent(T):
    return [(T.sent[i].msg, T.sent[i].kind, T.sent[i].target) for i in range(1, len(T.sent) + 1)]


def screen(T):
    return [T.screen[i] for i in range(1, len(T.screen) + 1)]


def signals(T):
    return [msg for msg, kind, target in sent(T) if kind == "WHISPER"]


def test_login_turns_on_the_chat_log(game):
    lua, T = game
    assert T.logging is True
    assert lua.globals().LookoutDB.alerts.whisper == "phone"


@pytest.mark.parametrize("suffix,expected", [
    ("Surname", "Example-Surname"),
    ("OtherRealm", "Example-OtherRealm"),
    ("", "Example"),
    (None, "Example"),
])
def test_signal_whispers_to_the_complete_player_name(game, suffix, expected):
    lua, T = game
    T.name_suffix = suffix
    lua.execute('function UnitName() return "Example", T.name_suffix end')
    T.slash("test")
    assert sent(T) == [
        (f"LOOKOUT :: {expected} :: test :: Lookout test alert", "WHISPER", expected)
    ]


def test_watched_whisper_goes_to_the_phone_once_per_cooldown(game):
    lua, T = game
    T.slash("add Saalora")
    T.fire("CHAT_MSG_WHISPER", "hi! sorry was afk", "Saalora-Zephras")
    T.fire("CHAT_MSG_WHISPER", "still there?", "Saalora-Zephras")
    assert sent(T) == [("LOOKOUT :: Yizzity :: whisper :: Saalora-Zephras: hi! sorry was afk", "WHISPER", "Yizzity")]
    T.now = T.now + 61
    T.fire("CHAT_MSG_WHISPER", "hello?", "Saalora")
    assert len(signals(T)) == 2


def test_own_signal_does_not_loop_and_is_hidden(game):
    lua, T = game
    T.slash("add Yizzity")
    T.fire("CHAT_MSG_WHISPER", "LOOKOUT :: Yizzity :: test :: x", "Yizzity")
    assert sent(T) == []
    assert T.filters.CHAT_MSG_WHISPER(None, "CHAT_MSG_WHISPER", "LOOKOUT :: Yizzity :: test :: x") is True
    assert not T.filters.CHAT_MSG_WHISPER(None, "CHAT_MSG_WHISPER", "normal whisper")


def test_watched_player_seen_in_general(game):
    lua, T = game
    T.slash("add saalora")
    T.fire("CHAT_MSG_CHANNEL", "LF healer", "Saalora", "Common", "1. General - Zephras Isle")
    assert signals(T) == ["LOOKOUT :: Yizzity :: seen :: Saalora in 1. General - Zephras Isle: LF healer"]


def test_keyword_and_links_are_made_plain(game):
    lua, T = game
    T.slash("word add sword")
    T.fire("CHAT_MSG_CHANNEL", "WTS |cff0070dd|Hitem:123::|h[Blue Sword]|h|r cheap", "Bob", "", "2. Trade")
    (message,) = signals(T)
    assert "|" not in message
    assert message == "LOOKOUT :: Yizzity :: keyword :: Bob said sword: WTS [Blue Sword] cheap"


def test_away_whisper_and_mention_keep_you_away(game):
    lua, T = game
    T.afk = True
    T.fire("CHAT_MSG_WHISPER", "you there?", "Stranger")
    T.afk = False                         # the whisper to yourself cleared the away flag
    T.flush()
    assert ("", "AFK", None) in sent(T)
    assert T.afk is True
    T.fire("CHAT_MSG_SAY", "yizzity come help", "Other")
    assert signals(T)[-1] == "LOOKOUT :: Yizzity :: afk :: Other mentioned you: yizzity come help"


def test_not_away_means_no_away_alerts(game):
    lua, T = game
    T.fire("CHAT_MSG_WHISPER", "hey", "Stranger")
    T.fire("CHAT_MSG_SAY", "yizzity hi", "Other")
    assert sent(T) == []


def test_invite_queue_and_ready_check(game):
    lua, T = game
    T.fire("PARTY_INVITE_REQUEST", "Tank")
    T.fire("LFG_PROPOSAL_SHOW")
    T.bg[1] = "confirm"
    T.fire("UPDATE_BATTLEFIELD_STATUS", 1)
    T.fire("UPDATE_BATTLEFIELD_STATUS", 1)   # fires again while the window is open
    T.fire("READY_CHECK", "Leader")
    kinds = [message.split(" :: ")[2] for message in signals(T)]
    assert kinds == ["invite", "queue", "queue", "readycheck"]


def test_alert_modes(game):
    lua, T = game
    T.slash("alert invite screen")
    T.fire("PARTY_INVITE_REQUEST", "Tank")
    assert sent(T) == [] and screen(T) == ["Tank invited you to a group"]
    T.slash("alert invite off")
    T.fire("PARTY_INVITE_REQUEST", "Healer")
    assert len(screen(T)) == 1
    T.slash("phone off")
    T.fire("READY_CHECK", "Leader")
    assert sent(T) == []


def test_long_messages_are_cut_to_fit(game):
    lua, T = game
    T.slash("add bob")
    T.fire("CHAT_MSG_WHISPER", "x" * 400, "Bob")
    assert len(signals(T)[0]) == 250


def set_quests(lua, T, quests):
    T.quests = lua.table_from([lua.table_from(q) for q in quests])


def objectives(lua, *items):
    return lua.table_from([lua.table_from({"text": text, "finished": done}) for text, done in items])


def test_quest_ready_alert_only_on_change(game):
    lua, T = game
    set_quests(lua, T, [{"header": "Zephras Isle"},
                        {"id": 7, "title": "Boar Hunt", "complete": False, "objectives": objectives(lua, ("Boars slain: 3/5", False))}])
    T.fire("QUEST_LOG_UPDATE")
    T.flush()
    assert screen(T) == []
    set_quests(lua, T, [{"header": "Zephras Isle"},
                        {"id": 7, "title": "Boar Hunt", "complete": True, "objectives": objectives(lua, ("Boars slain: 5/5", True))}])
    T.fire("QUEST_LOG_UPDATE")
    T.fire("QUEST_LOG_UPDATE")
    T.flush()
    assert screen(T) == ["Boar Hunt is ready to turn in"]
    assert sent(T) == []                     # quest alerts stay on screen by default


def test_quest_panel_lists_progress(game):
    lua, T = game
    set_quests(lua, T, [{"header": "Zephras Isle"},
                        {"id": 7, "title": "Boar Hunt", "complete": False, "objectives": objectives(lua, ("Boars slain: 3/5", False))},
                        {"id": 8, "title": "Letter Home", "complete": True, "objectives": objectives(lua)}])
    T.slash("quests")
    panel = T.frames[len(T.frames)]
    assert panel.shown
    text = panel.text.text
    assert "Boar Hunt" in text and "Boars slain: 3/5" in text and "Letter Home - turn in" in text
    assert lua.globals().LookoutDB.questPanel is True


def test_classic_quest_log(game):
    lua, T = game
    lua.execute("""
        C_QuestLog = nil
        local log = { {"Zephras Isle", true}, {"Boar Hunt", false, 1, 7} }
        function GetNumQuestLogEntries() return #log end
        function GetQuestLogTitle(i) local e = log[i]; return e[1], 1, nil, e[2], nil, e[3], nil, e[4] end
        function GetNumQuestLeaderBoards(i) return i == 2 and 1 or 0 end
        function GetQuestLogLeaderBoard() return "Boars slain: 5/5", "monster", true end
    """)
    quests = lua.globals().LookoutAPI.Quests()
    quest = quests[1]
    assert (quest.id, quest.title, quest.zone, quest.complete) == (7, "Boar Hunt", "Zephras Isle", True)
    assert quest.objectives[1].done is True


def test_way_uses_tomtom_with_the_game_waypoint(game):
    lua, T = game
    set_quests(lua, T, [{"id": 7, "title": "Boar Hunt", "complete": False, "objectives": objectives(lua)}])
    lua.execute("""
        C_QuestLog.GetNextWaypoint = function(id) if id == 7 then return 1411, 0.42, 0.61 end end
        TomTom = { AddWaypoint = function(self, map, x, y, opts) T.waypoints[#T.waypoints + 1] = { map, x, y, opts.title } end }
    """)
    T.slash("way")
    point = T.waypoints[1]
    assert (point[1], point[2], point[3], point[4]) == (1411, 0.42, 0.61, "Boar Hunt")
    assert "42.0, 61.0" in T.printed[len(T.printed)]


def test_other_addons_can_add_a_location_source(game):
    lua, T = game
    set_quests(lua, T, [{"id": 9, "title": "Lost Ring", "complete": False, "objectives": objectives(lua)}])
    lua.execute("""
        LookoutAPI.RegisterProvider({ name = "mydata", locate = function(id) if id == 9 then return 1, 0.5, 0.5 end end })
    """)
    T.slash("way 9")
    assert "from mydata" in T.printed[len(T.printed)]


def test_help_sends_the_question_with_the_characters_whereabouts(game):
    lua, T = game
    T.slash("help how do I see which realm I am on?")
    assert signals(T) == [
        "LOOKOUT :: Yizzity :: help :: how do I see which realm I am on? "
        "[Yizzity lvl 23 Mage, Horde, Whitemane, The Barrens (The Crossroads), contested]"
    ]
    assert "answer goes to your phone" in T.printed[len(T.printed)]


def test_help_survives_a_client_without_zone_functions(game):
    lua, T = game
    lua.execute("GetZonePVPInfo = nil; GetSubZoneText = nil")
    T.slash("help where am I")
    assert signals(T) == ["LOOKOUT :: Yizzity :: help :: where am I [Yizzity lvl 23 Mage, Horde, Whitemane, The Barrens]"]


def test_help_alone_prints_the_command_list(game):
    lua, T = game
    T.slash("help")
    assert signals(T) == []
    assert any("/lo help" in T.printed[i] for i in range(1, len(T.printed) + 1))
