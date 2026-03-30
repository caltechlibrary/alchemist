from pathlib import Path


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


def test_has_sequence_indicator_true():
    # The function expects at least three underscore-separated components, last must be 3 digits or 3 digits + r/v
    assert alchemist.has_sequence_indicator("foo_001_001") is True
    assert alchemist.has_sequence_indicator("foo_001_001r") is True
    assert alchemist.has_sequence_indicator("foo_001_001v") is True


def test_has_sequence_indicator_false():
    assert alchemist.has_sequence_indicator("file_no_seq") is False


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
    ao = {
        "publish": False,
        "restrictions_apply": True,
        "has_unpublished_ancestor": False,
        "title": "Test Title",
        "uri": "test-uri",
    }
    assert alchemist.is_archival_object_eligible_for_publication(ao, "pipeline") is False


def test_is_publication_file_supported_true():
    assert alchemist.is_publication_file_supported(Path("foo.tiff")) is True


def test_is_publication_file_supported_false():
    assert alchemist.is_publication_file_supported(Path("foo.unsupported")) is False
