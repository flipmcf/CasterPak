# Changelog

All notable changes to CasterPak are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions are the
values in the `VERSION` file.

## [0.9.1-alpha] - 2026-09-18
logging directives in docker-compose so disk space doesn't fill up.



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
