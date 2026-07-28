import json
import tempfile

from pathlib import Path
from types import SimpleNamespace

import pytest

import alchemist


def test_format_archival_object_creators_display_handles_empty():
    ao = {"linked_agents": []}
    result = alchemist.format_archival_object_creators_display(ao)
    assert result == {}


def test_format_archival_object_dates_display_handles_empty():
    ao = {"dates": []}
    result = alchemist.format_archival_object_dates_display(ao)
    assert result == []


def test_format_archival_object_extents_display_handles_empty():
    ao = {"extents": []}
    result = alchemist.format_archival_object_extents_display(ao)
    assert result == []


def test_format_archival_object_subjects_display_handles_empty():
    ao = {"subjects": []}
    result = alchemist.format_archival_object_subjects_display(ao)
    assert result == {}


def test_format_archival_object_notes_display_handles_empty():
    ao = {"notes": []}
    result = alchemist.format_archival_object_notes_display(ao)
    assert result == {}


def test_has_valid_sequence_indicators():
    # Contiguous, base only
    files = [
        "foo_001_01.tif",
        "foo_001_02.tif",
        "foo_001_03.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is True

    # Contiguous, r/v only, both present for each
    files = [
        "foo_001_01r.tif",
        "foo_001_01v.tif",
        "foo_001_02r.tif",
        "foo_001_02v.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is True

    # Not contiguous (gap)
    files = [
        "foo_001_01.tif",
        "foo_001_03.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is False

    # r/v present but not both for a number
    files = [
        "foo_001_01r.tif",
        "foo_001_02v.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is False

    # r/v present and base present for a number
    files = [
        "foo_001_01r.tif",
        "foo_001_01v.tif",
        "foo_001_01.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is False

    # r/v for one, base for another (should be fine)
    files = [
        "foo_001_01r.tif",
        "foo_001_01v.tif",
        "foo_001_02.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is True

    # Not enough digits
    files = [
        "foo_001_1.tif",
        "foo_001_2.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is True

    # Not enough components
    files = [
        "foo01.tif",
        "foo02.tif",
    ]
    assert alchemist.has_valid_sequence_indicators(files) is False


def test_is_archival_object_eligible_for_publication_true():
    ao = {
        "publish": True,
        "restrictions_apply": False,
        "has_unpublished_ancestor": False,
        "title": "Test Title",
        "uri": "test-uri",
    }
    assert alchemist.is_archival_object_eligible_for_publication(ao, "pipeline") is True


def test_is_archival_object_eligible_for_publication_false():
    alchemist.config = lambda key, **kwargs: (
        "https://archivesspace.example.edu"
        if key == "ARCHIVESSPACE_STAFF_URL"
        else kwargs.get("default")
    )
    ao = {
        "publish": False,
        "restrictions_apply": True,
        "has_unpublished_ancestor": False,
        "title": "Test Title",
        "uri": "test-uri",
    }
    assert (
        alchemist.is_archival_object_eligible_for_publication(ao, "pipeline") is False
    )


def test_is_archival_object_eligible_for_publication_true_with_only_unpublished_file_versions():
    # Distillery attaches its own file_versions (OCFL inventory copies) to
    # the same digital_object, always unpublished -- these must not be
    # mistaken for previously-published web access files.
    ao = {
        "publish": True,
        "has_unpublished_ancestor": False,
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [
            {
                "digital_object": {
                    "ref": "/repositories/2/digital_objects/1",
                    "_resolved": {
                        "title": "Test Title",
                        "file_versions": [
                            {
                                "file_uri": "file:///preservation/path/inventory.json",
                                "use_statement": "OCFL-Object-Inventory",
                                "publish": False,
                            }
                        ],
                    },
                }
            }
        ],
    }
    assert (
        alchemist.is_archival_object_eligible_for_publication(ao, "publication") is True
    )


def test_is_archival_object_eligible_for_publication_false_with_published_file_versions(
    monkeypatch,
):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: (
            "https://archivesspace.example.edu"
            if key == "ARCHIVESSPACE_STAFF_URL"
            else kwargs.get("default")
        ),
    )
    ao = {
        "publish": True,
        "has_unpublished_ancestor": False,
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [
            {
                "digital_object": {
                    "ref": "/repositories/2/digital_objects/1",
                    "_resolved": {
                        "title": "Test Title",
                        "file_versions": [
                            {
                                "file_uri": "https://example.com/image.tif",
                                "use_statement": "Web-Access",
                                "publish": True,
                            }
                        ],
                    },
                }
            }
        ],
    }
    assert (
        alchemist.is_archival_object_eligible_for_publication(ao, "publication")
        is False
    )


def test_is_archival_object_eligible_for_metadata_update_false_with_no_digital_object(
    monkeypatch,
):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: (
            "https://archivesspace.example.edu"
            if key == "ARCHIVESSPACE_STAFF_URL"
            else kwargs.get("default")
        ),
    )
    ao = {
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [],
    }
    assert alchemist.is_archival_object_eligible_for_metadata_update(ao) is False


def test_is_archival_object_eligible_for_metadata_update_false_with_only_unpublished_file_versions(
    monkeypatch,
):
    # An archival object can have a Distillery-minted ARK and a
    # digital_object with only preservation (OCFL inventory) file_versions,
    # never having gone through Alchemist's `files`/`publication` target --
    # there is no manifest.json in S3 yet to update.
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: (
            "https://archivesspace.example.edu"
            if key == "ARCHIVESSPACE_STAFF_URL"
            else kwargs.get("default")
        ),
    )
    ao = {
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [
            {
                "digital_object": {
                    "ref": "/repositories/2/digital_objects/1",
                    "_resolved": {
                        "title": "Test Title",
                        "file_versions": [
                            {
                                "file_uri": "file:///preservation/path/inventory.json",
                                "use_statement": "OCFL-Object-Inventory",
                                "publish": False,
                            }
                        ],
                    },
                }
            }
        ],
    }
    assert alchemist.is_archival_object_eligible_for_metadata_update(ao) is False


def test_is_archival_object_eligible_for_metadata_update_true_with_published_file_versions():
    ao = {
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [
            {
                "digital_object": {
                    "ref": "/repositories/2/digital_objects/1",
                    "_resolved": {
                        "title": "Test Title",
                        "file_versions": [
                            {
                                "file_uri": "https://example.com/image.tif",
                                "use_statement": "Web-Access",
                                "publish": True,
                            }
                        ],
                    },
                }
            }
        ],
    }
    assert alchemist.is_archival_object_eligible_for_metadata_update(ao) is True


def test_is_archival_object_eligible_for_metadata_update_false_with_multiple_digital_objects(
    monkeypatch,
):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: (
            "https://archivesspace.example.edu"
            if key == "ARCHIVESSPACE_STAFF_URL"
            else kwargs.get("default")
        ),
    )
    ao = {
        "title": "Test Title",
        "uri": "test-uri",
        "instances": [
            {"digital_object": {"ref": "/repositories/2/digital_objects/1"}},
            {"digital_object": {"ref": "/repositories/2/digital_objects/2"}},
        ],
    }
    assert alchemist.is_archival_object_eligible_for_metadata_update(ao) is False


def test_is_publication_file_supported_true():
    assert alchemist.is_publication_file_supported(Path("foo.tiff")) is True


def test_is_publication_file_supported_false():
    assert alchemist.is_publication_file_supported(Path("foo.unsupported")) is False


def test_update_external_ark_url_posts_when_changed(monkeypatch):
    archival_object = {
        "uri": "/repositories/2/archival_objects/1",
        "component_id": "aspace_1",
        "external_ark_url": "https://digital.example.edu/ark:99999/abc123x",
    }
    post_calls = []

    monkeypatch.setattr(
        alchemist.cascflow,
        "archivesspace_get",
        lambda uri: SimpleNamespace(json=lambda: {"external_ark_url": ""}),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "archivesspace_post",
        lambda uri, payload: post_calls.append((uri, payload)),
    )

    alchemist.update_external_ark_url(archival_object)

    assert post_calls == [(archival_object["uri"], archival_object)]


def test_update_external_ark_url_skips_post_when_unchanged(monkeypatch):
    archival_object = {
        "uri": "/repositories/2/archival_objects/1",
        "component_id": "aspace_1",
        "external_ark_url": "https://digital.example.edu/ark:99999/abc123x",
    }
    post_calls = []

    monkeypatch.setattr(
        alchemist.cascflow,
        "archivesspace_get",
        lambda uri: SimpleNamespace(
            json=lambda: {
                "external_ark_url": "https://digital.example.edu/ark:99999/abc123x"
            }
        ),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "archivesspace_post",
        lambda uri, payload: post_calls.append((uri, payload)),
    )

    alchemist.update_external_ark_url(archival_object)

    assert post_calls == []


def test_publish_archival_object_access_files_syncs_to_ark_path(monkeypatch):
    build_directory = tempfile.TemporaryDirectory()
    archival_object = {
        "component_id": "aspace_1",
        "external_ark_url": "https://digital.example.edu/ark:99999/abc123x",
    }
    arrangement = {"collection_id": "collection_1"}
    commands = []

    access_path = Path(build_directory.name, "collection_1", "aspace_1")
    access_path.mkdir(parents=True)
    (access_path / "1.ptif.metadata.json").write_text(
        json.dumps({"width": 4096, "height": 4096, "pages": 5, "tilesize": 256})
    )
    (access_path / "2.ptif.metadata.json").write_text(
        json.dumps({"width": 2048, "height": 1024, "pages": 4, "tilesize": 256})
    )
    (access_path / "3.ptif.metadata.json").write_text(
        json.dumps({"width": 512, "height": 512, "pages": 2, "tilesize": 256})
    )

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "OUR_NMA": "digital.example.edu",
            "S5CMD_CMD": "s5cmd",
            "ALCHEMIST_BUCKET": "bucket-name",
            "AWS_ACCESS_KEY_ID": "access",
            "AWS_SECRET_ACCESS_KEY": "secret",
        }.get(key, kwargs.get("default")),
    )

    def fake_run(cmd, **kwargs):
        commands.append((cmd, kwargs))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(alchemist.subprocess, "run", fake_run)

    copy_calls = []

    class FakeS3Client:
        def copy_object(self, **kwargs):
            copy_calls.append(kwargs)

    monkeypatch.setattr(
        alchemist.boto3, "client", lambda *args, **kwargs: FakeS3Client()
    )

    alchemist.publish_archival_object_access_files(
        build_directory, archival_object, arrangement
    )

    assert len(commands) == 1
    command, kwargs = commands[0]
    assert command == [
        "s5cmd",
        "sync",
        "--exclude",
        "*.metadata.json",
        build_directory.name + "/collection_1/aspace_1/*",
        "s3://bucket-name/ark:99999/abc123x/",
    ]
    assert kwargs["env"]["AWS_ACCESS_KEY_ID"] == "access"
    assert kwargs["env"]["AWS_SECRET_ACCESS_KEY"] == "secret"
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is True
    assert kwargs["text"] is True

    # threaded dispatch means completion order isn't guaranteed; sort by Key
    assert sorted(copy_calls, key=lambda call: call["Key"]) == [
        {
            "Bucket": "bucket-name",
            "Key": "ark:99999/abc123x/1.ptif",
            "CopySource": {"Bucket": "bucket-name", "Key": "ark:99999/abc123x/1.ptif"},
            "Metadata": {
                "width": "4096",
                "height": "4096",
                "pages": "5",
                "tilesize": "256",
            },
            "MetadataDirective": "REPLACE",
            "ContentType": "image/tiff",
        },
        {
            "Bucket": "bucket-name",
            "Key": "ark:99999/abc123x/2.ptif",
            "CopySource": {"Bucket": "bucket-name", "Key": "ark:99999/abc123x/2.ptif"},
            "Metadata": {
                "width": "2048",
                "height": "1024",
                "pages": "4",
                "tilesize": "256",
            },
            "MetadataDirective": "REPLACE",
            "ContentType": "image/tiff",
        },
        {
            "Bucket": "bucket-name",
            "Key": "ark:99999/abc123x/3.ptif",
            "CopySource": {"Bucket": "bucket-name", "Key": "ark:99999/abc123x/3.ptif"},
            "Metadata": {
                "width": "512",
                "height": "512",
                "pages": "2",
                "tilesize": "256",
            },
            "MetadataDirective": "REPLACE",
            "ContentType": "image/tiff",
        },
    ]


@pytest.mark.parametrize(
    "width, height, expected_pages",
    [
        (4096, 4096, 5),
        (256, 256, 1),
        (100, 50, 1),
        (10000, 256, 7),
    ],
)
def test_calculate_pyramid_pages(width, height, expected_pages):
    assert alchemist.calculate_pyramid_pages(width, height) == expected_pages


def test_create_pyramid_tiff_writes_metadata_sidecar(monkeypatch, tmp_path):
    build_directory = SimpleNamespace(name=str(tmp_path))
    filepath = tmp_path / "source.tiff"
    filepath.write_bytes(b"")
    archival_object = {"component_id": "aspace_1"}
    arrangement = {"collection_id": "collection_1"}
    Path(tmp_path, "collection_1", "aspace_1").mkdir(parents=True)

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "MAGICK_CMD": "magick",
            "VIPS_CMD": "vips",
        }.get(key, kwargs.get("default")),
    )

    def fake_run(cmd, **kwargs):
        if "identify" in cmd:
            return SimpleNamespace(stdout="TIFF*4096*4096")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(alchemist.subprocess, "run", fake_run)

    alchemist.create_pyramid_tiff(
        build_directory, filepath, archival_object, arrangement, "1"
    )

    metadata_file = Path(tmp_path, "collection_1", "aspace_1", "1.ptif.metadata.json")
    assert json.loads(metadata_file.read_text()) == {
        "width": 4096,
        "height": 4096,
        "pages": 5,
        "tilesize": 256,
    }


