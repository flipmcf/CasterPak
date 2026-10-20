# CasterPak Library - design

Status: **first version implemented** (accounts, upload, listing, embed URLs; filesystem and S3
storage). Everything under "Open questions" is not.

## What it is

CasterPak is a *bring-your-own-library* HLS streamer. It reads videos from a directory (or, now,
an S3 bucket) and serves them; it has no idea who owns a video and it must not learn. This is the
library you can bring to it: a small service that gives every user **their own directory**, lets them
upload into it, list what they have, and hands back the URL to play or embed each video.

```
                     +------------------+
   browser / Plone   |      nginx       |
   ----------------> |  /api/  -> library    (needs a token, writes)
                     |  /i/... -> casterpak  (needs nothing, reads)
                     +------------------+
                              |                        |
                     +--------v-------+       +--------v--------+
                     | library (5001) |       | casterpak (5000)|
                     +--------+-------+       +--------+--------+
                              | write                  | read
                              v                        v
                     +-----------------------------------------+
                     |  the library: a directory, or S3 bucket |
                     |    <root>/<username>/<folder>/<video>   |
                     +-----------------------------------------+
```

The two services **share nothing but the storage layout**. The library never calls CasterPak and
CasterPak never calls the library. An uploaded file is streamable the moment it lands, because CasterPak
reads the same place. There is nothing to notify, sync, or keep consistent.

### Decisions

