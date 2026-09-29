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

Addons can't reach the network or write files while you play. The addon sends each phone
alert as a whisper to yourself (`LOOKOUT :: <character> :: <kind> :: <text>`), hidden from
your chat window. The game writes it to `Logs/WoWChatLog.txt`, and the companion reads that
file and calls Pushover.

## Setup

1. `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`
2. Copy `config.example.json` to `config.json` and add your Pushover app token and user key.
3. `.venv\Scripts\python install.py` copies the addon into every installed game version.
4. In game: `/reload`, then `/lo` for commands.
5. Run `start-companion.cmd` for the tray icon. `--test-push` sends one test alert.

## Commands

| Command | Does |
| --- | --- |
| `/lo add <name>`, `/lo remove <name>`, `/lo names` | players to watch |
| `/lo word add <text>`, `/lo word remove <text>`, `/lo words` | chat keywords |
| `/lo alert <kind> phone\|screen\|off`, `/lo alerts` | where each kind of alert goes |
| `/lo phone on\|off`, `/lo hide on\|off`, `/lo test` | phone alerts, hiding the signal whispers, a test alert |
| `/lo quests`, `/lo way [questID]`, `/lo providers` | quest panel, waypoint, location sources |

Alert kinds: `whisper`, `seen`, `keyword`, `invite`, `queue`, `readycheck`, `afk`, `quest`, `test`.

## Tests

`.venv\Scripts\python -m pytest` loads the addon into Lua 5.1 against a stubbed game API and
tests the companion's log reader.

## Releasing

`.pkgmeta` and `.github/workflows/release.yml` use the BigWigs packager. Bump `## Version` in
`Lookout.toc`, then push a matching tag (`git tag v0.2.0 && git push origin v0.2.0`). The
workflow builds `Lookout-v0.2.0-forever.zip` with only the addon folder and attaches it to a GitHub
release.

CurseForge and Wago uploads start once both are set up:

- **CurseForge:** add `## X-Curse-Project-ID: <id>` to `Lookout.toc` and a `CF_API_KEY`
  repository secret (from authors.curseforge.com/#/settings/api-tokens).
- **Wago:** add `## X-Wago-ID: <id>` to `Lookout.toc` and a `WAGO_API_TOKEN` repository secret
  (from addons.wago.io/account/apikeys).

The companion app isn't part of the addon zip. Step-by-step account setup is in
[docs/publishing.md](docs/publishing.md).

## License

MIT. See [LICENSE](LICENSE).
