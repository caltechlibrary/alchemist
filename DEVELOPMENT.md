# 🛠️ Alchemist Development Guide

## Table of Contents

- [Quick Start](#quick-start)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Dependency Management](#dependency-management)
  - [Updating Dependencies](#updating-dependencies)
  - [Dependency Structure](#dependency-structure)
  - [Managing Local vs. Published Dependencies](#managing-local-vs-published-dependencies)
  - [Front-End Packages](#front-end-packages)
- [Release & Versioning](#release--versioning)
- [Local Development Workflows](#local-development-workflows)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)
- [Resources](#resources)

## Quick Start

### Prerequisites

- Python 3.13 (managed via `.python-version`)
- `uv` package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))

### Setup Local Environment

```bash
cd alchemist
uv venv                          # Create virtual environment
uv sync --all-groups             # Install dependencies + dev deps
```

The project uses `[tool.uv.sources]` to manage `arkminter` and `cascflow` dependencies. During development, these point to local editable installs so changes are immediately reflected:

```toml
[tool.uv.sources]
arkminter = { path = "../arkminter", editable = true }
cascflow = { path = "../cascflow", editable = true }
```

If you modify either of these sibling packages, changes are immediately reflected in alchemist without reinstalling.

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with verbose output
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_alchemist_helpers.py -v

# Run specific test
uv run pytest tests/test_alchemist_helpers.py::test_has_valid_sequence_indicators -v
```

### Test Coverage

The tests cover:

- ArchivesSpace integration (`test_alchemist_archivesspace.py`)
- Helper functions like sequence validation, formatting (`test_alchemist_helpers.py`)
- Integration workflows with mocked ArchivesSpace (`test_alchemist_integration_mocked_aspace.py`)
- Publishing the self-hosted front-end packages (`test_publish_frontend_assets.py`)

Tests use pytest fixtures to mock ArchivesSpace responses and maintain deterministic behavior.

## Code Quality

### Linting & Formatting

```bash
# Check code with Ruff
uv run ruff check .

# Format code with Ruff
uv run ruff format .

# Both check and format
uv run ruff check . --fix && uv run ruff format .
```

## Dependency Management

### Updating Dependencies

```bash
# Update all dependencies (generates new uv.lock)
uv lock --upgrade

# Update specific package
uv lock --upgrade-package boto3

# Add new dependency
uv add <package-name>

# Add dev dependency
uv add --group dev <package-name>
```

After updating dependencies, test locally:

```bash
uv sync --all-groups
uv run pytest tests/ -v
```

### Dependency Structure

**Core dependencies** (from `pyproject.toml`):

- `arkminter` - ARK minting integration
- `boto3` - AWS S3 integration
- `cascflow` - ArchivesSpace workflow library
- `jinja2` - Template rendering
- `python-decouple` - Configuration management

**Dev dependencies**:

- `decouple-types` - Type hints for python-decouple
- `pytest` - Testing framework
- `ruff` - Linting & formatting

### Managing Local vs. Published Dependencies

The dependencies section in `pyproject.toml` remains constant. The `[tool.uv.sources]` section controls whether packages come from local paths (development) or published GitHub tags (releases).

#### Development Workflow (with local editable installs)

For simultaneous development of alchemist with `arkminter` and/or `cascflow`:

```bash
# Initial setup
cd alchemist
uv sync --all-groups

# Make changes to ../arkminter or ../cascflow
cd ../arkminter
# ... edit files ...

# Changes are immediately available in alchemist
cd ../alchemist
uv run pytest tests/ -v  # Sees the changes immediately
```

**No need to reinstall**—editable installs pick up changes automatically.

#### Release Workflow (with published versions)

When releasing alchemist, switch `[tool.uv.sources]` to point to published GitHub tags:

##### Step 1: Determine published versions

```bash
# Check what versions are available
gh release list -R caltechlibrary/arkminter | head -5
gh release list -R caltechlibrary/cascflow | head -5
```

##### Step 2: Update [tool.uv.sources] only

Keep the dependencies section identical. Only change the sources:

```toml
# Before (development)
[tool.uv.sources]
arkminter = { path = "../arkminter", editable = true }
cascflow = { path = "../cascflow", editable = true }

# After (release)
[tool.uv.sources]
arkminter = { git = "https://github.com/caltechlibrary/arkminter", tag = "v0.1.0" }
cascflow = { git = "https://github.com/caltechlibrary/cascflow", tag = "v4.1.0" }
```

##### Step 3: Update uv.lock and verify

```bash
uv lock
uv sync --all-groups
uv run pytest tests/ -v
uv run ruff check .
```

##### Step 4: Commit and create release tag

```bash
git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "Release 3.2.0 - use published arkminter and cascflow"
git tag -a v3.2.0 -m "Release v3.2.0"
git push origin v3.2.0
```

##### Step 5: Switch back to development mode

After releasing, restore local editable paths:

```toml
[tool.uv.sources]
arkminter = { path = "../arkminter", editable = true }
cascflow = { path = "../cascflow", editable = true }
```

Then resync:

```bash
uv sync --all-groups
```

### Quick Reference: Switching Between Modes

**Switch to release mode:**

```bash
# Edit pyproject.toml: change [tool.uv.sources] entries to use git tags
# Then:
uv lock
uv sync --all-groups
uv run pytest tests/ -v
```

**Switch back to dev mode:**

```bash
# Edit pyproject.toml: change [tool.uv.sources] entries to use local paths
# Then:
uv sync --all-groups
```

### Front-End Packages

Generated pages load three third-party front-end packages. Alchemist serves
its own copies of them from the Alchemist bucket rather than from a CDN:

| Package | Loaded by | Used on |
|---|---|---|
| Pico CSS | `templates/base.tpl` | every page |
| Universal Viewer | `templates/iiif.tpl` | image pages |
| Mozilla’s PDF.js viewer | `templates/pdf.tpl` | PDF pages |

Each one lives at `{ALCHEMIST_BASE_URL}/alchemist/assets/{name}/{version}/`.
`FRONTEND_PACKAGES` in `alchemist.py` pins each package’s version, download
source, integrity hash, and the files to publish. Universal Viewer and Pico
come from npm; PDF.js’s prebuilt viewer is published only as a GitHub
release zip, so its entry pins the zip’s URL instead. Whatever serves the
published pages must also serve `/alchemist/assets/*` from the bucket;
otherwise the pages load without their styles or viewers.

#### Publishing the packages

`scripts/publish_frontend_assets.py` copies the pinned packages into the
bucket. It is not part of publishing pages. Run it:

- once for each bucket Alchemist publishes to, and
- again whenever a version in `FRONTEND_PACKAGES` changes, before publishing
  with the Alchemist release that pins it.

`alchemist.py validate` fails for every target, naming the script, until
each pinned version’s `.published.json` marker is in the bucket, so a missed
run stops publication rather than producing broken pages.

Run it from a checkout with AWS credentials that can write to the bucket.
It uses your own AWS profile, not the keys in `settings.ini`, which supplies
only the bucket name (`--bucket` overrides it):

```bash
uv run scripts/publish_frontend_assets.py --dry-run
uv run scripts/publish_frontend_assets.py
```

It checks each download against its pinned hash before uploading, never
rewrites a published version, and uploads only missing files, so re-running
it completes a partial upload.

#### Upgrading a package

Every published page keeps the asset URLs it was rendered with, so a
published version must stay in the bucket unchanged; an upgrade publishes
the new version alongside the old one.

1. Update the package’s `version` (and, for PDF.js, `url`) and `integrity`
   in `FRONTEND_PACKAGES`, and check that its `paths` still exist in the new
   download. For an npm package, `npm view <package>@<version>
   dist.integrity` prints the hash. For a release zip, GitHub publishes a
   sha256 digest, which converts to the integrity format like this:

   ```bash
   gh api repos/mozilla/pdf.js/releases/tags/v<version> \
     --jq '.assets[] | select(.name == "pdfjs-<version>-dist.zip") | .digest'
   python3 -c "import base64,sys; print('sha256-' + base64.b64encode(bytes.fromhex(sys.argv[1])).decode())" <hex digest>
   ```
2. Run `scripts/publish_frontend_assets.py` as above.
3. Republish pages for them to pick up the new version; a `metadata` run
   regenerates them. Pages not republished keep loading the old version.

## Release & Versioning

### Version Management

Version is defined in `pyproject.toml`:

```toml
[project]
name = "alchemist"
version = "3.2.0"
```

### Release Checklist

Before merging and releasing a new version:

#### 1. Ensure All Tests Pass

```bash
uv run pytest tests/ -v
```

#### 2. Update CHANGELOG.md

Document changes for this version:

```markdown
## X.Y.Z

- Feature description
- Bug fix description
- Dependency upgrade notes
```

#### 3. Update Version Number

Edit `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"
```

#### 4. Update Dependencies

Ensure dependencies are current:

```bash
uv lock --upgrade
uv sync --all-groups
uv run pytest tests/ -v
```

#### 5. Switch to Published Versions

Update `[tool.uv.sources]` to point to published tags instead of local paths.

#### 6. Create Git Tag

```bash
git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "Release X.Y.Z - <description>"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### Semantic Versioning

Follow [Semantic Versioning](https://semver.org/):

- **Major** (X._._ ): Breaking changes
- **Minor** (_.X._ ): New features (backward compatible)
- **Patch** (_._.X ): Bug fixes

### Example: Releasing 3.2.0 (with arkminter integration)

```bash
# 1. Update and test
uv lock --upgrade
uv sync --all-groups
uv run pytest tests/ -v

# 2. Update changelog
# Edit CHANGELOG.md

# 3. Update version
# Edit pyproject.toml: version = "3.2.0"

# 4. Switch to published versions
# Edit pyproject.toml [tool.uv.sources]:
#   arkminter = { git = "https://github.com/caltechlibrary/arkminter", tag = "v0.1.0" }
#   cascflow = { git = "https://github.com/caltechlibrary/cascflow", tag = "v4.1.0" }

# 5. Lock with published versions
uv lock
uv sync --all-groups
uv run pytest tests/ -v

# 6. Commit and tag
git add CHANGELOG.md pyproject.toml uv.lock
git commit -m "Release 3.2.0 - arkminter integration"
git tag -a v3.2.0 -m "Release v3.2.0 - arkminter integration"
git push origin v3.2.0
```

## Local Development Workflows

### Working with Dependent Packages

If developing `arkminter` and `alchemist` simultaneously:

```bash
# Make changes to ../arkminter/src/...
cd ../arkminter
uv sync

# Changes are immediately available in alchemist (editable install)
cd ../alchemist
uv run pytest tests/ -v
```

### Running Alchemist Commands Locally

```bash
# Validate workflow (requires settings.ini)
uv run alchemist.py validate --target publication --context <CONTEXT>

# Execute workflow (requires settings.ini)
uv run alchemist.py execute --target publication --context <CONTEXT>
```

See [CONFIGURATION.md](CONFIGURATION.md) for settings setup.

## Continuous Integration

`test.yml` runs the tests and Ruff on every push and pull request, and
`tag-release.yml` tags a release when the version in `pyproject.toml`
changes.

## Troubleshooting

### Import Errors with Local Packages

```bash
# Reset environment with fresh dependency install
uv sync --all-groups --fresh
```

### Tests Failing After Dependency Update

```bash
# Rebuild environment and lock file
uv lock --refresh
uv sync --all-groups --fresh
uv run pytest tests/ -v
```

### Settings File Not Found

- Ensure `settings.ini` exists next to `alchemist.py`, or pass `--settings` with its path

### Ruff Formatting Conflicts

```bash
# Run both check and format in one command
uv run ruff check . --fix && uv run ruff format .
```

## Resources

- [ArchivesSpace API Docs](https://archivesspace.github.io/archivesspace/api/)
- [ARK Identifiers](https://arks.org/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [pytest Documentation](https://docs.pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
