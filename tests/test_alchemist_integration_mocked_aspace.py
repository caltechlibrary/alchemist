import argparse

from pathlib import Path


import alchemist


def test_execute_publication_mints_and_persists_external_ark_url(
    monkeypatch, tmp_path, patch_fake_archivesspace
):
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text("[settings]\nDUMMY=1\n")

    archival_object = {
        "component_id": "aspace_1",
        "title": "Test AO",
        "uri": "/repositories/2/archival_objects/1",
        "linked_agents": [{"title": "Test Creator"}],
        "dates": [{"label": "2024"}],
    }
    arrangement = {"collection_id": "collection_1"}

    patch_fake_archivesspace["archival_objects_by_uri"][archival_object["uri"]] = {
        "uri": archival_object["uri"],
        "component_id": archival_object["component_id"],
        "external_ark_url": "",
    }

    def fake_config(key, **kwargs):
        config_map = {
            "OUR_NMA": "resolver.example.edu",
            "OUR_NAAN": "99999",
            "RESOLVER_BUCKET": "resolver-bucket",
            "ALCHEMIST_BASE_URL": "https://digital.example.edu",
            "AWS_ACCESS_KEY_ID": "dummy",
            "AWS_SECRET_ACCESS_KEY": "dummy",
        }
        return config_map.get(key, kwargs.get("default"))

    # Patch the shared _config singleton directly so cascflow-internal calls,
    # like establish_s3_connection(), see fake_config too -- not just
    # alchemist's own config() calls. Also stub set_config to a no-op so
    # main()'s own real set_config(Config(RepositoryIni(...))) call (reading
    # the near-empty settings_file above) doesn't clobber _config afterward.
    monkeypatch.setattr(alchemist.cascflow.cascflow, "_config", fake_config)
    monkeypatch.setattr(alchemist.cascflow, "set_config", lambda cfg: None)
    monkeypatch.setattr(alchemist.cascflow, "setup_logging", lambda _: None)

    monkeypatch.setattr(
        alchemist.parser,
        "parse_args",
        lambda: argparse.Namespace(
            command="execute",
            target="publication",
            context="VOL-001",
            settings=settings_file.as_posix(),
        ),
    )

    monkeypatch.setattr(
        alchemist.cascflow,
        "execute",
        lambda context, batch_set_id, target: iter(
            [
                (
                    tmp_path / "batch",
                    tmp_path / "stage_2" / "aspace_1",
                    [Path("dummy_001.tif")],
                    archival_object,
                    arrangement,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        alchemist.arkminter, "mint_ark", lambda **kwargs: "ark:99999/abc123x"
    )
    monkeypatch.setattr(
        alchemist, "archival_object_level_processing", lambda *args: None
    )
    monkeypatch.setattr(
        alchemist, "publish_archival_object_access_files", lambda *args: None
    )
    monkeypatch.setattr(
        alchemist, "create_digital_object_file_versions", lambda *args: None
    )
    monkeypatch.setattr(alchemist.cascflow, "move_to_stage_3", lambda *args: None)

    alchemist.main()

    updated = patch_fake_archivesspace["archival_objects_by_uri"][
        archival_object["uri"]
    ]
    assert (
        updated["external_ark_url"] == "https://resolver.example.edu/ark:99999/abc123x"
    )
    assert patch_fake_archivesspace["posts"]