def test_generate_archival_object_page_builds_ark_manifest_url(monkeypatch, tmp_path):
    arrangement = {
        "collection_id": "collection_1",
        "collection_uri": "/repositories/2/resources/1",
    }
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "uri": "/repositories/2/archival_objects/1",
        "external_ark_url": "https://digital.example.edu/ark:99999/abc123x",
        "linked_agents": [],
        "dates": [],
        "extents": [],
        "subjects": [],
        "notes": [],
    }
    build_directory = tempfile.TemporaryDirectory()

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "OUR_NMA": "digital.example.edu",
            "ARCHIVESSPACE_PUBLIC_URL": "https://archivesspace.example.edu",
        }.get(key, kwargs.get("default")),
    )

    class FakeTemplate:
        def render(self, **kwargs):
            return kwargs["iiif_manifest_url"]

    class FakeEnvironment:
        def __init__(self, **kwargs):
            pass

        def get_template(self, name):
            return FakeTemplate()

    monkeypatch.setattr(alchemist.jinja2, "Environment", FakeEnvironment)

    alchemist.generate_archival_object_page(
        build_directory, archival_object, arrangement, mimetype=""
    )

    output_file = (
        Path(build_directory.name) / "collection_1" / "aspace_1" / "index.html"
    )
    assert output_file.exists()
    assert (
        output_file.read_text()
        == "https://digital.example.edu/ark:99999/abc123x/manifest.json"
    )


