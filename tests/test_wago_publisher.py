import io
import json
from zipfile import ZipFile

from scripts import publish_wago


class Reply:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def read(self, *_):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_release_upload_uses_only_the_wago_request_for_the_injected_token():
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("Lookout/Lookout.toc", "## Interface: 16001\n## X-Wago-ID: 96EXEjNg\n")
    seen = []

    def open_request(request, timeout):
        seen.append(request)
        if request.full_url.endswith("/releases/tags/v0.2.2"):
            data = {"assets": [{"name": "Lookout-v0.2.2-forever.zip",
                                 "browser_download_url": "https://github.com/mdn87/lookout/releases/download/v0.2.2/Lookout-v0.2.2-forever.zip"}],
                    "body": "Release notes", "prerelease": False}
            return Reply(json.dumps(data).encode())
        if request.full_url.endswith("/api/data/game"):
            return Reply(json.dumps({"patches": {"forever": ["1.60.1"]}}).encode())
        if request.full_url.endswith(".zip"):
            return Reply(archive.getvalue())
        return Reply(b"{}", status=201)

    publish_wago.publish("v0.2.2", "synthetic-wago-token", open_request)
    assert len(seen) == 4
    assert all(request.get_header("Authorization") is None for request in seen[:3])
    upload = seen[3]
    assert upload.full_url == "https://addons.wago.io/api/projects/96EXEjNg/version"
    assert upload.get_header("Authorization") == "Bearer synthetic-wago-token"
    assert b"Lookout-v0.2.2-forever.zip" in upload.data
    assert b'"supported_forever_patches": ["1.60.1"]' in upload.data
    assert b'"changelog": "Release notes"' in upload.data


def test_dry_run_checks_archive_and_patch_without_posting():
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("Lookout/Lookout.toc", "## Interface: 16001\n## X-Wago-ID: 96EXEjNg\n")
    seen = []

    def open_request(request, timeout):
        seen.append(request.full_url)
        if request.full_url.endswith("/releases/tags/v0.2.2"):
            return Reply(json.dumps({"assets": [{"name": "Lookout-v0.2.2-forever.zip",
                "browser_download_url": "https://github.com/mdn87/lookout/releases/download/v0.2.2/Lookout-v0.2.2-forever.zip"}],
                "body": "", "prerelease": False}).encode())
        if request.full_url.endswith("/api/data/game"):
            return Reply(json.dumps({"patches": {"forever": ["1.60.1"]}}).encode())
        return Reply(archive.getvalue())

    publish_wago.publish("v0.2.2", "synthetic-wago-token", open_request, dry_run=True)
    assert len(seen) == 3
