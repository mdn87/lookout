# Setting up phone alerts and addon-site uploads

This covers the parts that need your own accounts: Pushover for phone alerts, then CurseForge and
Wago so each release uploads to both. The GitHub side already works. Every tag already builds a
zip and attaches it to a GitHub release.

The site menus below are described from the packager's documentation, not from clicking through
them. If a button has a different name, look for the nearest match.

## 1. Phone alerts (about 5 minutes)

1. Open https://pushover.net and sign in. Your **User Key** is at the top right of the dashboard.
2. Open https://pushover.net/apps/build, name the app `Lookout`, tick the terms box, and click
   **Create Application**. The next page shows its **API Token/Key**.
3. Open `config.json` in the project folder. Put the token in `"token"` and the user key in
   `"user"`, keep the quotes, and save.
4. In a terminal in the project folder, run:

   ```
   .venv/Scripts/python -m companion.app --test-push
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
5. Go to https://authors.curseforge.com/#/settings/api-tokens and generate a token named
   `lookout-github`. Copy it. It **is** secret, so don't paste it into chat.

## 3. Wago (done 2026-10-04)

Wago is set up the easy way: https://addons.wago.io/addons/lookout is connected to the GitHub
repository with **Releases Automation** on. Wago imports each new GitHub release on its own, so
there is no Wago API key and no `X-Wago-ID` line to manage. Two things to keep true on the
Wago **Settings > GitHub** page:

- The **Game Version** list has Classic Forever ticked. The zip is named `-forever.zip` and the
  packager's `release.json` names the same version, which is how Wago sorts the file.
- Leave **Always publish for latest game patch** off. The TOC's `## Interface:` line is correct
  for the Forever beta, and this switch would make Wago ignore it.

Releases made before the connection (v0.1.0) are not imported; the first automated one is v0.2.0.

## 4. Put the CurseForge token in GitHub

1. Open https://github.com/mdn87/lookout/settings/secrets/actions.
2. Click **New repository secret**. Set the name to `CF_API_KEY`, paste the CurseForge token as
   the value, and click **Add secret**.

GitHub never shows a secret again after you save it. Only the release workflow can read it.

## 5. Add the CurseForge ID and release

Send Claude the CurseForge Project ID; it's public anyway. Claude adds it to `Lookout.toc`, bumps
the version, and pushes a tag.

To do it yourself, add this line under `## X-License: MIT` in `addon/Lookout/Lookout.toc`:

```
## X-Curse-Project-ID: 123456
```

Then bump `## Version:`, commit, and push a matching tag:

```
git tag v0.2.1
git push origin master v0.2.1
```

The run shows up at https://github.com/mdn87/lookout/actions. The upload worked when the log shows
`Success!` after an upload to CurseForge. If CurseForge rejects the game version, the beta may not
be on its version list yet. That's a CurseForge limit, and the GitHub release still goes out. Wago
picks the release up from GitHub a few minutes later; check
https://addons.wago.io/addons/lookout/versions.

## 6. Optional: start the tray app with Windows

1. Press Win+R, type `shell:startup`, and press Enter.
2. Right-click in that folder, choose **New > Shortcut**, and browse to `start-companion.cmd` in
   the project folder.
