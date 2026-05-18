import sys

from pathlib import Path
from types import SimpleNamespace


import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def fake_archivesspace_store():
    """In-memory store for deterministic ArchivesSpace-like behavior in tests."""
    return {
        "archival_objects_by_uri": {},
        "posts": [],
    }


@pytest.fixture
def patch_fake_archivesspace(monkeypatch, fake_archivesspace_store):
    """Patch cascflow archivesspace_get/post to use an in-memory test store."""
    import alchemist

    def fake_archivesspace_get(uri):
        payload = fake_archivesspace_store["archival_objects_by_uri"][uri]
        return SimpleNamespace(json=lambda: payload.copy())

    def fake_archivesspace_post(uri, payload):
        fake_archivesspace_store["archival_objects_by_uri"][uri] = payload.copy()
        fake_archivesspace_store["posts"].append((uri, payload.copy()))
        return payload

    monkeypatch.setattr(alchemist.cascflow, "archivesspace_get", fake_archivesspace_get)
    monkeypatch.setattr(
        alchemist.cascflow,
        "archivesspace_post",
        fake_archivesspace_post,
    )
    return fake_archivesspace_store
