# CasterPak - Agent Context

## Rules for this file

**This file states what is true now. Nothing else.**

- Describe current decisions and current concepts only. Never describe a past design, why
  something changed, what was fixed, or what a thing "used to" or "no longer" do.
- History lives elsewhere: `CHANGELOG.md`, `git log`, GitHub issues and PRs, `docs/history.md`.
- Planned work lives in `ROADMAP.md`, `Todo.md` and `api/`. Link to it; don't copy it here.
- If you change behaviour, update the matching statement here in place. Delete anything that
  stops being true. Do not leave a note about the old behaviour.
- Do not put snapshots, dates, or version numbers of "latest work" in this file.

## Engineering principles

Build the simple version first and measure before optimizing:

> "We should forget about small efficiencies, say about 97% of the time: premature optimization is
> the root of all evil. Yet we should not pass up our opportunities in that critical 3%."
> - Donald Knuth

Accepted trade-off: a request that needs a source video waits until the input layer has made it a
local file, including the JIT stream's first segment. Do not add streaming reads or other
latency work without a measured problem.

## Working in the container (claude-sandbox)

This repo is worked on inside ephemeral containers started with `claude-here` (from
`~/Projects/claude-sandbox`, run from this directory).

- The entrypoint copies the repo into `/work`, discards uncommitted changes in that copy, and checks
  out (or creates) a `claude` branch. To work on another branch, `git fetch` and `git checkout` it.
- The container is destroyed on exit. Only what is pushed to GitHub survives. Host files are never
  modified.
- **Never merge a PR from inside the container.** Create, push and update PRs freely; a human merges.
- `CLAUDE.md` is a tracked file. Commit it like any other change.

## What CasterPak is

A Flask/gunicorn **HLS video-on-demand packager**. It streams video from an existing library
without migrating or pre-encoding it: it packages HLS on request with Bento4 (`mp42hls`), caches
the result, and can auto-encode an adaptive-bitrate ladder with FFmpeg. It replaces Akamai Media
Services On Demand (MSOD) and accepts MSOD-style `.csmil` URLs.

- Language: Python 3.10, Flask, gunicorn. Binaries: Bento4, FFmpeg. State: SQLite.
- Runs **only as containers**: the `casterpak` app image and the `casterpak-proxy` nginx image,
  via `docker-compose.yml`.
- Repo: https://github.com/flipmcf/CasterPak

## Architecture decisions

- **The segment root comes from config, and everything else comes from the CSMIL descriptor.**
  `MultivariantManager` and `vodhls_master_playlist_factory` are built from a `CsmilDescriptor`
  alone. Never pass them an `output_dir`, a dirname, or a master-playlist name.
  - `MultivariantManager.output_dir` = `<segmentParentPath>/<csmil.dirname>`.
  - The master playlist file name = `csmil.csmil_filename` (no directory).
  - Each rendition's segments are in `<output_dir>/<rendition basename>/`, the same path
    `MediaManager.output_dir` and the master's URLs use.
  - `csmil_string` (has a `dirname/` prefix) is for URLs. `csmil_filename` is for files on disk.
    Using the wrong one doubles the dirname.
- **Renditions are segmented eagerly.** A master-manifest request segments every listed rendition
  (`ProcessSource` in `vodhls/master_manifest.py`) so each rendition's playlist and segments exist
  before a player asks for them. Child-playlist and segment requests create missing segments on
  demand.
- **The input layer is the only code that knows where source videos live.** A video is identified by
  its *library path* (the URL path, e.g. `shows/2024/episode.mp4`). The `MediaManager` selected by
  `[input] input_type` (`vodhls/media_manifest_<type>.py`) maps a library path to a local file
  (`process_input()` makes it available, `input_file` returns it). Routes, `EncodingManager`,
  `JitManager` and cleanup get source files from the input layer and key everything they own by the
  library path: transcode directory, segment directory, cache records. Nothing outside the input
  layer reads an input-type section (`[filesystem]`, `[http]`, ...) or assumes a source is a local
  file under a configured directory. Every route, including `/i/abr/`, works with every input type.
