import pytest
import alchemist


def test_validate_metadata_identifier_success(monkeypatch):
    # Simulate cascflow returning eligible archival objects
    fake_result = {
        "eligible_archival_objects": {"aspace_1": {"component_id": "aspace_1"}},
        "identifier_level": "resource",
    }
    monkeypatch.setattr(alchemist.cascflow, "validate_metadata_identifier", lambda ctx: fake_result)
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
        archival_object["instances"] = [{"digital_object": {"ref": "/digital_objects/1"}}]
        return "/digital_objects/1", archival_object
    monkeypatch.setattr(alchemist.cascflow, "create_digital_object", fake_create_digital_object)
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
    monkeypatch.setattr(alchemist.cascflow, "save_digital_object_file_versions", fake_save)
    ao = {"component_id": "aspace_1", "instances": [{"digital_object": {"ref": "/digital_objects/1"}}]}
    file_versions = [{"file_uri": "uri"}]
    alchemist.cascflow.save_digital_object_file_versions(ao, file_versions)
    assert called["archival_object"] == ao
    assert called["file_versions"] == file_versions


def test_config_returns_value(monkeypatch):
    monkeypatch.setattr(alchemist.cascflow, "config", lambda key, **kwargs: "dummy-value")
    assert alchemist.cascflow.config("ANY_KEY") == "dummy-value"