def test_generate_iiif_manifest_sets_id_and_thumbnail_urls(monkeypatch, tmp_path):
    arrangement = {
        "collection_id": "collection_1",
        "collection_title": "Collection 1",
    }
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
        "linked_agents": [],
        "dates": [],
        "extents": [],
        "subjects": [],
        "notes": [],
    }
    build_directory = tempfile.TemporaryDirectory()
    filepaths = [Path("foo_001_01.tif")]
    sequenced_filepaths = {"0001": Path("foo_001_01.tif")}

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_IIIF_ENDPOINT": "https://iiif.example.edu",
            "OUR_NMA": "resolver.example.edu",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(alchemist, "has_valid_sequence_indicators", lambda fps: True)

    class FakeFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, filepath, archival_object_arg, sequence_indicator_arg):
            return FakeFuture(
                {"@type": "sc:Canvas", "@id": f"canvas:{Path(filepath).stem}"}
            )

    monkeypatch.setattr(alchemist, "ProcessPoolExecutor", FakeExecutor)

    alchemist.generate_iiif_manifest(
        build_directory,
        filepaths,
        archival_object,
        arrangement,
        mimetype="",
        sequenced_filepaths=sequenced_filepaths,
    )

    manifest_path = (
        Path(build_directory.name) / "collection_1" / "aspace_1" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())

    assert (
        manifest["@id"]
        == "https://digital.example.edu/ark:99999/abc123x/manifest.json"
    )
    assert (
        manifest["thumbnail"]["@id"]
        == "https://iiif.example.edu/ark:99999/abc123x/0001/full/200,/0/default.webp"
    )
    assert (
        manifest["thumbnail"]["service"]["@id"]
        == "https://iiif.example.edu/ark:99999/abc123x/0001"
    )


