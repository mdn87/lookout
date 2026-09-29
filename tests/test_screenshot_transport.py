"""The screenshot route: the addon's rate-limited queue, and the companion reading the result."""
import pytest
from PIL import Image, ImageDraw
from lupa import lua51

from companion import screenshots
from companion.app import Watcher
from companion.chatlog import Signal
from test_addon import ADDON, sent, start


@pytest.fixture
def shots():
    lua, T = start()
    T.payloads = lua.table()
    lua.execute("""
        local encode = T.ns.qrcode
        T.ns.qrcode = function(text, ...) T.payloads[#T.payloads + 1] = text; return encode(text, ...) end
    """)
    return lua, T


def payloads(T):
    return [T.payloads[i] for i in range(1, len(T.payloads) + 1)]


def emit(lua, T, kind, text, key=None):
    lua.globals().emit_args = lua.table_from([kind, text, key or text])
    lua.execute("T.ns.emit(emit_args[1], emit_args[2], emit_args[3])")


def qr_frame(T):
    return next(T.frames[i] for i in range(1, len(T.frames) + 1) if T.frames[i].events["SCREENSHOT_SUCCEEDED"])


def save(T):
    """Let the render delay pass and have the game report the screenshot saved."""
    T.advance(1)
    T.fire("SCREENSHOT_SUCCEEDED")


def rasterize(T, size=(1920, 1080)):
    """Paint the addon's QR frame the way the game would, one frame unit per pixel."""
    frame = qr_frame(T)
    image = Image.new("RGB", size, "gray")
    draw = ImageDraw.Draw(image)
    left, top = 16, size[1] - 16 - frame.w
    draw.rectangle((left, top, left + frame.w - 1, top + frame.h - 1), fill="white")
    for i in range(1, len(frame.textures) + 1):
        texture = frame.textures[i]
        if texture.shown and texture.color == 0:
            x, y = left + texture.x, top - texture.y
            draw.rectangle((x, y, x + texture.w - 1, y + texture.h - 1), fill="black")
    return image


def qr_image(payload, path):
    """A screenshot carrying payload, drawn with the addon's own encoder."""
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    ok, matrix = lua.execute((ADDON / "vendor/qrencode.lua").read_text(encoding="utf-8")).qrcode(payload, 2)
    assert ok
    image = Image.new("RGB", (1920, 1080), "gray")
    draw = ImageDraw.Draw(image)
    side = (len(matrix) + 8) * 6
    left, top = 16, 1080 - 16 - side
    draw.rectangle((left, top, left + side - 1, top + side - 1), fill="white")
    for x in range(1, len(matrix) + 1):
        for y in range(1, len(matrix) + 1):
            if matrix[x][y] > 0:
                px, py = left + (x + 3) * 6, top + (y + 3) * 6
                draw.rectangle((px, py, px + 5, py + 5), fill="black")
    image.save(path, quality=70)
    return path


def test_screenshot_is_the_default_and_the_companion_reads_it(shots, tmp_path):
    lua, T = shots
    T.slash("test")
    assert sent(T) == [] and T.screenshots is None
    assert qr_frame(T).shown
    T.advance(1)
    assert T.screenshots == 1
    path = tmp_path / "WoWScrnShot_1.jpg"
    rasterize(T).save(path, quality=70)
    shot = screenshots.decode(path)
    assert shot.char == "Yizzity" and shot.seq == 1
    assert shot.signals == (Signal("Yizzity", "test", "Lookout test alert"),)
    T.fire("SCREENSHOT_SUCCEEDED")
    assert not qr_frame(T).shown


def test_alerts_between_screenshots_wait_and_go_together(shots):
    lua, T = shots
    emit(lua, T, "whisper", "Bob: one")
    save(T)
    T.advance(2)
    emit(lua, T, "whisper", "Carl: two")
    emit(lua, T, "seen", "Dana in General")
    T.advance(16)
    assert len(payloads(T)) == 1               # 19 seconds after the first, the gap is 20
    T.advance(1)
    assert payloads(T)[1].split("\n")[2:] == ["whisper\tCarl: two", "seen\tDana in General"]
    assert T.screenshots == 1                  # the second is drawn, its screenshot a second later
    save(T)
    assert T.screenshots == 2


def test_urgent_alerts_wait_less_and_go_first(shots):
    lua, T = shots
    emit(lua, T, "whisper", "Bob: one")
    save(T)
    T.advance(1)
    emit(lua, T, "whisper", "Carl: two")
    emit(lua, T, "invite", "Tank invited you to a group")
    T.advance(2)
    assert len(payloads(T)) == 1
    T.advance(1)                               # 5 seconds after the first screenshot
    assert payloads(T)[1].split("\n")[2:] == ["invite\tTank invited you to a group", "whisper\tCarl: two"]


def test_hourly_cap(shots):
    lua, T = shots
    T.slash("rate 5 2")
    emit(lua, T, "whisper", "one")
    save(T)
    T.advance(4)
    emit(lua, T, "whisper", "two")
    save(T)
    T.advance(10)
    emit(lua, T, "whisper", "three")
    T.advance(3000)
    assert len(payloads(T)) == 2
    T.advance(3600 - 3014)                     # an hour after the first screenshot
    assert payloads(T)[2].endswith("whisper\tthree")
    assert "every 5s" in T.printed[len(T.printed)]


