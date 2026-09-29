# One-Shot Screenshot Probe

This experiment came first. Normal phone alerts now use the same drawing and screenshot
code, rate limited and read automatically by the tray app (see the README). The probe below
is still there as a manual check.

1. Install Python dependencies with `python -m pip install -r requirements-probe.txt`.
2. Install the updated addon and `/reload` in game.
3. Run `/lo qrtest unique-code` in game. Use 1-32 letters, digits, or hyphens.
4. Run `python -m companion.screenshot_probe "path/to/new-screenshot.jpg" --code unique-code --send`.

The addon displays a QR code in the bottom-left corner, waits one second for
rendering, and calls WoW's screenshot API. It hides the overlay on completion,
failure, or a ten-second timeout. The decoder reads only the bottom-left 512x512
crop and refuses to send unless the expected code appears exactly once.

WoW still saves a **full game screenshot locally**, possibly including private
chat. The probe uploads only fixed test text and the matching test code to the
configured Pushover account, not the image. Screenshots are not deleted. Each
explicit `--send` invocation can send another notification; this is not a watcher.

## Live Result

On 2026-09-28, Forever build 1.60.1.70009 saved a 3840x2160 screenshot during
gameplay. The corner decoder recovered `live-2320`, Pushover returned HTTP 200,
and the user confirmed the notification arrived on their phone without logout.
An earlier attempt exposed a UI-unit/physical-pixel scaling mismatch; the addon
now scales using the root UI height divided by the physical screen height.

Unverified: background/minimized capture, automated alert watching, longer real
messages, repeated delivery, and other game clients. The existing chat-log
transport still has its previously observed logout-time buffering limitation.