- **Renditions belong in the user's library; auto-encoding is the fallback.** CasterPak works best when
  each video's renditions already exist in the user's library (S3, http, a filesystem, a FUSE or
  NTFS mount): a `.csmil` URL names them, CasterPak packages them as they are, and nothing is
  encoded. A library without renditions can serve only one bitrate. For that case `/i/abr/`
  auto-encodes a ladder, and those renditions are written to the **input cache**
  (`<videoCachePath>/<library path>.transcodes/`), not to the library. Input cache entries expire
  (see Storage), so auto-encoded renditions are deleted and re-encoded on the next `/i/abr/` request.
  Writing them back to the library is a planned, opt-in setting (see Planned work).
- **Every write to a cache is recorded in the cache database.** The cleaner evicts only what the
  database records. A file written to the input cache or segment cache and not recorded is never
  evicted, and the cache fills up. Whatever writes into a cache records the file at write time:
  fetched sources, auto-encoded renditions, segments.
- **CSMIL is stateless.** A rendition list is encoded in the URL; no manifest-description file is
  stored. Rendition filenames are plain concatenation: `prefix + label + suffix`, nothing inserted
  between them (`vodhls/csmil.py`).
- **No ladder database.** A per-video rendition ladder, if built, is a SMIL 3.0 file (Chapter 6,
  Content Control) stored with the transcodes. See `api/cache.md`.
- **Container + gunicorn is the only production path.** Cache cleanup and the encoding dispatcher are
  scheduled by gunicorn's master process (`on_starting` in `gunicorn.conf.py`). There is no cron and
  no systemd unit.
- **Gunicorn owns every log destination.** A CasterPak logger never opens its own file or stream; it
  borrows gunicorn's handlers via `applogging.use_gunicorn_handlers()`, called from the worker
  (`setup_gunicorn_logging` in `casterpak/__init__.py`) and the master (`on_starting`). Each
  re-pointed logger sets `propagate = False`, or it logs twice. Subsystem tags (`[vodhls]`,
  `[cleanup]`, `[encoding]`) are added by `applogging.TagFilter`, a `logging.Filter` on the logger,
  because a Formatter lives on the handler that gets swapped out.
- **This project is not an installed package.** `setup.py` exists but is decorative. Top-level modules
  (`config.py`, `cachedb.py`, `pathsafety.py`, `applogging.py`, `version.py`) are flat modules,
  importable only because the repo root is `sys.path[0]`. Launch things from the repo root, with
  `-m` for nested modules (e.g. `./bin/python -m cleanup.cleaner`), never by nested file path.
- **Input is validated, never mutated.** See Path rules below.
- **Encode commands come from one place.** `EncodingManager.get_ffmpeg_command()` is the only builder
  of encode argv; the queue persists that command and the dispatcher executes it. Do not add another
  source of queued commands.

## Request flows

All streaming routes are in `casterpak/routes.py`.

| URL | Behaviour |
|---|---|
| `/i/<dir>/<video>.mp4/master.m3u8` | Single-bitrate master: a `CsmilDescriptor` with one unlabeled rendition (`bitrates=['']`). |
| `/i/<dir>/<prefix>,<label>,...,<suffix>.csmil/master.m3u8` | Master for renditions that already exist on disk. Writes the master and eagerly segments each rendition. |
| `/i/<dir>/<rendition>/index_0_av.m3u8` | Child (media) playlist; creates it and its segments if missing. |
| `/i/<dir>/<rendition>/segment-N.ts` | Segment. Creates the stream if missing. |
| `/i/abr/<dir>/<video>.mp4/master.m3u8` | ABR state manager (below). |
| `/i/<dir>/<video>.mp4` | Always 404. CasterPak is not a file server. |
| `/d/...`, `/c/...` | Registered, `NotImplementedError`. |

**ABR state manager** (`abr_manifest`):
1. Renditions exist in the input cache at `<videoCachePath>/<library path>.transcodes/` -> `302` to
   the `.csmil` URL. (`EncodingManager.renditions_exist` looks only in the input cache, not in the
   library.)
2. Otherwise queue the background FFmpeg ABR encode (no-op if already queued), then serve the
   **JIT emergency stream**: a low-quality 480p FFmpeg HLS stream written to a `JIT_<name>`
   directory, returned as a master manifest pointing at `/i/JIT_<dir>/index_0_av.m3u8`. The request
   blocks until the first JIT segment exists (5 s timeout). Both the background encode and the JIT
   stream read the source through the input layer.

