"""Publish the existing GitHub release archive to Wago with a GLAS-injected token."""

import argparse
import io
import json
import os
import re
import secrets
import sys
from urllib import error, request
from zipfile import BadZipFile, ZipFile


PROJECT_ID = "96EXEjNg"
REPOSITORY = "mdn87/lookout"
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024


class PublishError(Exception):
    pass


class RejectRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def open_request(outgoing, timeout):
    if outgoing.get_method() == "POST":
        return request.build_opener(RejectRedirect()).open(outgoing, timeout=timeout)
    return request.urlopen(outgoing, timeout=timeout)


def read_response(opener, url, limit):
    outgoing = request.Request(url, headers={"User-Agent": "lookout-wago-publisher/1"})
    with opener(outgoing, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise PublishError("A release response exceeded its size limit")
    return data


def read_json(opener, url):
    try:
        return json.loads(read_response(opener, url, MAX_JSON_BYTES))
    except (ValueError, UnicodeError) as exc:
        raise PublishError("A release endpoint returned invalid JSON") from exc


def archive_version(archive):
    try:
        with ZipFile(io.BytesIO(archive)) as package:
            info = package.getinfo("Lookout/Lookout.toc")
            if info.file_size > 100_000:
                raise PublishError("The release archive has an oversized TOC")
            toc = package.read(info).decode("utf-8")
    except (BadZipFile, KeyError, UnicodeError) as exc:
        raise PublishError("The GitHub release archive has no valid Lookout TOC") from exc
    project = re.search(r"^## X-Wago-ID:\s*(\S+)\s*$", toc, re.MULTILINE)
    interface = re.search(r"^## Interface:\s*(\d{5})\s*$", toc, re.MULTILINE)
    if not project or project.group(1) != PROJECT_ID or not interface:
        raise PublishError("The release archive does not target this Wago project")
    version = int(interface.group(1))
    if version // 10000 != 1 or version // 100 % 100 < 60:
        raise PublishError("The release archive is not for Classic Forever")
    return f"{version // 10000}.{version // 100 % 100}.{version % 100}"


def upload_body(archive_name, archive, metadata):
    boundary = "lookout-" + secrets.token_hex(16)
    metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n"
        "Content-Type: application/json\r\n\r\n"
    ).encode() + metadata_bytes + (
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{archive_name}\"\r\nContent-Type: application/zip\r\n\r\n"
    ).encode() + archive + f"\r\n--{boundary}--\r\n".encode()
    return boundary, body


def publish(tag, token, opener=open_request, dry_run=False):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", tag):
        raise PublishError("Supply a version tag such as v0.2.3")
    if not token:
        raise PublishError("WAGO_API_TOKEN is missing from the GLAS launch")

    release = read_json(opener, f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}")
    archive_name = f"Lookout-{tag}-forever.zip"
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{archive_name}"
    assets = release.get("assets", [])
    if not isinstance(assets, list) or not any(
        isinstance(asset, dict)
        and asset.get("name") == archive_name
        and asset.get("browser_download_url") == expected_url
        for asset in assets
    ):
        raise PublishError("The tagged GitHub release has no matching Lookout archive")

    game = read_json(opener, "https://addons.wago.io/api/data/game")
    archive = read_response(opener, expected_url, MAX_ARCHIVE_BYTES)
    patch = archive_version(archive)
    if patch not in game.get("patches", {}).get("forever", []):
        raise PublishError("Wago does not list the archive's Classic Forever patch")
    print(f"Verified {archive_name} for Classic Forever {patch}")
    if dry_run:
        return

    metadata = {
        "label": f"{tag}-forever",
        "supported_forever_patches": [patch],
        "stability": "beta" if release.get("prerelease") else "stable",
        "changelog": release.get("body") or "",
    }
    boundary, body = upload_body(archive_name, archive, metadata)
    outgoing = request.Request(
        f"https://addons.wago.io/api/projects/{PROJECT_ID}/version",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "lookout-wago-publisher/1",
        },
        method="POST",
    )
    with opener(outgoing, timeout=60) as response:
        if response.status not in (200, 201):
            raise PublishError(f"Wago returned HTTP {response.status}")
    print(f"Published {tag} to Wago")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Tag of an existing Lookout GitHub release")
    parser.add_argument("--dry-run", action="store_true", help="Check the archive and Wago patch without uploading")
    args = parser.parse_args(argv)
    try:
        publish(args.tag, os.environ.get("WAGO_API_TOKEN", ""), dry_run=args.dry_run)
    except error.HTTPError as exc:
        print(f"Release request failed with HTTP {exc.code}", file=sys.stderr)
        return 1
    except (error.URLError, TimeoutError, OSError):
        print("Release request failed; check the network and retry", file=sys.stderr)
        return 1
    except PublishError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
