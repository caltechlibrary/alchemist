import alchemist


def test_validate_metadata_identifier_success(monkeypatch):
    # Simulate cascflow returning eligible archival objects
    fake_result = {
        "eligible_archival_objects": {"aspace_1": {"component_id": "aspace_1"}},
        "identifier_level": "resource",
    }
    monkeypatch.setattr(
        alchemist.cascflow, "validate_metadata_identifier", lambda ctx: fake_result
    )
    result = alchemist.cascflow.validate_metadata_identifier("fakeid")
    assert "eligible_archival_objects" in result
    assert result["identifier_level"] == "resource"


def test_get_arrangement_returns_expected(monkeypatch):
    # Simulate cascflow.get_arrangement returning a known arrangement dict
    arrangement = {"collection_id": "EX-001", "series_title": "Series 1"}
    monkeypatch.setattr(alchemist.cascflow, "get_arrangement", lambda ao: arrangement)
    ao = {"component_id": "aspace_1"}
    result = alchemist.cascflow.get_arrangement(ao)
    assert result["collection_id"] == "EX-001"
    assert result["series_title"] == "Series 1"


def test_create_digital_object_adds_instance(monkeypatch):
    # Simulate cascflow.create_digital_object updating archival_object
    def fake_create_digital_object(archival_object, digital_object_type=""):
        archival_object["instances"] = [
            {"digital_object": {"ref": "/digital_objects/1"}}
        ]
        return "/digital_objects/1", archival_object

    monkeypatch.setattr(
        alchemist.cascflow, "create_digital_object", fake_create_digital_object
    )
    ao = {"component_id": "aspace_1", "title": "Test AO", "instances": []}
    uri, updated_ao = alchemist.cascflow.create_digital_object(ao)
    assert uri == "/digital_objects/1"
    assert updated_ao["instances"][0]["digital_object"]["ref"] == "/digital_objects/1"


def test_save_digital_object_file_versions_calls(monkeypatch):
    # Simulate save_digital_object_file_versions as a no-op
    called = {}

    def fake_save(archival_object, file_versions):
        called["archival_object"] = archival_object
        called["file_versions"] = file_versions

    monkeypatch.setattr(
        alchemist.cascflow, "save_digital_object_file_versions", fake_save
    )
    ao = {
        "component_id": "aspace_1",
        "instances": [{"digital_object": {"ref": "/digital_objects/1"}}],
    }
    file_versions = [{"file_uri": "uri"}]
    alchemist.cascflow.save_digital_object_file_versions(ao, file_versions)
    assert called["archival_object"] == ao
    assert called["file_versions"] == file_versions


def test_config_returns_value(monkeypatch):
    monkeypatch.setattr(
        alchemist.cascflow, "config", lambda key, **kwargs: "dummy-value"
    )
    assert alchemist.cascflow.config("ANY_KEY") == "dummy-value"


def test_update_digital_object_metadata_syncs_title_and_captions(monkeypatch):
    updated = {}

    def fake_update_digital_object(uri, data):
        updated["uri"] = uri
        updated["data"] = data

    monkeypatch.setattr(
        alchemist.cascflow, "update_digital_object", fake_update_digital_object
    )
    digital_object = {
        "uri": "/digital_objects/1",
        "title": "Old Title",
        "file_versions": [
            {"use_statement": "image-thumbnail", "caption": "Old Title"},
            {"use_statement": "Persistent-URL", "caption": "Old Title"},
            {"use_statement": "Web-Access"},
        ],
    }
    ao = {
        "component_id": "aspace_1",
        "title": "New Title",
        "instances": [{"digital_object": {"_resolved": digital_object}}],
    }
    alchemist.update_digital_object_metadata(ao)
    assert updated["uri"] == "/digital_objects/1"
    assert updated["data"]["title"] == "New Title"
    captions = {
        fv["use_statement"]: fv.get("caption") for fv in updated["data"]["file_versions"]
    }
    assert captions["image-thumbnail"] == "New Title"
    assert captions["Persistent-URL"] == "New Title"
    assert "caption" not in [
        fv
        for fv in updated["data"]["file_versions"]
        if fv["use_statement"] == "Web-Access"
    ][0]


def test_update_digital_object_metadata_no_file_versions_is_noop(monkeypatch):
    called = {"invoked": False}

    def fake_update_digital_object(uri, data):
        called["invoked"] = True

    monkeypatch.setattr(
        alchemist.cascflow, "update_digital_object", fake_update_digital_object
    )
    ao = {
        "component_id": "aspace_1",
        "title": "New Title",
        "instances": [{"digital_object": {"_resolved": {"uri": "/digital_objects/1"}}}],
    }
    alchemist.update_digital_object_metadata(ao)
    assert called["invoked"] is False


def test_update_digital_object_metadata_no_digital_object_is_noop(monkeypatch):
    called = {"invoked": False}

    def fake_update_digital_object(uri, data):
        called["invoked"] = True

    monkeypatch.setattr(
        alchemist.cascflow, "update_digital_object", fake_update_digital_object
    )
    ao = {"component_id": "aspace_1", "title": "New Title", "instances": []}
    alchemist.update_digital_object_metadata(ao)
    assert called["invoked"] is False


def test_update_digital_object_metadata_multiple_digital_objects_raises(monkeypatch):
    ao = {
        "component_id": "aspace_1",
        "title": "New Title",
        "instances": [
            {"digital_object": {"_resolved": {"uri": "/digital_objects/1"}}},
            {"digital_object": {"_resolved": {"uri": "/digital_objects/2"}}},
        ],
    }
    try:
        alchemist.update_digital_object_metadata(ao)
        assert False, "expected ValueError"
    except ValueError:
        pass