**Caching headers:** the JIT master manifest is `Cache-Control: no-cache, no-store, must-revalidate`
(plus `Pragma`, `Expires`); JIT media playlists (`JIT_` dirs) are `no-cache`, because they are EVENT
playlists that grow until `#EXT-X-ENDLIST`. Segments set no `Cache-Control`.

**Segment delivery:** with `[output] behind_nginx = True`, Flask returns an empty body plus
`X-Accel-Redirect: /protected_media/<path>` and nginx serves the file from the segment cache. With it
False, Flask serves the bytes itself. Flask adds `Access-Control-Allow-Origin: *` to responses.

**Manifest URLs:** `get_base_url()` builds absolute URLs from `[output] serverName`; with no
`serverName` they are relative. The scheme is `https` if `[output] use_https` is true, otherwise
auto-detected from the request (`X-Forwarded-Proto` is trusted only when `behind_nginx` is true).

## Storage

Paths below are container defaults; each is configurable.

| Layer | Default path | Config |
|---|---|---|
| Source library (read-only) | per input type (`/mnt/data` for the compose filesystem default) | the `[input] input_type` section, e.g. `[filesystem] videoParentPath` |
| Input/transcode cache (read/write) | `/var/cache/casterpak/video_input` | `[input] videoCachePath` |
| HLS segment cache (TTL) | `/var/cache/casterpak/segments` | `[output] segmentParentPath` |
| Cache database | `/var/lib/casterpak/data/cacheDB.db` | env `CASTERPAK_DB_PATH` |

- **Transcodes** (auto-encoded renditions) are written only to the input cache, keyed by the library
  path, whatever the input type:
  `{videoCachePath}/shows/2024/episode.mp4.transcodes/episode_720p.mp4`. Rendition names are
  `<basename>_<label><ext>` (`EncodingManager.rendition_prefix`).
- **Segments** are at `{segmentParentPath}/<dirname>/<rendition>/{index_0_av.m3u8,segment-N.ts}`; the
  CSMIL master playlist is in `{segmentParentPath}/<dirname>/`. Nothing is written directly under
  the segment root except `<dirname>/` trees and `JIT_` directories.
- **Cache database** (SQLite, `cachedb.py`): tables `segmentfile` and `inputfile` track entries for
  TTL cleanup; the `encodingqueue` table is the encode queue.
- **Cleanup** (`cleanup/cleaner.py`) deletes only paths recorded in the database, by TTL
  (`segment_file_age`, `input_file_age`, minutes) and by size threshold. The input layer records an
  input-cache file when it processes it (`process_input()`), which covers fetched sources and
  auto-encoded renditions; both then expire like any input-cache file. Filesystem input with
  `cache_input = False` records nothing, so files in the input cache are never expired. It runs every
  `[cache] cleanup_interval` seconds from gunicorn's master, and standalone with
  `./bin/python -m cleanup.cleaner`.

## Code map

| Path | Role |
|---|---|
| `app.py`, `wsgi.py`, `run.sh` | Entry points; `run.sh` execs gunicorn (4 workers, 120 s timeout). |
| `gunicorn.conf.py` | Master-process hooks: starts cleanup loop and encoding dispatcher. |
| `casterpak/` | Flask app factory (`__init__.py`) and all HTTP routes (`routes.py`). |
| `vodhls/` | HLS packaging: `csmil.py` (descriptor), `master_manifest.py` (`MultivariantManager`), `media_manifest_*.py` (`MediaManager`, per-input-type), `factory.py`. |
| `bento4/` | Bento4 Python wrappers (`mp4hls.py`, `mp4utils.py`). |
| `encoding/` | `EncodingManager` (ladder, ffmpeg command, transcode dir) and `encoding_process_manager.py` (queue + dispatcher). |
| `jit/` | `JitManager`: emergency stream. |
| `cleanup/` | Cache cleaner and maintenance loop. |
| `cachedb.py`, `config.py`, `pathsafety.py`, `applogging.py`, `version.py` | Flat shared modules. |
| `nginx/` | Proxy image: `conf.d/default.conf`, `ssl/`, `config_overrides/` (`*.conf` loaded, `*.inactive` ignored). |
| `api/` | Design docs for the management API. Not implemented. |

