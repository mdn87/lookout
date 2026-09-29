"""Round-trip the actual Lua encoder through JPEG and the cropped decoder."""
import pytest
from PIL import Image, ImageDraw
from lupa import lua51

from companion.screenshot_probe import decode
from test_addon import ADDON, game, sent


def test_actual_lua_qr_survives_jpeg_and_corner_crop(tmp_path):
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    encoder = lua.execute((ADDON / "vendor/qrencode.lua").read_text(encoding="utf-8"))
    ok, matrix = encoder.qrcode("LOOKOUT-PROBE-1:proof-123")
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
    path = tmp_path / "screenshot.jpg"
    image.save(path, quality=70)
    assert "proof-123" in decode(path, "proof-123").text
    with pytest.raises(ValueError, match="not found"):
        decode(path, "wrong-code")
    image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(path)
    with pytest.raises(ValueError, match="not found"):
        decode(path, "proof-123")


def test_probe_only_runs_explicitly_and_hides_on_completion(game):
    lua, T = game
    assert T.screenshots is None
    T.slash("qrtest proof-123")
    assert sent(T) == []
    frame = T.frames[len(T.frames)]
    assert frame.shown
    assert frame.scale == pytest.approx(768 / 2160)
    # Run the render-delay callback, then simulate the game's completion event.
    T.timers[1]()
    assert T.screenshots == 1
    T.fire("SCREENSHOT_SUCCEEDED")
    assert not frame.shown


def test_probe_rejects_invalid_codes_and_times_out(game):
    lua, T = game
    T.slash("qrtest invalid code")
    assert len(T.timers) == 0
    T.slash("qrtest proof-123")
    count = len(T.timers)
    T.slash("qrtest second")
    assert len(T.timers) == count
    T.flush()
    assert not T.frames[len(T.frames)].shown
