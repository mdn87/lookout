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

   `Pushover answered 200` means your phone should buzz. Any other reply names the key Pushover
   rejected.
5. In game, `/reload` and then `/lo test`. This checks the whole chain: addon, chat log, tray
   app, phone.

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

## 3. Wago

1. Go to https://addons.wago.io and sign in.
2. Open the developer dashboard and create an addon named `Lookout`.
3. The dashboard shows the addon's **Wago ID**, a short code like `he54k6bL`. Write it down; it
   isn't secret.
4. Go to https://addons.wago.io/account/apikeys, create a key, and copy it. It **is** secret.

## 4. Put the two tokens in GitHub

1. Open https://github.com/mdn87/lookout/settings/secrets/actions.
2. Click **New repository secret**. Set the name to `CF_API_KEY`, paste the CurseForge token as
   the value, and click **Add secret**.
3. Do the same with the name `WAGO_API_TOKEN` and the Wago key.

GitHub never shows a secret again after you save it. Only the release workflow can read it.

## 5. Add the IDs and release

Send Claude the CurseForge Project ID and the Wago ID; they're public anyway. Claude adds them to
`Lookout.toc`, bumps the version, and pushes a tag.

To do it yourself, add these two lines under `## X-License: MIT` in
`addon/Lookout/Lookout.toc`:

```
## X-Curse-Project-ID: 123456
## X-Wago-ID: abcd1234
```

Then change `## Version:` to `0.1.1`, commit, and run:

```
git tag v0.1.1
git push origin master v0.1.1
```

The run shows up at https://github.com/mdn87/lookout/actions. The upload worked when the log shows
`Success!` after an upload to CurseForge and to Wago. If CurseForge rejects the game version,
the beta may not be on its version list yet. That's a CurseForge limit, and the GitHub release
still goes out.

## 6. Optional: start the tray app with Windows

1. Press Win+R, type `shell:startup`, and press Enter.
2. Right-click in that folder, choose **New > Shortcut**, and browse to `start-companion.cmd` in
   the project folder.