## Configuration

`config.ini` (copied from `config_example.ini` when absent) is read by `config.get_config()`.
**Any key can be overridden by env var `CASTERPAK_<SECTION>_<KEY>`** (upper-case), e.g.
`CASTERPAK_OUTPUT_SERVERNAME`. Containers are configured by env vars from `.env` (written by
`./setup`) via `docker-compose.yml`.

Sections: `[application]`, `[cache]`, `[input]`, `[output]`, `[bento4]`, `[ffmpeg]`, `[encoding]`
(`max_concurrent_encodes`, `poll_interval`), `[encoding_ladder]` (`label = resolution, bitrate`),
`[filesystem]`, `[http]`, `[logging]` (`access_log`, `error_log`; `-` is stdout). `[ftp]`, `[sftp]`,
`[scp]`, `[rsync]` are placeholders. The only implemented input types are `filesystem` and `http`;
S3 is not implemented.

## Path rules (security)

- `pathsafety.py` is the single definition of a valid filename/directory segment: letters, digits,
  `_`, `-`, `+`, `.`; no leading `-`; no `,`; no empty segment; not `.` or `..`. Invalid input
  raises `InvalidPathError` and the route returns `422`. It is never rewritten.
- Build filesystem paths from URL input with `safe_join` and treat `None` as an error.
- The source library is read-only to CasterPak; the input/transcode cache and segment cache are
  writable.
- Every subprocess call uses argv-list form, never a shell string.
- The `.csmil` rendition-list delimiter is `,`, which is why `,` is rejected in names.

## Running and testing

- Run the app: `docker compose up -d --build` (after `./setup`). Logs: `docker logs -f casterpak_server`.
- Unit tests: `./bin/pytest` from the repo root (no Docker needed).
- Container tests: `./bin/pytest tests/containertests/run_tests.py -vv`. They need Docker, build and
  run the real stack, and clear the caches between tests.
- Manual checks: `curl -i http://localhost/i/abr/<video>.mp4/master.m3u8` (first call returns the JIT
  manifest; once encoding finishes it returns `302` to the `.csmil` URL).

## Versioning and release

- `VERSION` holds the version. At runtime `CASTERPAK_VERSION` (env, set at image build) wins over
  `VERSION`; `version.py` falls back to `dev`. The version is stamped into generated manifests.
- `CHANGELOG.md` has one section per version; unreleased changes go in the topmost section.
- Release procedure (tagging, images `flipmcf/casterpak` and `flipmcf/casterpak-proxy`, Docker Hub):
  `docs/pushing_to_docker_hub.md`.

## Planned work

- Management API (`GET /api/library`, `/api/video`, `/api/backends`, `POST /api/upload`, cache and
  transcode control, auth): designed in `api/*.md`, with open questions listed in each file.
- S3 input backend and a storage abstraction layer.
- Transcode writeback: an opt-in setting (off by default) that writes auto-encoded renditions back to
  the user's library, so they outlive the input cache.
- Plone integration: a metadata-only `casterpak.video` Dexterity type (`source_path`,
  `streaming_mode` of `single` or `abr`, cached duration/resolution/size/transcode status) and a
  computed HLS URL; a library-browser widget over `/api/library`; an upload handler over
  `/api/upload`. Plone stores no video, only references. Delivery phases: `ROADMAP.md`.

## Glossary

- **ABR**: adaptive bitrate; several renditions the player switches between.
- **CSMIL**: Comma Separated Media Integration Language; a rendition list encoded in the URL
  (see `docs/why_csmil.md`).
- **JIT stream**: the emergency stream served while the real ABR encode runs.
- **Master manifest**: top-level `.m3u8` listing renditions. **Media/child playlist**: one
  rendition's `.m3u8` listing its segments.
- **Rendition**: one encoding of a video at one resolution/bitrate.
- **Segment**: a short `.ts` chunk of a rendition.
- **Transcodes directory**: `<video>.mp4.transcodes/`, holding a video's rendition files.

## Contact

Michael McFadden (`@flipmcf`, flipmcf@gmail.com), OpenForge Solutions, openforgesolutions.com.
