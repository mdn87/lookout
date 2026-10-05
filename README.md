# Lookout

A World of Warcraft addon plus a small Windows tray app.

- **Alerts** for players you watch (whispers, or talking in any channel you can see), chat
  keywords, whispers and mentions while you're away, group invites, dungeon and battleground
  queue pops, and ready checks.
- **Phone alerts** through Pushover, sent by the companion app.
- **Quest helper**: a movable progress panel, a notice when an objective or a whole quest is
  done, and `/lo way` to point at a quest's next step with TomTom or the game's map pin.
  Other addons can add location sources through `LookoutAPI`.

## Why there are two parts

Addons can't reach the network or write files while you play, but they can take a
screenshot. For each phone alert the addon draws a QR code in the bottom-left corner for
about a second and takes a screenshot. The companion watches the game's `Screenshots`
folder, reads the code, sends the push through Pushover, and deletes that screenshot.
Your own screenshots are left alone.

Screenshots are rate limited: at most one every 20 seconds (5 for group invites, queue pops
and ready checks) and 30 an hour. Alerts raised in between go out together in the next
screenshot, as one push. If more than 20 pile up, the oldest ordinary ones are dropped and
the next push says how many. During a fight you're at the keyboard for, ordinary alerts
wait until it ends so the code doesn't cover your screen. `/lo rate` shows or changes the
limits.

The older route, `/lo transport chat`, whispers each alert to yourself
(`LOOKOUT :: CHARACTER :: KIND :: TEXT`) for the companion to read from
`Logs/WoWChatLog.txt`. On Forever beta 1.60.1.70009 the game only writes that file at
logout, so it can't deliver alerts during play there.

## Setup

1. `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`
2. Copy `config.example.json` to `config.json` and add your Pushover app token and user key.
3. `.venv\Scripts\python install.py` copies the addon into every installed game version.
4. In game: `/reload`, then `/lo` for commands.
5. Run `start-companion.cmd` for the tray icon. `--test-push` sends one test alert.

## Commands

| Command | Does |
| --- | --- |
| `/lo add NAME`, `/lo remove NAME`, `/lo names` | players to watch |
| `/lo word add TEXT`, `/lo word remove TEXT`, `/lo words` | chat keywords |
| `/lo alert KIND phone\|screen\|off`, `/lo alerts` | where each kind of alert goes |
| `/lo phone on\|off`, `/lo hide on\|off`, `/lo test` | phone alerts, hiding the signal whispers, a test alert |
| `/lo transport screenshot\|chat`, `/lo rate [seconds perHour]` | how phone alerts leave the game, screenshot limits |
| `/lo quests`, `/lo way [questID]`, `/lo providers` | quest panel, waypoint, location sources |
| `/lo help QUESTION` | ask the companion's assistant; the answer arrives as a phone alert |

Alert kinds: `whisper`, `seen`, `keyword`, `invite`, `queue`, `readycheck`, `afk`, `quest`, `test`.

## Asking the assistant

`/lo help how do I see which realm I'm on?` sends the question to the companion the same way an
alert goes out, with your character's level, class, faction, realm and zone appended in square
brackets. The companion asks an OpenAI-compatible chat endpoint and pushes the answer to your
phone as a `Lookout answer` alert (and a tray notification). Settings live in the `assistant`
block of `config.json`: `url` is the API base (`.../v1`), `model` the model name, `key` optional.
`url` and `key` fall back to the `LOOKOUT_AI_URL` / `LOOKOUT_AI_KEY` environment variables,
then `OMNIROUTE_BASE_URL` / `OMNIROUTE_API_KEY`; `model` falls back to `LOOKOUT_AI_MODEL`.
`python -m companion.app --ask "..."` tries it from a terminal. Questions are rate limited like
any other phone alert, and the answer usually takes ten seconds or so.

## Tests

`.venv\Scripts\python -m pytest` loads the addon into Lua 5.1 against a stubbed game API,
draws its QR code into an image, and checks that the companion reads it back.

## Screenshot probe

`/lo qrtest CODE` is the one-shot [screenshot probe](docs/screenshot-probe.md) that first
proved a screenshot reaches the phone without logging out.

## Releasing

`.pkgmeta` and `.github/workflows/release.yml` use the BigWigs packager. Bump `## Version` in
`Lookout.toc`, then push a matching tag (`git tag v0.2.0 && git push origin v0.2.0`). The
workflow builds `Lookout-v0.2.0-forever.zip` with only the addon folder and attaches it to a GitHub
release.

**Wago** (https://addons.wago.io/addons/lookout) gets the same zip from the packager: `Lookout.toc`
carries `## X-Wago-ID: 96EXEjNg` and the repository has a `WAGO_API_TOKEN` secret. The run log
prints `Uploading ... to https://addons.wago.io/addons/96EXEjNg` followed by `Success!`.

**CurseForge** uploads start once it is set up: add `## X-Curse-Project-ID: 123456` to `Lookout.toc`
and a `CF_API_KEY` repository secret (from authors.curseforge.com/#/settings/api-tokens).

The companion app isn't part of the addon zip. Step-by-step account setup is in
[docs/publishing.md](docs/publishing.md).

## License

MIT. See [LICENSE](LICENSE). The vendored Lua QR encoder retains its BSD-3-Clause
license; see [vendor attribution](addon/Lookout/vendor/README.md).
