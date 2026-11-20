# Setting up phone alerts and addon-site uploads

This covers Pushover phone alerts and addon-site releases. A tag builds a zip and attaches it to a
GitHub release. A separate GLAS-backed command sends that zip to Wago.

The site menus below are described from the packager's documentation, not from clicking through
them. If a button has a different name, look for the nearest match.

## 1. Phone alerts (about 5 minutes)

1. Open https://pushover.net and sign in. Your **User Key** is at the top right of the dashboard.
2. Open https://pushover.net/apps/build, name the app `Lookout`, tick the terms box, and click
   **Create Application**. The next page shows its **API Token/Key**.
3. Store the app token and user key as separate BWS entries. Map them to `PUSHOVER_TOKEN` and
   `PUSHOVER_USER` in the ignored `config/glas.local.json` manifest.
4. In a terminal in the project folder, run:

   ```
   .venv/Scripts/python scripts/with-glas.py --test-push
   ```

   `Pushover answered 200` means Pushover accepted the message, not that the phone displayed
   it. Check the phone and its notification permissions. Failures print diagnostic details.
5. Start the tray app (`start-companion.cmd`). In game, `/reload` and then `/lo test`. A QR
   code flashes in the bottom-left corner, and the push should reach the phone within a few
   seconds. This checks the whole chain: addon, screenshot, tray app, phone.

## 2. CurseForge

1. Go to https://authors.curseforge.com and sign in, or make an account.
2. Create a project: game **World of Warcraft**, type **Addons**, name `Lookout`, license
   **MIT**. For the source code link, use `https://github.com/mdn87/lookout`. If it asks for an
   icon, any square image works for now.
3. New projects go through a CurseForge review before the public can see them. That's normal.
4. Open the project page. The **Project ID** is a number in the **About Project** box. Write it
   down; it isn't secret.
5. When enabling publishing, create a CurseForge API token and store it in BWS. The GitHub
   release workflow does not upload to CurseForge.

## 3. Wago

The publisher uses the zip attached to the GitHub release:

- `## X-Wago-ID: 96EXEjNg` in `addon/Lookout/Lookout.toc`. The ID is the project code shown on
  the Wago **Settings > General** page; it isn't secret.
- A BWS Wago API token mapped to `WAGO_API_TOKEN` by a separate ignored
  `config/glas.wago.local.json` manifest.
- `Lookout.toc` has `## Interface: 16001`. The publisher verifies that the corresponding
  Classic Forever patch is listed by Wago before uploading.

The first historical packager release to reach Wago was v0.2.2. Its run log shows
`Uploading Lookout-v0.2.2-forever.zip (1.60.1 release) to https://addons.wago.io/addons/96EXEjNg`
and then `Success!`; the file appeared on https://addons.wago.io/addons/lookout/versions within a
minute.

The Wago GitHub webhook remains deactivated. The BWS-backed publisher sends one explicit upload
after the GitHub release exists.

## 4. Prepare the Wago GLAS manifest

Create `config/glas.wago.local.json` with one BWS reference mapped to `WAGO_API_TOKEN`. Keep
that manifest on the publishing machine. Its consumer ID can be `lookout-wago-publisher`.
Use the GLAS runtime profile that can read the Wago entry.

## 5. Release

Bump `## Version:`, commit, and push a matching tag:

```
git tag v0.2.3
git push origin master v0.2.3
```

The Actions run attaches the zip to the GitHub release. From the Lookout checkout, run the
following commands with a GLAS installation that has Bitwarden support and a native-store
profile. `GLAS_HOME` points to that profile's inventory. The first command checks the asset and
Wago patch without creating a version:

```powershell
$env:GLAS_HOME = 'C:\path\to\your\glas-state'
glas run --manifest config/glas.wago.local.json -- .venv/Scripts/python.exe scripts/publish_wago.py v0.2.3 --dry-run
glas run --manifest config/glas.wago.local.json -- .venv/Scripts/python.exe scripts/publish_wago.py v0.2.3
```

Check the new version at https://addons.wago.io/addons/lookout/versions. The upload command
creates a public Wago version, so run it once for each release.

## 6. Optional: start the tray app with Windows

1. Press Win+R, type `shell:startup`, and press Enter.
2. Right-click in that folder, choose **New > Shortcut**, and browse to `start-companion.cmd` in
   the project folder.
