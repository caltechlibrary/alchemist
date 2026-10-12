# Alchemist Configuration

Alchemist reads its configuration from a `settings.ini` file. Copy
[example-settings.ini](example-settings.ini) and fill in the values for your
environment; every setting is described there.

```bash
cp example-settings.ini settings.ini
```

By default `alchemist.py` reads `settings.ini` from its own directory. Pass
`--settings /path/to/settings.ini` to use a file elsewhere:

```bash
uv run alchemist.py --settings /path/to/settings.ini validate --target publication --context <CONTEXT>
```

`settings.ini` holds credentials, so keep it out of version control
(`settings*.ini` is ignored).

## Host requirements

The machine that runs Alchemist needs:

- the source volumes mounted under `SOURCE_MOUNT_PARENT`
- the external tools named by `MAGICK_CMD`, `VIPS_CMD` (built with PDF
  support), `FFPROBE_CMD`, `FFMPEG_CMD` and `S5CMD_CMD`
- network access to the S3 buckets, CloudFront and ArchivesSpace API in the
  settings, and to github.com for the `arkminter` and `cascflow` dependencies

## Logging

The `[loggers]`, `[handlers]` and `[formatters]` sections configure logging.
The example writes `alchemist.log` to the current working directory.