def test_get_published_web_access_url_returns_none_without_digital_object():
    ao = {"instances": []}
    assert alchemist.get_published_web_access_url(ao) is None


def test_get_published_web_access_url_returns_none_without_web_access_file_version():
    ao = {
        "instances": [
            {
                "digital_object": {
                    "_resolved": {
                        "file_versions": [
                            {
                                "file_uri": "file:///preservation/path/inventory.json",
                                "use_statement": "OCFL-Object-Inventory",
                            }
                        ]
                    }
                }
            }
        ]
    }
    assert alchemist.get_published_web_access_url(ao) is None


def test_get_published_web_access_url_returns_legacy_url():
    ao = {
        "instances": [
            {
                "digital_object": {
                    "_resolved": {
                        "file_versions": [
                            {
                                "file_uri": "https://digital.example.edu/collections/collection_1/aspace_1",
                                "use_statement": "Web-Access",
                            }
                        ]
                    }
                }
            }
        ]
    }
    assert (
        alchemist.get_published_web_access_url(ao)
        == "https://digital.example.edu/collections/collection_1/aspace_1"
    )


def test_generate_iiif_manifest_metadata_only_loads_from_ark_key_when_already_migrated(
    monkeypatch,
):
    arrangement = {"collection_id": "collection_1", "collection_title": "Collection 1"}
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
        "linked_agents": [],
        "dates": [],
        "extents": [],
        "subjects": [],
        "notes": [],
        "instances": [
            {
                "digital_object": {
                    "_resolved": {
                        "file_versions": [
                            {
                                "file_uri": "https://digital.example.edu/ark:99999/abc123x",
                                "use_statement": "Web-Access",
                            }
                        ]
                    }
                }
            }
        ],
    }
    build_directory = tempfile.TemporaryDirectory()

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "OUR_NMA": "resolver.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
        }.get(key, kwargs.get("default")),
    )

    requested_keys = []

    def fake_s3_get_object(bucket, key):
        requested_keys.append(key)
        return {
            "Body": SimpleNamespace(
                read=lambda: json.dumps(
                    {"@id": "https://old-id-does-not-matter", "sequences": []}
                ).encode()
            )
        }

    monkeypatch.setattr(alchemist.cascflow, "s3_get_object", fake_s3_get_object)

    alchemist.generate_iiif_manifest(
        build_directory,
        [],
        archival_object,
        arrangement,
        mimetype="",
        sequenced_filepaths={},
    )

    assert requested_keys == ["ark:99999/abc123x/manifest.json"]
    manifest_path = (
        Path(build_directory.name) / "collection_1" / "aspace_1" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    # already at the ARK key -- @id is left as whatever was already stored
    assert manifest["@id"] == "https://old-id-does-not-matter"


def test_generate_iiif_manifest_metadata_only_migrates_from_legacy_key(monkeypatch):
    arrangement = {"collection_id": "collection_1", "collection_title": "Collection 1"}
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
        "linked_agents": [],
        "dates": [],
        "extents": [],
        "subjects": [],
        "notes": [],
        "instances": [
            {
                "digital_object": {
                    "_resolved": {
                        "file_versions": [
                            {
                                "file_uri": "https://digital.example.edu/collections/collection_1/aspace_1",
                                "use_statement": "Web-Access",
                            }
                        ]
                    }
                }
            }
        ],
    }
    build_directory = tempfile.TemporaryDirectory()

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "OUR_NMA": "resolver.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
        }.get(key, kwargs.get("default")),
    )

    requested_keys = []

    def fake_s3_get_object(bucket, key):
        requested_keys.append(key)
        return {
            "Body": SimpleNamespace(
                read=lambda: json.dumps(
                    {
                        "@id": "https://digital.example.edu/collections/collection_1/aspace_1/manifest.json",
                        "sequences": [],
                    }
                ).encode()
            )
        }

    monkeypatch.setattr(alchemist.cascflow, "s3_get_object", fake_s3_get_object)

    alchemist.generate_iiif_manifest(
        build_directory,
        [],
        archival_object,
        arrangement,
        mimetype="",
        sequenced_filepaths={},
    )

    assert requested_keys == ["collections/collection_1/aspace_1/manifest.json"]
    manifest_path = (
        Path(build_directory.name) / "collection_1" / "aspace_1" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    assert (
        manifest["@id"]
        == "https://digital.example.edu/ark:99999/abc123x/manifest.json"
    )


def test_generate_iiif_manifest_metadata_only_raises_when_manifest_missing_everywhere(
    monkeypatch,
):
    arrangement = {"collection_id": "collection_1", "collection_title": "Collection 1"}
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
        "linked_agents": [],
        "dates": [],
        "extents": [],
        "subjects": [],
        "notes": [],
        "instances": [],
    }
    build_directory = tempfile.TemporaryDirectory()

    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "OUR_NMA": "resolver.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(alchemist.cascflow, "s3_get_object", lambda bucket, key: None)

    with pytest.raises(FileNotFoundError, match="MANIFEST NOT FOUND IN S3"):
        alchemist.generate_iiif_manifest(
            build_directory,
            [],
            archival_object,
            arrangement,
            mimetype="",
            sequenced_filepaths={},
        )