| Decision | Why |
|---|---|
| **Separate service, same repo, same image** (`gunicorn "library:create_app()"`) | Streaming stays simple and always up; uploads (slow, large, authenticated) cannot starve playback workers; the library gets write access, CasterPak keeps read-only. Same image because both need `config.py`, `pathsafety.py` (flat modules, no installed package). |
| **It writes where CasterPak reads** - no storage settings of its own | `[input] input_type` and `[filesystem]`/`[s3]` are the single source of truth. Misconfiguring the two services to different places is impossible. |
| **One directory per user**: key = `<username>/<path>` | The username *is* the first URL segment: `/i/alice/trips/holiday.mp4/master.m3u8`. Isolation is structural - there is no request field that can name another user's directory. |
| **Playing needs no account; only writing and listing your own files do** | CasterPak URLs are unauthenticated by design (a `<video>` tag can't send a token). Consequence: anyone with a URL can watch. See "Privacy" below. |
| **Flask + pre-built components, not Django** | Flask is already in the image. Flask-JWT-Extended (tokens), werkzeug scrypt (passwords), Flask-SQLAlchemy (users) cover it. Django would add a second framework, an ORM, an admin and settings system to run beside Flask, for ~5 endpoints. |
| **JWT bearer tokens** (access 15 min + refresh 30 days, refresh revocable) | The shape most API clients, Plone included, already speak. **This is not a full OAuth2 authorization server** - see Open questions. |
| **A database row per upload** (`Video`) as an *index* | Listing is a query, not an S3 LIST or a directory walk; quota is a `SUM()`. The bytes stay in storage. Trade-off: a file placed in the library by other means streams fine but isn't listed. |
| **Uploads never overwrite (409) and appear atomically** | Overwriting a source video would leave CasterPak's cached segments stale for days. Atomic (`link()` from a staging dir, or an S3 object that only appears on completion) means CasterPak can never stream a half-uploaded file. |
| **Names are validated with `pathsafety`, never rewritten** | The same rule CasterPak enforces. A rejected name gets a message saying why; the example page suggests a valid one client-side. |
| **Registration defaults to `closed`** | An open upload endpoint is free storage and free transcoding for the internet. Admins create users with a CLI; `invite`/`open` are opt-in. |
| **The library refuses to start without a 32+ char `jwt_secret`** | A default secret would make every deployment's tokens forgeable. |

## Layout on disk / in S3

```
<videoParentPath or [s3] prefix>/
  .incoming/                   staging for uploads in flight (never a URL; a username can't start with '.')
  alice/
    holiday.mp4                -> /i/alice/holiday.mp4/master.m3u8
    trips/2026/paris.mp4       -> /i/alice/trips/2026/paris.mp4/master.m3u8
  bob/
    ...
```

Usernames: 3-32 chars, `[a-z0-9_-]`, starting with a letter/digit. Names CasterPak's URL space uses
(`abr`, `api`, `protected_media`, ...) are reserved: a user named `abr` would make `/i/abr/x.mp4/...`
ambiguous.

## Endpoints

Base path `/api`. JSON in and out, except upload (multipart). Errors are always
`{"error": {"code": "<stable>", "message": "<for people>"}}`.

| | Auth | |
|---|---|---|
| `GET  /api/health` | - | up? storage type, registration mode |
| `POST /api/users` | - (per `registration`) | create an account. `{username, password, email?, invite_code?}` |
| `POST /api/auth/login` | - | `{username, password}` -> access + refresh token |
| `POST /api/auth/refresh` | refresh token | new access token |
| `POST /api/auth/logout` | refresh token | revoke it |
| `GET  /api/me` | access | account, usage, limits |
| `POST /api/upload` | access | multipart: `file`, `path?` (folder), `filename?` -> `201` with the video, its `urls`, `embed_html` |
| `GET  /api/videos` | access | your videos; `directory`, `limit`, `offset` |
| `GET  /api/videos/<user>/<path>` | access | one of yours; anyone else's is indistinguishable from missing (404) |

Status codes worth knowing: `409` name taken, `413` too large / quota, `415` not a video (extension or
magic bytes), `422` invalid name/path, `401` any token problem (`token_expired`, `token_revoked`, ...).

A video looks like:

```json
{ "id": 7, "path": "alice/trips/paris.mp4", "name": "paris.mp4", "directory": "trips",
  "size": 4500000, "created_at": "2026-09-23T19:41:07Z",
  "urls": { "single": ".../i/alice/trips/paris.mp4/master.m3u8",
            "abr":    ".../i/abr/alice/trips/paris.mp4/master.m3u8",
            "hls":    "<whichever to embed: abr when offered, else single>" },
  "embed_html": "<video ...></video><script>...hls.js...</script>" }
```

`abr` is only offered when CasterPak can auto-encode from the library - today only a filesystem
library (see `docs/s3-input.md`). `[library] abr` overrides.

## Security model

- Passwords: scrypt (werkzeug), 10-128 chars. Login takes the same time and returns the same error
  for an unknown user and a wrong password.
- Tokens are signed with `jwt_secret`; access tokens are not revocable (15 min), refresh tokens are (logout).
  A disabled account's tokens stop working at once (checked per request).
- Uploads: name validated by `pathsafety`; extension allowlist; first bytes must match the container
  (a renamed `.html` or `.exe` is refused); size and per-user quota limits; written via a staging area.
  Not a virus scanner and not a media validator - see Open questions.
- Brute force: nginx rate-limits `/api/auth/login` and `/api/users` to 10/min per IP (burst 10).
- CORS defaults to `*`. Safe *because* the API uses bearer tokens, not cookies: another site cannot
  ride on a logged-in browser. Restrict with `[library] cors_origins` if you like.
- The library container gets the library volume read-write; nothing else does.

### Privacy: anyone with the URL can watch

CasterPak serves whatever is in the library to whoever asks. Listing is private (your own videos, with a
token), but a stream URL is not secret. That is the point of the "no account to watch" design, and it
means upload paths should be treated as unguessable-by-obscurity only. If videos must be private, that
needs signed/expiring URLs in CasterPak (or nginx `secure_link`) - a separate decision, not made here.

## Testing

- `library/tests/` - 100+ tests, no network, no AWS (S3 via moto). `pytest library`.
- `library/smoke_test.py` - end-to-end against RUNNING services (register -> upload -> list -> play).
- `api/postman/` - the same flow as a Postman collection with assertions; runs unchanged in Newman.
- `docs/test-access.md` - how to test against real S3 / a real server without risking cost or production.

## Open questions

1. **OAuth2.** JWT bearer covers "log in and call the API". A real OAuth2 authorization server
   (authorization-code + PKCE, client registration, scopes) is what you'd want if third-party apps,
   or Plone acting on a user's behalf, must get tokens *without ever seeing the password*. Authlib
   provides one for Flask. Not built because nothing needs it yet - **who are the API clients?**
2. **Deleting and replacing videos.** Deliberately absent: a delete/replace leaves CasterPak's cached
   segments (up to `segment_file_age`, 3 days) and transcodes serving the old video. Needs a
   cache-invalidation story first (`api/cache.md`), which CasterPak itself should own.
3. **Private videos** (see Privacy). Signed URLs, or is public-by-URL acceptable?
4. **Ingest validation.** `ffprobe` on upload would catch corrupt files and iPhone-style files Bento4
   chokes on (`Todo.md`), and could reject them at upload instead of at first play. It costs a
   subprocess per upload; where it runs (inline vs queue) is open.
5. **Upload size and speed.** One request per file, buffered by nginx. Multi-GB uploads over bad links
   want resumable uploads (tus, or S3 multipart with presigned URLs straight from the browser - which
   also takes the bytes off this service entirely).
6. **Upload plumbing.** Flask spools the whole upload to a temp file before the endpoint runs, and
   `LocalStorage` then copies it into place: a 2 GB upload briefly needs ~4 GB of scratch space. And an
   upload killed mid-copy leaves a file in `.incoming/` that nothing sweeps yet (a startup/cron sweep of
   files older than a day is a few lines). Streaming the body straight to storage would fix both.
7. **Stream-during-upload** (Roadmap Phase D) is impossible with atomic uploads; it needs the opposite
   trade-off.
8. **Schema migrations.** Tables are created with `create_all()`. The first schema change needs
   Alembic (Flask-Migrate).
9. **Refresh-token rotation, password reset, email verification, user self-deletion.** None exist.
   Reset and verification need an email sender, i.e. a new dependency and an operations decision.
10. **Users beyond a flat namespace** (teams, shared folders, admin role) - `is_active` is the only
   privilege bit today.
11. **SQLite** is right for one host. A second library instance needs Postgres (`database_url` is
    already a SQLAlchemy URL).
