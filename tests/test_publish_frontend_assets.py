import base64
import hashlib
import io
import json
import sys
import tarfile

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import publish_frontend_assets as publish  # noqa: E402


def build_tarball(files: dict[str, bytes]) -> bytes:
    """Build an npm-style .tgz holding `files` under a top-level package/."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def sri(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


class FakeS3:
    def __init__(self, existing_keys=()):
        self.existing_keys = set(existing_keys)
        self.puts = {}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        fake = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {
                    "Contents": [
                        {"Key": key}
                        for key in sorted(fake.existing_keys)
                        if key.startswith(Prefix)
                    ]
                }

        return Paginator()

    def put_object(self, **kwargs):
        self.puts[kwargs["Key"]] = kwargs


@pytest.mark.parametrize(
    "npm_name, expected",
    [
        (
            "universalviewer",
            "https://registry.npmjs.org/universalviewer/-/universalviewer-4.4.4.tgz",
        ),
        (
            "@picocss/pico",
            "https://registry.npmjs.org/@picocss/pico/-/pico-4.4.4.tgz",
        ),
    ],
)
def test_tarball_url(npm_name, expected):
    assert publish.tarball_url(npm_name, "4.4.4") == expected


def test_verify_integrity_accepts_matching_hash():
    publish.verify_integrity(b"tarball", sri(b"tarball"))


def test_verify_integrity_rejects_mismatch():
    with pytest.raises(publish.IntegrityError):
        publish.verify_integrity(b"tampered", sri(b"tarball"))


def test_verify_integrity_rejects_other_algorithms():
    with pytest.raises(publish.IntegrityError, match="unsupported"):
        publish.verify_integrity(b"tarball", "sha1-abc")


def test_select_files_expands_directories(tmp_path):
    (tmp_path / "dist" / "umd").mkdir(parents=True)
    (tmp_path / "dist" / "umd" / "UV.js").write_text("js")
    (tmp_path / "dist" / "umd" / "1000.abc.js").write_text("chunk")
    (tmp_path / "dist" / "uv.css").write_text("css")
    (tmp_path / "dist" / "esm").mkdir()
    (tmp_path / "dist" / "esm" / "index.js").write_text("unpublished")

    files = publish.select_files(
        tmp_path, ["dist/umd", "dist/uv.css"], "assets/universalviewer/4.4.4"
    )

    assert set(files) == {
        "assets/universalviewer/4.4.4/dist/umd/1000.abc.js",
        "assets/universalviewer/4.4.4/dist/umd/UV.js",
        "assets/universalviewer/4.4.4/dist/uv.css",
    }


def test_select_files_rejects_missing_paths(tmp_path):
    with pytest.raises(FileNotFoundError, match="dist/uv.min.css"):
        publish.select_files(tmp_path, ["dist/uv.min.css"], "assets/x/1")


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("UV.js", "text/javascript"),
        ("uv.css", "text/css"),
        ("2206.1cf3214a73e02044b188.js.LICENSE.txt", "text/plain"),
    ],
)
def test_content_type(filename, expected):
    assert publish.content_type(Path(filename)) == expected


def _patch_package(monkeypatch, tarball, integrity):
    monkeypatch.setitem(
        publish.FRONTEND_PACKAGES,
        "testpkg",
        {
            "npm_name": "testpkg",
            "version": "1.0.0",
            "integrity": integrity,
            "paths": ["dist", "LICENSE"],
        },
    )
    monkeypatch.setattr(
        publish.urllib.request, "urlopen", lambda url: io.BytesIO(tarball)
    )


def test_publish_package_uploads_only_missing_keys(monkeypatch):
    tarball = build_tarball(
        {"dist/a.js": b"a", "dist/b.css": b"b", "LICENSE": b"MIT", "README.md": b""}
    )
    _patch_package(monkeypatch, tarball, sri(tarball))
    s3 = FakeS3(existing_keys={"assets/testpkg/1.0.0/dist/a.js"})

    uploaded = publish.publish_package(s3, "bucket", "testpkg", dry_run=False)

    assert uploaded == 2
    assert set(s3.puts) == {
        "assets/testpkg/1.0.0/dist/b.css",
        "assets/testpkg/1.0.0/LICENSE",
        "assets/testpkg/1.0.0/.published.json",
    }
    # the marker is written last, once every file is in place
    assert list(s3.puts)[-1] == "assets/testpkg/1.0.0/.published.json"
    marker = json.loads(s3.puts["assets/testpkg/1.0.0/.published.json"]["Body"])
    assert marker == {
        "npm_name": "testpkg",
        "version": "1.0.0",
        "integrity": sri(tarball),
        "files": 3,
    }
    css = s3.puts["assets/testpkg/1.0.0/dist/b.css"]
    assert css["Body"] == b"b"
    assert css["ContentType"] == "text/css"
    assert css["CacheControl"] == "public, max-age=31536000, immutable"


def test_publish_package_dry_run_uploads_nothing(monkeypatch):
    tarball = build_tarball({"dist/a.js": b"a", "LICENSE": b"MIT"})
    _patch_package(monkeypatch, tarball, sri(tarball))
    s3 = FakeS3()

    assert publish.publish_package(s3, "bucket", "testpkg", dry_run=True) == 2
    assert s3.puts == {}


def test_publish_package_uploads_nothing_when_integrity_fails(monkeypatch):
    tarball = build_tarball({"dist/a.js": b"a", "LICENSE": b"MIT"})
    _patch_package(monkeypatch, tarball, sri(b"something else"))
    s3 = FakeS3()

    with pytest.raises(publish.IntegrityError):
        publish.publish_package(s3, "bucket", "testpkg", dry_run=False)
    assert s3.puts == {}


def test_publish_package_keeps_an_existing_marker(monkeypatch):
    tarball = build_tarball({"dist/a.js": b"a", "LICENSE": b"MIT"})
    _patch_package(monkeypatch, tarball, sri(tarball))
    s3 = FakeS3(
        existing_keys={
            "assets/testpkg/1.0.0/dist/a.js",
            "assets/testpkg/1.0.0/LICENSE",
            "assets/testpkg/1.0.0/.published.json",
        }
    )

    assert publish.publish_package(s3, "bucket", "testpkg", dry_run=False) == 0
    assert s3.puts == {}
