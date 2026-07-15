import io
import struct
import sys

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_pyramid_tiff_metadata as backfill  # noqa: E402


def build_minimal_tiff(width, height, endian="<", field_type=3):
    """Build a minimal, valid classic-TIFF byte string with a single IFD
    holding only ImageWidth (256) and ImageLength (257), for testing the
    Range-GET-based IFD parser without depending on libvips being installed."""
    order_marker = b"II" if endian == "<" else b"MM"
    ifd_offset = 8
    header = order_marker + struct.pack(endian + "H", 42) + struct.pack(
        endian + "I", ifd_offset
    )

    def entry(tag, value):
        if field_type == backfill.TIFF_FIELD_TYPE_SHORT:
            value_bytes = struct.pack(endian + "H", value) + b"\x00\x00"
        else:
            value_bytes = struct.pack(endian + "I", value)
        return struct.pack(endian + "HHI", tag, field_type, 1) + value_bytes

    entries = entry(256, width) + entry(257, height)
    ifd = (
        struct.pack(endian + "H", 2)
        + entries
        + struct.pack(endian + "I", 0)  # next-IFD offset: none
    )
    return header + ifd


class FakeS3Client:
    def __init__(self, objects=None):
        self.objects = objects or {}
        self.copy_calls = []
        self.head_calls = []

    def get_object(self, Bucket, Key, Range=None):
        body = self.objects[Key]["body"]
        if Range:
            spec = Range.split("=", 1)[1]
            start, end = spec.split("-")
            start = int(start)
            end = int(end) if end else len(body) - 1
            data = body[start : end + 1]
        else:
            data = body
        return {"Body": io.BytesIO(data)}

    def head_object(self, Bucket, Key):
        self.head_calls.append(Key)
        obj = self.objects[Key]
        return {"ContentType": obj["content_type"], "Metadata": dict(obj["metadata"])}

    def copy_object(self, **kwargs):
        self.copy_calls.append(kwargs)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.objects)


class FakePaginator:
    def __init__(self, objects, page_size=2):
        self.objects = objects
        self.page_size = page_size

    def paginate(self, Bucket, Prefix=""):
        keys = [k for k in self.objects if k.startswith(Prefix)]
        for i in range(0, len(keys), self.page_size):
            yield {
                "Contents": [{"Key": k} for k in keys[i : i + self.page_size]]
            }


@pytest.mark.parametrize("endian", ["<", ">"])
def test_read_tiff_dimensions_short_field_type(endian):
    body = build_minimal_tiff(800, 500, endian=endian, field_type=backfill.TIFF_FIELD_TYPE_SHORT)
    client = FakeS3Client({"a.ptif": {"body": body, "content_type": "x", "metadata": {}}})
    assert backfill.read_tiff_dimensions(client, "bucket", "a.ptif") == (800, 500)


def test_read_tiff_dimensions_long_field_type():
    body = build_minimal_tiff(70000, 60000, endian="<", field_type=backfill.TIFF_FIELD_TYPE_LONG)
    client = FakeS3Client({"a.ptif": {"body": body, "content_type": "x", "metadata": {}}})
    assert backfill.read_tiff_dimensions(client, "bucket", "a.ptif") == (70000, 60000)


def test_read_tiff_dimensions_rejects_bigtiff_magic():
    body = bytearray(build_minimal_tiff(800, 500))
    body[2:4] = struct.pack("<H", 43)  # BigTIFF magic instead of 42
    client = FakeS3Client({"a.ptif": {"body": bytes(body), "content_type": "x", "metadata": {}}})
    with pytest.raises(backfill.UnsupportedTiffError):
        backfill.read_tiff_dimensions(client, "bucket", "a.ptif")


def test_read_tiff_dimensions_rejects_unrecognized_byte_order():
    body = b"XX" + build_minimal_tiff(800, 500)[2:]
    client = FakeS3Client({"a.ptif": {"body": body, "content_type": "x", "metadata": {}}})
    with pytest.raises(backfill.UnsupportedTiffError):
        backfill.read_tiff_dimensions(client, "bucket", "a.ptif")


def test_backfill_object_skips_already_tagged_metadata():
    client = FakeS3Client(
        {
            "a.ptif": {
                "body": b"",
                "content_type": "application/octet-stream",
                "metadata": {"width": "800", "height": "500", "pages": "3"},
            }
        }
    )
    result = backfill.backfill_object(client, "bucket", "a.ptif", dry_run=False)
    assert result == "skipped-already-tagged"
    assert client.copy_calls == []


def test_backfill_object_dry_run_does_not_call_copy_object():
    body = build_minimal_tiff(800, 500)
    client = FakeS3Client(
        {"a.ptif": {"body": body, "content_type": "application/octet-stream", "metadata": {}}}
    )
    result = backfill.backfill_object(client, "bucket", "a.ptif", dry_run=True)
    assert result == "dry-run"
    assert client.copy_calls == []


def test_backfill_object_copy_preserves_content_type_and_sets_metadata():
    body = build_minimal_tiff(800, 500)
    client = FakeS3Client(
        {"a.ptif": {"body": body, "content_type": "image/tiff", "metadata": {}}}
    )
    result = backfill.backfill_object(client, "bucket", "a.ptif", dry_run=False)
    assert result == "updated"
    assert len(client.copy_calls) == 1
    call = client.copy_calls[0]
    assert call["Bucket"] == "bucket"
    assert call["Key"] == "a.ptif"
    assert call["CopySource"] == {"Bucket": "bucket", "Key": "a.ptif"}
    assert call["MetadataDirective"] == "REPLACE"
    assert call["ContentType"] == "image/tiff"
    assert call["Metadata"] == {
        "width": "800",
        "height": "500",
        "pages": str(backfill.calculate_pyramid_pages(800, 500)),
        "tilesize": str(backfill.PYRAMID_TILE_SIZE),
    }


def test_iter_ptif_keys_filters_by_suffix_and_respects_limit():
    client = FakeS3Client(
        {
            "collections/x/1.ptif": {},
            "collections/x/manifest.json": {},
            "collections/x/2.ptif": {},
            "collections/x/3.ptif": {},
        }
    )
    keys = list(
        backfill.iter_ptif_keys(client, "bucket", "collections/", limit=2)
    )
    assert len(keys) == 2
    assert all(k.endswith(".ptif") for k in keys)
