#!/usr/bin/env python3
# file: scripts/publish_frontend_assets.py
# Publish the front-end packages the generated pages load (FRONTEND_PACKAGES
# in alchemist.py) to {ALCHEMIST_BUCKET}/alchemist/assets/{name}/{version}/,
# so pages are served without a third-party CDN.
#
# Each package is downloaded, as an npm tarball or a release zip from its
# pinned URL, and checked against the integrity hash pinned in
# FRONTEND_PACKAGES before anything is uploaded.
# Published versions are immutable: keys that already exist are never
# rewritten, only missing ones are uploaded, so re-running after a partial
# upload completes it. Once every file is in place, a .published.json marker
# is written, which `alchemist.py validate` requires before any publication;
# a package whose marker is already in place is skipped without downloading
# anything. Run this before publishing pages that reference a new version.

import argparse
import base64
import hashlib
import json
import logging
import mimetypes
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from pathlib import Path

import boto3  # pypi: boto3

from decouple import Config, RepositoryIni  # pypi: python-decouple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alchemist import (  # noqa: E402
    FRONTEND_PACKAGES,
    get_frontend_assets_marker_key,
    get_frontend_package_key_prefix,
)

logger = logging.getLogger("publish_frontend_assets")

NPM_REGISTRY = "https://registry.npmjs.org"
CACHE_CONTROL = "public, max-age=31536000, immutable"


class IntegrityError(Exception):
    pass


def tarball_url(npm_name: str, version: str) -> str:
    """Return the npm registry URL of a package version's tarball; a scoped
    package's tarball filename omits the scope."""
    return f"{NPM_REGISTRY}/{npm_name}/-/{npm_name.split('/')[-1]}-{version}.tgz"


def package_url(package: dict) -> str:
    if "npm_name" in package:
        return tarball_url(package["npm_name"], package["version"])
    return package["url"]


def verify_integrity(data: bytes, integrity: str) -> None:
    """Raise IntegrityError unless `data` matches a sha512 or sha256
    Subresource Integrity string."""
    algorithm, _, expected = integrity.partition("-")
    if algorithm not in ("sha512", "sha256"):
        raise IntegrityError(f"unsupported integrity algorithm: {algorithm}")
    actual = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if actual != expected:
        raise IntegrityError(
            f"expected {algorithm}-{expected}, got {algorithm}-{actual}"
        )


def extract_package(package: dict, data: bytes, directory: Path) -> Path:
    """Extract a downloaded package into `directory` and return its root."""
    archive_path = directory / "download"
    archive_path.write_bytes(data)
    if "npm_name" in package:
        with tarfile.open(archive_path) as archive:
            # the "data" filter rejects absolute paths, links out of the
            # destination, and device files
            archive.extractall(directory / "extracted", filter="data")
        # npm tarballs hold their contents under a top-level package/
        return directory / "extracted" / "package"
    with zipfile.ZipFile(archive_path) as archive:
        # ZipFile.extractall drops absolute paths and ".." components, so
        # nothing lands outside the destination
        archive.extractall(directory / "extracted")
    return directory / "extracted"


def select_files(
    package_root: Path, paths: list[str], key_prefix: str
) -> dict[str, Path]:
    """Map each S3 key to the extracted file it publishes. A directory in
    `paths` contributes every file beneath it; every path must exist."""
    files = {}
    for path in paths:
        source = package_root / path
        if source.is_dir():
            candidates = sorted(p for p in source.rglob("*") if p.is_file())
        elif source.is_file():
            candidates = [source]
        else:
            raise FileNotFoundError(f"not in package: {path}")
        for candidate in candidates:
            relative = candidate.relative_to(package_root).as_posix()
            files[f"{key_prefix}/{relative}"] = candidate
    return files


def content_type(path: Path) -> str:
    if path.name.endswith(".LICENSE.txt"):
        return "text/plain"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def list_existing_keys(s3_client, bucket: str, prefix: str) -> set[str]:
    keys = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
        keys.update(item["Key"] for item in page.get("Contents", []))
    return keys


def publish_package(s3_client, bucket: str, name: str, dry_run: bool) -> int:
    """Publish one FRONTEND_PACKAGES entry; return the number of files
    uploaded (or that would be, with dry_run)."""
    package = FRONTEND_PACKAGES[name]
    key_prefix = get_frontend_package_key_prefix(name)
    marker_key = get_frontend_assets_marker_key(name)
    existing = list_existing_keys(s3_client, bucket, key_prefix)
    if marker_key in existing:
        marker = json.loads(
            s3_client.get_object(Bucket=bucket, Key=marker_key)["Body"].read()
        )
        if marker.get("integrity") != package["integrity"]:
            # published versions are immutable, so this can't be repaired by
            # uploading over it
            raise IntegrityError(
                f"s3://{bucket}/{marker_key} records {marker.get('integrity')}, "
                f"not the pinned {package['integrity']}"
            )
        logger.info(f"{name} {package['version']}: already published")
        return 0
    url = package_url(package)
    logger.info(f"downloading {url}")
    with urllib.request.urlopen(url) as response:
        data = response.read()
    verify_integrity(data, package["integrity"])
    with tempfile.TemporaryDirectory() as extract_directory:
        package_root = extract_package(package, data, Path(extract_directory))
        files = select_files(package_root, package["paths"], key_prefix)
        missing = {key: path for key, path in files.items() if key not in existing}
        logger.info(
            f"{name} {package['version']}: {len(files)} files, "
            f"{len(files) - len(missing)} already published, {len(missing)} to upload"
        )
        for key, path in missing.items():
            if dry_run:
                logger.info(f"would upload s3://{bucket}/{key}")
                continue
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType=content_type(path),
                CacheControl=CACHE_CONTROL,
            )
            logger.debug(f"uploaded s3://{bucket}/{key}")
    # written only after every file is in place: `alchemist.py validate`
    # treats the marker as the package being fully published
    if not dry_run:
        s3_client.put_object(
            Bucket=bucket,
            Key=marker_key,
            Body=json.dumps(
                {
                    "source": package.get("npm_name") or package["url"],
                    "version": package["version"],
                    "integrity": package["integrity"],
                    "files": len(files),
                },
                indent=2,
            ).encode(),
            ContentType="application/json",
        )
        logger.info(f"marked s3://{bucket}/{marker_key}")
    return len(missing)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Publish the self-hosted front-end packages "
        "(FRONTEND_PACKAGES in alchemist.py) to the Alchemist bucket."
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Path to settings.ini (defaults to the repo's settings.ini).",
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help="S3 bucket to target (defaults to ALCHEMIST_BUCKET from settings.ini).",
    )
    parser.add_argument(
        "--package",
        action="append",
        choices=sorted(FRONTEND_PACKAGES),
        help="Only publish this package; repeatable (defaults to all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and verify, then log what would be uploaded.",
    )
    return parser.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()

    bucket = args.bucket
    if not bucket:
        settings_path = (
            Path(args.settings).expanduser().resolve()
            if args.settings
            else Path(__file__).resolve().parent.parent / "settings.ini"
        )
        if not settings_path.exists():
            raise FileNotFoundError(
                f"--bucket not given and settings file not found: {settings_path}"
            )
        config = Config(RepositoryIni(settings_path.as_posix()))
        bucket = config("ALCHEMIST_BUCKET")

    # Credentials come from the operator's normal AWS credential chain: this
    # is a manually run deployment tool.
    s3_client = boto3.client("s3")

    for name in args.package or sorted(FRONTEND_PACKAGES):
        publish_package(s3_client, bucket, name, args.dry_run)
    logger.info("DONE")


if __name__ == "__main__":
    main()
