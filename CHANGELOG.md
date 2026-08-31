# Alchemist Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.5.3]

### Fixed

- `create_pyramid_tiff()` and `create_canvas_metadata()` no longer mis-parse `magick identify` output for multi-frame images -- `-format` is emitted once per frame with no separator, so a TIFF carrying an embedded reduced-resolution preview (as Capture One writes on export from the iXG copy stand) yielded `TIFF*12381*9926TIFF*160*128`, which crashed `create_pyramid_tiff()` with "too many values to unpack (expected 3)" and silently gave `create_canvas_metadata()` a corrupt canvas height like `9926TIFF`; both now parse only the first frame, which is the one vips reads when building the pyramid
- `loop_over_archival_object_files()` now calls `.result()` on its futures and raises naming the files that failed -- worker exceptions were previously discarded, so a failed derivative still logged "DERIVATIVE FILE PROCESSING COMPLETE" and the object went on to be published with missing derivatives before dying with an opaque `IndexError` in `create_digital_object_file_versions()`

## [3.5.2]

### Fixed

- `migrate_legacy_s3_object()` now derives the legacy representative `*.ptif` filename authoritatively from the digital_object's existing `image-thumbnail` file_version URL (`get_legacy_thumbnail_identifier()`), instead of guessing from an S3 listing -- legacy naming conventions vary by collection (some collections name their PTIFs after the component_id itself, like `EX-7.ptif`, with no sequence suffix at all), so a single-file legacy object could be migrated under the wrong filename

## [3.5.1]

### Fixed

- legacy `*.ptif` redirect markers now store the literal new S3 key (ending in `.ptif`) in `WebsiteRedirectLocation` instead of a bare IIIF identifier, so each marker points at a concrete target like the `index.html`/`manifest.json` markers

## [3.5.0]

### Added

- `migrate_legacy_s3_object()`: both the `metadata` and `files`/`publication` targets now fully migrate an archival object still on Alchemist's pre-ARK-migration S3 layout the first time they touch it -- copying its pyramid TIFFs to the ARK-based key when no fresh derivatives are otherwise being uploaded, and writing zero-byte `WebsiteRedirectLocation` markers at the legacy `index.html`/`manifest.json`/`*.ptif` keys so old bookmarks/search-engine links keep working; pairs with cascflow v4.5.0's `URL-Redirected` relabeling of the retired file_versions

### Changed

- pin cascflow to v4.5.0

### Fixed

- the `metadata` target now skips archival objects that have never been published via `files`/`publication` (e.g. only have a Distillery-minted ARK), logging a clear error instead of crashing with an opaque "MANIFEST NOT FOUND IN S3" error deep in `generate_iiif_manifest()`
- `generate_iiif_manifest()`'s metadata-only update now locates the existing manifest via the digital_object's "Web-Access" file_version instead of assuming the ARK-based key -- objects published before the ARK migration and not yet re-touched by `files`/`publication` have their manifest.json migrated to the ARK-based key on this first metadata-only touch instead of raising "MANIFEST NOT FOUND IN S3"

## [3.4.8]

### Changed

- `digital_object_id` is now derived from the archival object's ARK instead of `component_id` everywhere a digital_object is created or updated (cascflow v4.4.0); requires `external_ark_url` to already be set

### Fixed

- `is_archival_object_eligible_for_publication()` now only treats *published* `file_versions` as "already published for web access" -- Distillery's own unpublished OCFL inventory file_versions on the same digital_object no longer trip a false "DIGITAL OBJECT ALREADY HAS FILE VERSIONS" error

## [3.4.7]

### Changed

- use cascflow's shared `invalidate_cloudfront_paths()` instead of a local copy; pin cascflow to v4.3.2

## [3.4.6]

### Changed

- pin cascflow to v4.2.2, which types `config()` with `decouple`'s real overloads instead of an untyped passthrough
- drop redundant f-string wraps around already-string values

## [3.4.5]

### Changed