def test_build_current_file_versions_returns_three_ark_based_entries(monkeypatch):
    arrangement = {"collection_id": "collection_1", "collection_title": "Collection 1"}
    archival_object = {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
    }
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_IIIF_ENDPOINT": "https://iiif.example.edu",
            "OUR_NMA": "resolver.example.edu",
        }.get(key, kwargs.get("default")),
    )

    file_versions = alchemist.build_current_file_versions(
        archival_object, arrangement, {"0001": Path("0001.ptif")}
    )

    by_use_statement = {fv["use_statement"]: fv for fv in file_versions}
    assert set(by_use_statement) == {"image-thumbnail", "Persistent-URL", "Web-Access"}
    assert (
        by_use_statement["image-thumbnail"]["file_uri"]
        == "https://iiif.example.edu/ark:99999/abc123x/0001/full/200,/0/default.webp"
    )
    assert (
        by_use_statement["Persistent-URL"]["file_uri"]
        == "https://resolver.example.edu/ark:99999/abc123x"
    )
    assert (
        by_use_statement["Web-Access"]["file_uri"]
        == "https://digital.example.edu/ark:99999/abc123x"
    )


def _migration_archival_object(web_access_url):
    return {
        "component_id": "aspace_1",
        "title": "Test Title",
        "external_ark_url": "https://resolver.example.edu/ark:99999/abc123x",
        "instances": [
            {
                "digital_object": {
                    "_resolved": {
                        "file_versions": [
                            {
                                "file_uri": web_access_url,
                                "use_statement": "Web-Access",
                            }
                        ]
                    }
                }
            }
        ],
    }


