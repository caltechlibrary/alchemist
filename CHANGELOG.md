# Alchemist Changelog

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