def test_failed_screenshots_are_retried_then_given_up(shots):
    lua, T = shots
    emit(lua, T, "whisper", "Bob: one")
    for _ in range(3):
        T.advance(1)
        T.fire("SCREENSHOT_FAILED")
        T.advance(19)
    assert [p.split("\n")[2] for p in payloads(T)] == ["whisper\tBob: one"] * 3
    T.advance(100)
    assert len(payloads(T)) == 3


def test_a_flood_is_capped_counted_and_fits_the_corner(shots, tmp_path):
    lua, T = shots
    emit(lua, T, "whisper", "first")
    save(T)
    for n in range(25):
        emit(lua, T, "keyword", f"{n:02d} " + "x" * 140)
    T.advance(20)
    payload = payloads(T)[1]
    assert len(payload.encode()) <= 360 and payload.endswith("dropped\t5")
    assert qr_frame(T).w <= 486                # 73 modules and the quiet zone, inside the 512 crop
    path = tmp_path / "flood.jpg"
    rasterize(T).save(path, quality=70)
    shot = screenshots.decode(path)
    assert shot.dropped == 5 and [s.text[:2] for s in shot.signals] == ["05", "06"]
    save(T)
    T.advance(20)
    assert "dropped" not in payloads(T)[2]     # the count went out once


def test_ordinary_alerts_wait_out_a_fight(shots):
    lua, T = shots
    T.combat = True
    emit(lua, T, "whisper", "Bob: one")
    T.advance(60)
    assert payloads(T) == []
    T.combat = False
    T.fire("PLAYER_REGEN_ENABLED")
    assert payloads(T)[0].endswith("whisper\tBob: one")
    save(T)
    T.combat = True
    T.advance(20)
    emit(lua, T, "whisper", "Carl: two")
    emit(lua, T, "readycheck", "Leader started a ready check")
    # Urgent alerts don't wait, and take the waiting ones along.
    assert payloads(T)[1].split("\n")[2:] == ["readycheck\tLeader started a ready check", "whisper\tCarl: two"]
    save(T)
    T.afk = True                               # nobody at the keyboard to be in the way of
    T.advance(20)
    emit(lua, T, "whisper", "Dana: three")
    assert payloads(T)[2].endswith("whisper\tDana: three")


def test_long_text_is_cut_on_a_character_boundary(shots):
    lua, T = shots
    emit(lua, T, "whisper", "é" * 150)
    assert payloads(T)[0].split("\n")[2] == "whisper\t" + "é" * 100


def test_transport_switches_to_the_chat_log(shots):
    lua, T = shots
    T.slash("transport chat")
    T.slash("test")
    assert sent(T) == [("LOOKOUT :: Yizzity :: test :: Lookout test alert", "WHISPER", "Yizzity")]
    assert payloads(T) == []


def test_parse_accepts_only_lookout_payloads():
    shot = screenshots.parse("LOOKOUT-2 7\nYizzity\nwhisper\tBob: hi\tthere\ndropped\t2")
    assert shot == screenshots.Shot("Yizzity", 7, (Signal("Yizzity", "whisper", "Bob: hi\tthere"),), 2)
    assert screenshots.parse("LOOKOUT-PROBE-1:abc") is None
    assert screenshots.parse("LOOKOUT-2\nYizzity\nwhisper\thi") is None
    assert screenshots.parse("LOOKOUT-2 7\nYizzity\ndropped\t2") is None


def test_watcher_sends_and_deletes_lookout_screenshots_only(tmp_path):
    old = qr_image("LOOKOUT-2 1\nYizzity\nwhisper\told", tmp_path / "WoWScrnShot_0.jpg")
    got = []
    watcher = Watcher({"chat_log": str(tmp_path / "none.txt"), "screenshot_dirs": [str(tmp_path)]},
                      lambda signals, dropped=0: got.append(([s.text for s in signals], dropped)))
    watcher.step()
    assert watcher.status == "watching" and got == []
    mine = qr_image("LOOKOUT-2 2\nYizzity\nqueue\tDungeon ready\ndropped\t1", tmp_path / "WoWScrnShot_1.jpg")
    theirs = tmp_path / "WoWScrnShot_2.jpg"
    Image.new("RGB", (800, 600), "blue").save(theirs)
    watcher.step()
    assert got == [(["Dungeon ready"], 1)]
    assert not mine.exists() and theirs.exists() and old.exists()
    assert "queue: Dungeon ready" in watcher.last


def test_watcher_waits_for_a_screenshot_still_being_written(tmp_path):
    whole = qr_image("LOOKOUT-2 3\nYizzity\ninvite\tTank", tmp_path / "whole.jpg").read_bytes()
    shots_dir = tmp_path / "Screenshots"
    got = []
    watcher = Watcher({"chat_log": str(tmp_path / "none.txt"), "screenshot_dirs": [str(shots_dir)],
                       "keep_screenshots": True}, lambda signals, dropped=0: got.extend(signals))
    watcher.step()                             # the folder doesn't exist until the first screenshot
    shots_dir.mkdir()
    path = shots_dir / "WoWScrnShot_3.jpg"
    path.write_bytes(whole[: len(whole) // 2])
    watcher.step()
    assert got == []
    path.write_bytes(whole)
    watcher.step()
    assert [s.text for s in got] == ["Tank"] and path.exists()