def test_migrate_legacy_s3_object_returns_none_when_already_ark_based(
    monkeypatch,
):
    archival_object = _migration_archival_object(
        "https://digital.example.edu/ark:99999/abc123x"
    )
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
        }.get(key, kwargs.get("default")),
    )

    result = alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=True
    )

    assert result is None


def test_migrate_legacy_s3_object_returns_none_without_web_access_url(
    monkeypatch,
):
    archival_object = {"instances": []}
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
        }.get(key, kwargs.get("default")),
    )

    result = alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=True
    )

    assert result is None


def test_migrate_legacy_s3_object_returns_none_without_legacy_derivatives(
    monkeypatch,
):
    archival_object = _migration_archival_object(
        "https://digital.example.edu/collections/collection_1/aspace_1"
    )
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(
        alchemist.cascflow, "s3_list_object_keys", lambda bucket, prefix: []
    )

    result = alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=True
    )

    assert result is None


def test_migrate_legacy_s3_object_copies_ptifs_and_writes_markers(monkeypatch):
    archival_object = _migration_archival_object(
        "https://digital.example.edu/collections/collection_1/aspace_1"
    )
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
            "OUR_NMA": "resolver.example.edu",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_list_object_keys",
        lambda bucket, prefix: [
            "collections/collection_1/aspace_1/0001.ptif",
            "collections/collection_1/aspace_1/0001.ptif.metadata.json",
            "collections/collection_1/aspace_1/0002.ptif",
            "collections/collection_1/aspace_1/index.html",
            "collections/collection_1/aspace_1/manifest.json",
        ],
    )
    copy_calls = []
    put_calls = []
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_copy_object",
        lambda bucket, source_key, dest_key: copy_calls.append((source_key, dest_key)),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_put_object",
        lambda bucket, key, **kwargs: put_calls.append((key, kwargs)),
    )

    result = alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=True
    )

    assert result == {
        "0001": Path("0001.ptif"),
        "0002": Path("0002.ptif"),
    }
    assert set(copy_calls) == {
        (
            "collections/collection_1/aspace_1/0001.ptif",
            "ark:99999/abc123x/0001.ptif",
        ),
        (
            "collections/collection_1/aspace_1/0001.ptif.metadata.json",
            "ark:99999/abc123x/0001.ptif.metadata.json",
        ),
        (
            "collections/collection_1/aspace_1/0002.ptif",
            "ark:99999/abc123x/0002.ptif",
        ),
    }
    put_by_key = dict(put_calls)
    assert put_by_key["collections/collection_1/aspace_1/index.html"] == {
        "website_redirect_location": "https://resolver.example.edu/ark:99999/abc123x"
    }
    assert put_by_key["collections/collection_1/aspace_1/manifest.json"] == {
        "website_redirect_location": "https://digital.example.edu/ark:99999/abc123x/manifest.json"
    }
    assert put_by_key["collections/collection_1/aspace_1/0001.ptif"] == {
        "website_redirect_location": "/ark:99999/abc123x/0001"
    }
    assert put_by_key["collections/collection_1/aspace_1/0002.ptif"] == {
        "website_redirect_location": "/ark:99999/abc123x/0002"
    }


