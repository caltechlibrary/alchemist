# Alchemist

Alchemist is the publication and access system for Caltech Archives. It
takes digital material described in ArchivesSpace and publishes it to the
web as static HTML using the Universal Viewer for IIIF images, HTML5 for
video, and PDF.js for PDF files. We have adopted ARKs for persistent URLs
and reciprocally link between Alchemist pages and ArchivesSpace records.
Much of how it works is specific to our decisions and infrastructure; it is
not standalone software. It is published for anyone to look at and adapt
for other uses.

## Usage

```bash
uv run alchemist.py --help
uv run alchemist.py validate --help
uv run alchemist.py execute --help
```

## Configuration

See [CONFIGURATION.md](CONFIGURATION.md) for getting started.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for getting started.

## License

Software produced by the Caltech Library is Copyright © 2026 California
Institute of Technology. This software is freely distributed under a modified
BSD 3-clause license. Please see the [LICENSE](LICENSE) file for more
information.
