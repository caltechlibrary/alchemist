# Alchemist Changelog

## 3.4.4


## 3.4.3

- fix `OUR_SHOULDER` incorrectly marked required in `ALCHEMIST_SETTINGS_SPEC` (`get_our_ark()` already treats a blank shoulder as valid); `validate` was failing for deployments that don't set one

## 3.4.2

- set `ContentType` to `image/tiff` explicitly on pyramid TIFFs (both the forward publish path and the backfill script), instead of preserving s5cmd's generic `application/octet-stream` fallback for the unrecognized `.ptif` extension; `_update_pyramid_tiff_metadata()` no longer needs a `head_object()` call now that the value is fixed and known up front

## 3.4.1

- fix `_update_pyramid_tiff_metadata()` resetting `ContentType` to a service default when attaching pyramid TIFF metadata (`copy_object` with `MetadataDirective="REPLACE"` doesn't preserve system metadata that isn't explicitly repeated); the existing `ContentType` is now read via `head_object()` and passed through
- add `scripts/backfill_pyramid_tiff_metadata.py`, a standalone one-off tool to attach `x-amz-meta-width`/`height`/`pages`/`tilesize` to pyramid TIFFs published before that metadata was written at publish time; reads image dimensions directly from each object's TIFF IFD via small S3 Range GETs rather than downloading files

## 3.4.0

- attach `x-amz-meta-width`/`height`/`pages`/`tilesize` to pyramid TIFFs on publish, so `serverless-iiif` can read image geometry from S3 object metadata instead of recalculating it on every request
- `create_pyramid_tiff()` writes a `.metadata.json` sidecar with the computed values; `publish_archival_object_access_files()` applies them via a threaded, same-key S3 metadata copy after the bulk `s5cmd sync` (which only supports one uniform `--metadata` value per batch)

## 3.3.1

- fix Digital Object records not staying in sync when an Archival Object's title changes: metadata-only runs now update the existing Digital Object's title and File Version captions via new `update_digital_object_metadata()`; `create_digital_object_file_versions()` picks up the Digital Object title sync from `cascflow.save_digital_object_file_versions()`
- pin cascflow to v4.2.1

## 3.3.0

- add settings.ini validation to the `validate` command (checks required variables are set and usable: binary paths, directories, URLs)
- clean up example-settings.ini: remove unused `ARCHIVESSPACE_BASIC_AUTH_*` keys, document `IIIF_CLOUDFRONT_DISTRIBUTION_ID` and the ARK keys (`OUR_NMA`, `OUR_NAAN`, `OUR_SHOULDER`, `RESOLVER_BUCKET`)
- pin cascflow to v4.2.0

## 3.2.2

- bump arkminter pin to v0.2.1 (fixes minted ARK names occasionally containing a `/` as the check digit)

## 3.2.1

- fix `get_our_ark` to use one shared S3 client for both the update and mint paths (previously the mint path silently fell back to the default AWS credential chain instead of configured credentials)
- use arkminter's shared `get_existing_our_ark` instead of a local copy
- pin arkminter and cascflow to tagged releases (v0.2.0, v4.1.1)
- add pytest CI workflow

## 3.2.0

- integrate arkminter for ARK minting and metadata management
- refactor publication workflow to use ARK identifiers instead of component IDs
- add ARK-aware canvas metadata and IIIF manifest generation
- expand test coverage with ARK-specific unit tests and integration tests
- upgrade dependencies (boto3, pytest, ruff, and others)

## 3.1.0

- add to [README](README.md) and [CONFIGURATION](CONFIGURATION.md) files
- upgrade dependencies
- begin changelog