def test_migrate_legacy_s3_object_renames_to_canonical_indicator_filenames(
    monkeypatch,
):
    # Legacy filenames don't necessarily already match the {indicator}.ptif
    # convention (pre-ARK naming used the source file's own stem) --
    # get_thumbnail_url()/build_current_file_versions() build the ARK-based
    # IIIF identifier from the indicator alone, so the copy must rename to
    # match, and the redirect marker's value must carry the indicator too.
    archival_object = _migration_archival_object(
        "https://digital.example.edu/collections/collection_1/aspace_1"
    )
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
            "OUR_NMA": "resolver.example.edu",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_list_object_keys",
        lambda bucket, prefix: [
            "collections/collection_1/aspace_1/aspace_1_1.ptif",
        ],
    )
    copy_calls = []
    put_calls = []
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_copy_object",
        lambda bucket, source_key, dest_key: copy_calls.append((source_key, dest_key)),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_put_object",
        lambda bucket, key, **kwargs: put_calls.append((key, kwargs)),
    )

    alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=True
    )

    assert copy_calls == [
        (
            "collections/collection_1/aspace_1/aspace_1_1.ptif",
            "ark:99999/abc123x/0001.ptif",
        )
    ]
    put_by_key = dict(put_calls)
    assert put_by_key["collections/collection_1/aspace_1/aspace_1_1.ptif"] == {
        "website_redirect_location": "/ark:99999/abc123x/0001"
    }


