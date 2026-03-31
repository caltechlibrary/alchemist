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
    assert alchemist.has_valid_sequence_indicators(files) is False

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
