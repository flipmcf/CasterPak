# Changelog

All notable changes to CasterPak are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions are the
values in the `VERSION` file.

## [0.9.2-alpha] - Unreleased

Not tagged and no Docker image published yet.

### Changed
- **BREAKING: CasterPak is container-only.** Bare-metal/systemd deployment
  (`casterpak.service`) and crontab-driven cleanup (`crontab.tpl`) are removed.
  Cleanup and encoding are scheduled only by gunicorn's master process
  (`on_starting` in `gunicorn.conf.py`).
- **BREAKING: logging has one model, gunicorn owns every destination.**
  The `cache_log` and `encoding_log` settings (and
  `CASTERPAK_LOGGING_CACHE_LOG`) no longer exist. Cleanup and encoding borrow
  gunicorn's handlers, so `access_log` and `error_log` are the only log
  destinations; `-` means stdout. Remove the two keys from your `config.ini`.
- Log lines are tagged by subsystem (`[vodhls]`, `[cleanup]`, `[encoding]`) with
  a logger `Filter`, so the tag survives handler swaps.
- `cleanup/cleaner.py` logs to stdout when run standalone, and runs as
  `./bin/python -m cleanup.cleaner` from the repo root.
- `docker-compose.yml`: `json-file` log rotation (10 MB, 3 files) on both
  services, so container logs don't fill the disk.

### Fixed
- **`/i/abr/` works with every input type (#58).** It used to read `[filesystem] videoParentPath`
  itself, so it worked only with `input_type = filesystem`. The source video now comes from the
  input layer (`MediaManager.process_input()` / `input_file`), and `EncodingManager` is keyed by the
  library path: it takes the library path, and the local file to encode is passed to
  `queue_background_encoding()`. Transcodes still live at
  `<videoCachePath>/<library path>.transcodes/`. Encode queue lock names are now library paths
  (they were absolute file paths), so an encode queued before upgrading is not recognised as
  in progress. The input cache directory is now always created at startup.
- **CSMIL/ABR renditions were segmented twice (#54).** Since `1c31f2d`, the
  master manifest request wrote every rendition's segments into the segment
  cache root, where nothing serves them, and the first child playlist request
  segmented them again under `<name>.transcodes/`: about twice the segment disk,
  and the root-level copies were never cleaned up. `MultivariantManager` no
  longer takes an `output_dir`; its directory and master playlist name are built
  from the CSMIL descriptor alone. **Existing installs:** delete the stray
  rendition directories at the top of the segment cache.
- JIT (emergency) streams are no longer cacheable. The JIT master manifest from
  `/i/abr/` is sent with `Cache-Control: no-cache, no-store, must-revalidate`
  (plus `Pragma` and `Expires`), so a cache can't keep serving the emergency
  stream after renditions are ready and never see the redirect to CSMIL.
- JIT media playlists (`JIT_` directories) send `Cache-Control: no-cache`
  explicitly. They are growing EVENT playlists, and previously stayed
  uncacheable only through `send_file`'s default.

### Added
- Management API design docs in `api/` (library, video, upload, backends,
  transcode, cache, auth). Design only, nothing is implemented.
- Docker Hub release process in `docs/pushing_to_docker_hub.md`.
- Unit tests for the cache headers on JIT manifests, and a container-test
  assertion on the JIT master manifest headers.

### Known issues
- `segment()` tries to Bento4-create a missing segment for `JIT_` directories,
  which fails with a 500 instead of a 404 (#51).

## [0.9.1-alpha] - 2026-09-18

### Changed
- **BREAKING: CSMIL rendition filenames are built by plain concatenation.**
  A rendition file is `prefix + label + suffix`, exactly as written in the URL.
  CasterPak no longer inserts a `_` between the prefix and the label, which
  matches Akamai MSOD's `.csmil` grammar. Any separator the files use (`_`,
  `-`, `.`, or none) is part of the prefix.

  | Files on disk | Old URL | New URL |
  |---|---|---|
  | `bbb_360p.avi` | `bbb,360p,.avi.csmil` | `bbb_,360p,.avi.csmil` |
  | `bbb-360p.avi` | not addressable | `bbb-,360p,.avi.csmil` |

  If you built CSMIL URLs by hand without the trailing separator, add it to the
  prefix. URLs produced by `/i/abr/` redirects are updated automatically.

### Fixed
- Bring-your-own transcodes with any naming scheme other than `<name>_<label>`
  can now be served. Previously `bbb_,360p,...` looked for `bbb__360p.avi` and
  returned 404, and the Readme's own examples had the same problem.
- Readme example URL typo (`hidef,mp4` should be `hidef,.mp4`).

### Added
- `[http] connect_timeout` and `transfer_timeout` settings for HTTP sources
  (defaults: 5 seconds to connect, 300 seconds for the full transfer).
- Encoding output naming lives in one place: `EncodingManager.rendition_delimiter`
  and `rendition_prefix`.
- Unit tests for bring-your-own transcode naming schemes.
- Documentation updates: install and hosting instructions, streaming endpoint
  and caching details in the Readme.

## [0.9.0-alpha] - 2026-09-15

First tagged release. The `/i/abr/` auto-encode route works end to end.

### Added
- **`/i/abr/<path>/master.m3u8`**: adaptive bitrate streaming from a single
  source file.
  - If renditions already exist in `<video>.transcodes/`, it returns a `302`
    redirect to the matching `.csmil` URL.
  - If not, it queues high-quality background encoding and serves a low-quality
    just-in-time (JIT) emergency stream so playback can start immediately.
- Background encoding runs through a queue and a dedicated encoding process
  manager, with process locks so concurrent requests don't start duplicate
  encodes.
- Configurable encoding ladder (`[encoding_ladder]`), with defaults for 1080p
  through 240p.
- Transcode cache layout mirrors the source video's path, so nested videos get
  their own `.transcodes` directories.
- CSMIL endpoint (`.csmil`) serving master manifests from existing renditions,
  and single-bitrate HLS streaming, with segment and input-file caching.
- nginx front end in the Docker Compose stack: X-Accel-Redirect segment
  delivery (`behind_nginx`), HTTPS support, and automatic restart on reboot.
- Container test suite, install script, and hosting instructions (cache,
  library and OS volumes).

### Security
- URL path handling validates filenames and directories instead of rewriting
  them: invalid names are rejected with `422`, `,` is reserved as the CSMIL
  delimiter, and names may not start with `-`.
- Fixed a potential ffmpeg argument injection.

[0.9.1-alpha]: https://github.com/flipmcf/CasterPak/compare/0.9.0-alpha...0.9.1-alpha
[0.9.0-alpha]: https://github.com/flipmcf/CasterPak/releases/tag/0.9.0-alpha
