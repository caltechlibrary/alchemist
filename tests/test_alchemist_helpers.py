import json
import tempfile

from pathlib import Path
from types import SimpleNamespace


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


def test_is_publication_file_supported_true():
    assert alchemist.is_publication_file_supported(Path("foo.tiff")) is True


def test_is_publication_file_supported_false():
    assert alchemist.is_publication_file_supported(Path("foo.unsupported")) is False


def test_get_existing_our_ark_returns_none_without_external_ark_url():
    ao = {"component_id": "aspace_1"}
    assert alchemist.get_existing_our_ark(ao) is None


def test_get_existing_our_ark_accepts_our_naan(monkeypatch):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: "99999" if key == "OUR_NAAN" else kwargs.get("default"),
    )
    ao = {
        "component_id": "aspace_1",
        "external_ark_url": "https://digital.example.edu/ark:/99999/abc123x",
    }
    assert alchemist.get_existing_our_ark(ao) == "ark:99999/abc123x"


def test_get_existing_our_ark_rejects_non_our_naan(monkeypatch):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: "99999" if key == "OUR_NAAN" else kwargs.get("default"),
    )
    ao = {
        "component_id": "aspace_1",
        "external_ark_url": "https://n2t.net/ark:/99999/abc123x",
    }
    assert alchemist.get_existing_our_ark(ao) is None


def test_get_existing_our_ark_rejects_invalid_external_ark_url(monkeypatch):
    monkeypatch.setattr(
        alchemist,
        "config",
        lambda key, **kwargs: "99999" if key == "OUR_NAAN" else kwargs.get("default"),
    )
    ao = {
        "component_id": "aspace_1",
        "external_ark_url": "https://example.org/not-an-ark",
    }
    assert alchemist.get_existing_our_ark(ao) is None


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

    alchemist.publish_archival_object_access_files(
        build_directory, archival_object, arrangement
    )

    assert len(commands) == 1
    command, kwargs = commands[0]
    assert command == [
        "s5cmd",
        "sync",
        build_directory.name + "/collection_1/aspace_1/*",
        "s3://bucket-name/ark:99999/abc123x/",
    ]
    assert kwargs["env"]["AWS_ACCESS_KEY_ID"] == "access"
    assert kwargs["env"]["AWS_SECRET_ACCESS_KEY"] == "secret"
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is True
    assert kwargs["text"] is True


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
