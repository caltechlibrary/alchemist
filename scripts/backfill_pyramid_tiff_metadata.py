#!/usr/bin/env python3
# file: scripts/backfill_pyramid_tiff_metadata.py
# One-off backfill: attach x-amz-meta-width/height/pages/tilesize to pyramid
# TIFFs published before that metadata was written at publish time.
#
# Width/height are read directly from each object's first TIFF IFD via two
# small S3 Range GETs (no full download), since re-deriving from original
# source files isn't reliably possible for a backlog this size. `pages` is
# computed with the same formula alchemist.py uses going forward.
#
# IMPORTANT: copy_object(..., MetadataDirective="REPLACE") resets ContentType
# to a service default unless explicitly re-specified -- this script always
# reads and re-passes the object's existing ContentType.

import argparse
import logging
import struct
import sys
import threading

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3  # pypi: boto3

from botocore.config import Config as BotoClientConfig  # pypi: boto3
from decouple import Config, RepositoryIni  # pypi: python-decouple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alchemist import calculate_pyramid_pages, PYRAMID_TILE_SIZE  # noqa: E402

logger = logging.getLogger("backfill_pyramid_tiff_metadata")

IFD_READ_CHUNK = 4096  # bytes; comfortably covers a vips pyramid TIFF's IFD entries
TIFF_TAG_IMAGE_WIDTH = 256
TIFF_TAG_IMAGE_LENGTH = 257
TIFF_FIELD_TYPE_SHORT = 3
TIFF_FIELD_TYPE_LONG = 4


class UnsupportedTiffError(Exception):
    pass


def read_tiff_dimensions(s3_client, bucket: str, key: str) -> tuple[int, int]:
    """Read (width, height) from a TIFF's first IFD via targeted Range GETs."""
    header = s3_client.get_object(Bucket=bucket, Key=key, Range="bytes=0-7")[
        "Body"
    ].read()
    byte_order = header[0:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        raise UnsupportedTiffError(f"unrecognized byte-order marker: {byte_order!r}")

    magic = struct.unpack(endian + "H", header[2:4])[0]
    if magic != 42:
        raise UnsupportedTiffError(
            f"unsupported TIFF magic number: {magic} (BigTIFF or non-TIFF?)"
        )

    ifd_offset = struct.unpack(endian + "I", header[4:8])[0]

    chunk = s3_client.get_object(
        Bucket=bucket,
        Key=key,
        Range=f"bytes={ifd_offset}-{ifd_offset + IFD_READ_CHUNK - 1}",
    )["Body"].read()
    entry_count = struct.unpack(endian + "H", chunk[0:2])[0]
    entries_size = entry_count * 12
    if len(chunk) < 2 + entries_size:
        chunk = s3_client.get_object(
            Bucket=bucket,
            Key=key,
            Range=f"bytes={ifd_offset}-{ifd_offset + 2 + entries_size - 1}",
        )["Body"].read()

    width = height = None
    for i in range(entry_count):
        entry = chunk[2 + i * 12 : 2 + (i + 1) * 12]
        tag, field_type = struct.unpack(endian + "HH", entry[0:4])
        if tag not in (TIFF_TAG_IMAGE_WIDTH, TIFF_TAG_IMAGE_LENGTH):
            continue
        if field_type == TIFF_FIELD_TYPE_SHORT:
            value = struct.unpack(endian + "H", entry[8:10])[0]
        elif field_type == TIFF_FIELD_TYPE_LONG:
            value = struct.unpack(endian + "I", entry[8:12])[0]
        else:
            raise UnsupportedTiffError(
                f"unexpected field type {field_type} for tag {tag}"
            )
        if tag == TIFF_TAG_IMAGE_WIDTH:
            width = value
        else:
            height = value
        if width is not None and height is not None:
            break

    if width is None or height is None:
        raise UnsupportedTiffError("ImageWidth/ImageLength not found in first IFD")
    return width, height


def backfill_object(s3_client, bucket: str, key: str, dry_run: bool) -> str:
    head = s3_client.head_object(Bucket=bucket, Key=key)
    existing_metadata = head.get("Metadata", {})
    if (
        existing_metadata.get("width")
        and existing_metadata.get("height")
        and existing_metadata.get("pages")
    ):
        return "skipped-already-tagged"

    width, height = read_tiff_dimensions(s3_client, bucket, key)
    pages = calculate_pyramid_pages(width, height)
    metadata = {
        "width": str(width),
        "height": str(height),
        "pages": str(pages),
        "tilesize": str(PYRAMID_TILE_SIZE),
    }

    if dry_run:
        logger.info(f"DRY-RUN {key}: {metadata}")
        return "dry-run"

    s3_client.copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": bucket, "Key": key},
        Metadata=metadata,
        MetadataDirective="REPLACE",
        ContentType=head.get("ContentType", "application/octet-stream"),
    )
    return "updated"


def iter_ptif_keys(s3_client, bucket: str, prefix: str, limit: int | None):
    paginator = s3_client.get_paginator("list_objects_v2")
    yielded = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".ptif"):
                continue
            yield obj["Key"]
            yielded += 1
            if limit and yielded >= limit:
                return


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill x-amz-meta-width/height/pages/tilesize onto "
        "already-published pyramid TIFFs."
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
        "--prefix",
        default="",
        help="Only process keys under this S3 prefix (e.g. collections/EXAMPLE/).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after processing this many matching objects.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=32,
        help="Number of concurrent worker threads.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would change without calling copy_object.",
    )
    parser.add_argument(
        "--failures-log",
        default="backfill_failures.log",
        help="Path to write failed keys and error reasons.",
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

    # Credentials come from the operator's normal AWS credential chain
    # (environment/~/.aws/credentials/SSO/instance role/etc.) rather than
    # settings.ini: this is a manually-run migration tool, not the automated
    # pipeline, so it should use whatever AWS identity is already active
    # instead of the app's bucket-scoped settings.ini credentials.
    s3_client = boto3.client(
        "s3", config=BotoClientConfig(max_pool_connections=args.workers)
    )

    counts = Counter()
    counts_lock = threading.Lock()
    failures = []

    def process(key):
        try:
            outcome = backfill_object(s3_client, bucket, key, args.dry_run)
        except Exception as e:
            outcome = "failed"
            failures.append((key, str(e)))
            logger.error(f"FAILED {key}: {e}")
        with counts_lock:
            counts[outcome] += 1
            total = sum(counts.values())
        if total % 500 == 0:
            logger.info(f"progress: {total} processed -- {dict(counts)}")

    logger.info(
        f"starting backfill: bucket={bucket} prefix={args.prefix!r} "
        f"limit={args.limit} workers={args.workers} dry_run={args.dry_run}"
    )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        list(
            executor.map(
                process, iter_ptif_keys(s3_client, bucket, args.prefix, args.limit)
            )
        )

    logger.info(f"DONE: {dict(counts)}")
    if failures:
        with open(args.failures_log, "w") as f:
            for key, reason in failures:
                f.write(f"{key}\t{reason}\n")
        logger.warning(f"{len(failures)} failures written to {args.failures_log}")


if __name__ == "__main__":
    main()
