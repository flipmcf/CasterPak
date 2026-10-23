# Contributing to CasterPak

Thanks for wanting to help. CasterPak is a small project with one maintainer, and first-time
contributors are genuinely welcome. If this is your first open source pull request, say so on the
issue you pick and you will get help getting set up.

## Ways to help

- **Docs.** The README has rough edges. Fixing them is a great first PR.
- **Tests.** Add a missing case, or make a brittle test less brittle.
- **Small bugs.** Look for issues labelled `good first issue`.
- **Bug reports.** A clear report with a URL and a log is a real contribution (see below).

For anything larger (a new input type such as S3, the management API designed in `api/`, changes to
routes, caching or encoding) please open an issue first so we agree on the approach before you write
code. A quick conversation is much cheaper than a rejected PR.

## How the project is shaped

Read [`CLAUDE.md`](CLAUDE.md). It is written as context for AI coding agents, but it is also the
most accurate architecture overview we have: request flows, storage layout, a code map and the
rules below, all describing the code as it is now.

The short version:

- A Flask + gunicorn app that packages HLS video on demand with Bento4 and encodes with FFmpeg.
  State lives in SQLite.
- It is deployed as two containers (the app and an nginx proxy) with `docker compose`.
- Top-level modules (`config.py`, `cachedb.py`, `pathsafety.py`, ...) are flat modules, not an
  installed package. Run things from the repo root, and use `-m` for nested modules
  (`./bin/python -m cleanup.cleaner`), never a nested file path.

## Set up a development environment

You need Python 3.10 or newer (the Docker image uses 3.10) and git.

```bash
git clone https://github.com/<your-fork>/casterpak
cd casterpak
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp config_example.ini config.ini
.venv/bin/pytest
```

- `config.ini` is for local development only and is not tracked by git.
- [`docs/development.md`](docs/development.md) has the full dev guide: configuration, running the
  Flask dev server, cache cleanup and debugging.
- The unit tests take a few seconds and need neither Docker nor the Bento4 binaries.
- If pytest stops with "stray SQLite cache database in the repo tree", a `cacheDB.db` file is
  sitting in the repo root and would hide test-isolation bugs. Delete it and re-run:
  `rm -f cacheDB.db cacheDB.db-wal cacheDB.db-shm`

> **Known issue (delete this note once fixed):** `test_get_ffmpeg_command_default` hard-codes
> `-threads 7`, but the code correctly uses your CPU count minus one, so the test only passes on an
> 8-core machine. If it is the only failure you see, your setup is fine. Making the test compute its
> expected value would be a nice first PR.

## Run the whole stack in Docker

Docker is how CasterPak actually runs, so check container-level behavior here.

```bash
./setup                          # asks a few questions, writes .env
docker compose up -d --build
docker logs -f casterpak_server
```

Put an `.mp4` in the video directory you gave `./setup`, then open
`http://localhost/testing/test_player.html` and enter
`http://localhost/i/abr/<yourvideo>.mp4/master.m3u8`.

The container tests build and run the real stack, so they are slower and need Docker:

```bash
./bin/pytest tests/containertests/run_tests.py -vv
```

They refuse to run if a `docker-compose.override.yml` is present. Run them when your change touches
routes, encoding, caching, nginx, `docker-compose.yml` or the `Dockerfile`.

## Rules for code

These are checked in review.

**Security and paths** (details in `CLAUDE.md`, "Path rules"):

- Names that come from a URL are validated, never rewritten. Use `pathsafety.py`; invalid input
  raises `InvalidPathError` and the route returns `422`.
- Build filesystem paths from URL input with `safe_join` (from `werkzeug.utils`), and treat a
  `None` result as an error.
- Subprocess calls use an argv list, never a shell string.
- The source library is read-only to CasterPak. Only the input cache and segment cache are
  written, and every cache write is recorded in the cache database so the cleaner can evict it.
- Never commit secrets, `config.ini`, `.env` or video files. Use the samples in `tests/assets/`.

**Style and scope:**

- Follow the surrounding code. Keep each PR to one concern.
- Add or update tests with your change. For a bug fix, a test that fails before your fix and
  passes after it is ideal.
- A new config key goes in `config_example.ini` with a comment. Any key can be overridden by an
  environment variable named `CASTERPAK_<SECTION>_<KEY>`.
- Dependencies are pinned in `requirements.txt`. Please discuss a new dependency in an issue first.
- New Python files start with the same three-line GPLv2 header as the existing ones.

**Docs:**

- A user-visible change gets an entry in `CHANGELOG.md`, in the topmost (unreleased) section.
- `CLAUDE.md` states what is true now. If your change alters a behavior or decision it describes,
  edit that statement in place. Do not add notes about what used to be true.
- Please do not bump version numbers. The maintainer keeps them in sync at release time
  (see `docs/pushing_to_docker_hub.md`).

## Submitting a change

1. Fork the repo and branch from `master`.
2. Make your change and run the tests. There is no automated CI yet, so please say in the PR what
   you ran.
3. Sign off your commits: `git commit -s`. This adds a `Signed-off-by:` line certifying the
   [Developer Certificate of Origin](https://developercertificate.org/).
   Commit messages are short and say what changed. Reference the issue like `(#58)`; a prefix such
   as `tests:` or `docs:` is welcome.
4. Open a pull request against `master`. Say what changed, why, and how you tested it. Draft PRs
   are welcome if you want early feedback.
5. Expect review comments. Requests for changes are normal and are not a rejection. Reviews are
   done by hand by one person, so please be patient.

## License

CasterPak is licensed under [GPLv2](LICENSE). By contributing, you agree that your contribution is
licensed under the same terms, and your sign-off certifies you have the right to submit it.

## Reporting bugs

Open an issue with:

- the CasterPak version (the `VERSION` file or your image tag) and whether you run Docker or a
  dev install
- your input type and, with anything sensitive removed, the relevant config
- the exact URL you requested and the status code you got
- the relevant log lines (`docker logs casterpak_server`)

Status codes worth knowing: `422` means a filename or directory failed validation (most often a
space or comma); `404` means the source or renditions were not where CasterPak looked; `500` means
packaging failed (usually Bento4 refusing the source file); `504` means encoding failed or timed
out on `/i/abr/`.

**Security problems:** please do not open a public issue. Email mcfaddenm@openforgesolutions.com
instead.

## Conduct

Be kind and constructive, assume good faith, and keep feedback about the code rather than the
person. Harassment and personal attacks are not tolerated, and the maintainer may remove comments
or contributors who engage in them.