def test_migrate_legacy_s3_object_skips_copy_when_copy_ptifs_false(monkeypatch):
    archival_object = _migration_archival_object(
        "https://digital.example.edu/collections/collection_1/aspace_1"
    )
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: {
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "ALCHEMIST_BUCKET": "test-bucket",
            "OUR_NMA": "resolver.example.edu",
        }.get(key, kwargs.get("default")),
    )
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_list_object_keys",
        lambda bucket, prefix: ["collections/collection_1/aspace_1/0001.ptif"],
    )
    copy_calls = []
    monkeypatch.setattr(
        alchemist.cascflow,
        "s3_copy_object",
        lambda bucket, source_key, dest_key: copy_calls.append((source_key, dest_key)),
    )
    monkeypatch.setattr(
        alchemist.cascflow, "s3_put_object", lambda bucket, key, **kwargs: None
    )

    result = alchemist.migrate_legacy_s3_object(
        archival_object, "ark:99999/abc123x", copy_ptifs=False
    )

    assert result == {"0001": Path("0001.ptif")}
    assert copy_calls == []


def make_settings_validation_results(**overrides):
    base = {"results": [], "missing": [], "invalid": []}
    base.update(overrides)
    return base


def test_validate_settings_for_publication_raises_for_missing_settings():
    settings_validation_results = make_settings_validation_results(
        missing=[{"key": "ALCHEMIST_BUCKET", "kind": "string", "status": "missing", "detail": "ALCHEMIST_BUCKET is not set"}]
    )

    with pytest.raises(RuntimeError, match="SETTINGS VALIDATION FAILED"):
        alchemist.validate_settings_for_publication(settings_validation_results)


def test_validate_settings_for_publication_raises_for_invalid_settings():
    settings_validation_results = make_settings_validation_results(
        invalid=[{"key": "MAGICK_CMD", "kind": "executable", "status": "invalid", "detail": "magick not found"}]
    )

    with pytest.raises(RuntimeError, match="SETTINGS VALIDATION FAILED"):
        alchemist.validate_settings_for_publication(settings_validation_results)


def test_validate_settings_for_publication_happy_path_no_exception():
    settings_validation_results = make_settings_validation_results()

    alchemist.validate_settings_for_publication(settings_validation_results)


def test_alchemist_settings_spec_marks_our_shoulder_optional():
    spec_entry = next(
        item for item in alchemist.ALCHEMIST_SETTINGS_SPEC if item["key"] == "OUR_SHOULDER"
    )
    assert spec_entry.get("required") is False