- log unhandled exceptions through the standard logger (`❌ UNEXPECTED ERROR: ...`) before re-raising, so a crash always leaves a clean error line in the console log instead of jumping straight to a bare traceback
- demote the settings-validation success message to DEBUG so the first line of output is the identifier/summary line (or a real error)

## [3.4.3]

### Fixed

- fix `OUR_SHOULDER` incorrectly marked required in `ALCHEMIST_SETTINGS_SPEC` (`get_our_ark()` already treats a blank shoulder as valid); `validate` was failing for deployments that don't set one

## [3.4.2]

### Changed

- set `ContentType` to `image/tiff` explicitly on pyramid TIFFs (both the forward publish path and the backfill script), instead of preserving s5cmd's generic `application/octet-stream` fallback for the unrecognized `.ptif` extension; `_update_pyramid_tiff_metadata()` no longer needs a `head_object()` call now that the value is fixed and known up front

## [3.4.1]

### Added

- add `scripts/backfill_pyramid_tiff_metadata.py`, a standalone one-off tool to attach `x-amz-meta-width`/`height`/`pages`/`tilesize` to pyramid TIFFs published before that metadata was written at publish time; reads image dimensions directly from each object's TIFF IFD via small S3 Range GETs rather than downloading files

### Fixed

- fix `_update_pyramid_tiff_metadata()` resetting `ContentType` to a service default when attaching pyramid TIFF metadata (`copy_object` with `MetadataDirective="REPLACE"` doesn't preserve system metadata that isn't explicitly repeated); the existing `ContentType` is now read via `head_object()` and passed through

## [3.4.0]

### Added

- attach `x-amz-meta-width`/`height`/`pages`/`tilesize` to pyramid TIFFs on publish, so `serverless-iiif` can read image geometry from S3 object metadata instead of recalculating it on every request
- `create_pyramid_tiff()` writes a `.metadata.json` sidecar with the computed values; `publish_archival_object_access_files()` applies them via a threaded, same-key S3 metadata copy after the bulk `s5cmd sync` (which only supports one uniform `--metadata` value per batch)

## [3.3.1]

### Changed

- pin cascflow to v4.2.1

### Fixed

- fix Digital Object records not staying in sync when an Archival Object's title changes: metadata-only runs now update the existing Digital Object's title and File Version captions via new `update_digital_object_metadata()`; `create_digital_object_file_versions()` picks up the Digital Object title sync from `cascflow.save_digital_object_file_versions()`

## [3.3.0]

### Added

- add settings.ini validation to the `validate` command (checks required variables are set and usable: binary paths, directories, URLs)

### Changed

- clean up example-settings.ini: remove unused `ARCHIVESSPACE_BASIC_AUTH_*` keys, document `IIIF_CLOUDFRONT_DISTRIBUTION_ID` and the ARK keys (`OUR_NMA`, `OUR_NAAN`, `OUR_SHOULDER`, `RESOLVER_BUCKET`)
- pin cascflow to v4.2.0

## [3.2.2]

### Changed

- bump arkminter pin to v0.2.1 (fixes minted ARK names occasionally containing a `/` as the check digit)

## [3.2.1]

### Added

- add pytest CI workflow

### Changed

- use arkminter's shared `get_existing_our_ark` instead of a local copy
- pin arkminter and cascflow to tagged releases (v0.2.0, v4.1.1)

### Fixed

- fix `get_our_ark` to use one shared S3 client for both the update and mint paths (previously the mint path silently fell back to the default AWS credential chain instead of configured credentials)

## [3.2.0]

### Added

- integrate arkminter for ARK minting and metadata management
- refactor publication workflow to use ARK identifiers instead of component IDs
- add ARK-aware canvas metadata and IIIF manifest generation
- expand test coverage with ARK-specific unit tests and integration tests
- upgrade dependencies (boto3, pytest, ruff, and others)

## [3.1.0]

### Added

- add to [README](README.md) and [CONFIGURATION](CONFIGURATION.md) files
- upgrade dependencies
- begin changelog
