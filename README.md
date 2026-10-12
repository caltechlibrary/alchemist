# Alchemist

Alchemist is the Caltech Archives publication and access system. It validates
digital files and their ArchivesSpace metadata, then publishes them: image,
video and PDF pages, IIIF manifests and pyramid TIFFs, ARK redirects, and the
digital object records in ArchivesSpace.

## About this project

Alchemist runs Caltech Archives' digital collections. It is built around
our ArchivesSpace data, storage layout and page design, so it isn't a
general-purpose application. We publish it for reference and so others
can reuse its parts; we can't offer support for running it elsewhere.

## Usage

```bash
uv run alchemist.py validate --target <TARGET> --context <CONTEXT>
uv run alchemist.py execute --target <TARGET> --context <CONTEXT>
```

- `publication` publishes new digital objects from a source volume; the
  context is the volume's name under `SOURCE_MOUNT_PARENT`.
- `files` republishes the digital files of objects already published, from
  a source volume.
- `metadata` regenerates published pages and records from current
  ArchivesSpace metadata; the context is an archival object's component
  unique identifier.

`validate` checks settings, files and ArchivesSpace records without
publishing anything; run it and review its output before `execute`.

## Configuration

See [CONFIGURATION.md](CONFIGURATION.md) for getting started.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for getting started.

## License

Software produced by the Caltech Library is Copyright © 2026 California Institute of Technology. This software is freely distributed under a modified BSD 3-clause license. Please see the [LICENSE](LICENSE) file for more information.
