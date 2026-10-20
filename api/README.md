# CasterPak API

Status: **draft / planned.** Nothing described in this folder is implemented yet unless it says so.
This folder records what we want the API to do. It is the place to argue about the design before
writing code.

> **Update:** CasterPak itself is staying a bring-your-own-library streamer and is **not** growing an
> API. Accounts, upload and per-user listing are now built, as a separate service:
> [`library/DESIGN.md`](../library/DESIGN.md). The endpoints below that concern the *library*
> (`library`, `video`, `upload`, `backends`, `auth`) describe that service's territory - read them
> against the design there. Cache and transcode management remain open questions for CasterPak
> proper.

The streaming endpoints (`/i/...`) are documented in the top-level `Readme.md`. This folder covers
the management API under `/api`.

## Documents

| File | Covers |
|---|---|
| [library.md](library.md) | `GET /api/library` - browse the library |
| [video.md](video.md) | `GET /api/video` - metadata and status for one video |
| [upload.md](upload.md) | `POST /api/upload` - add a video to the library |
| [backends.md](backends.md) | `GET /api/backends` - storage backend health |
| [cache.md](cache.md) | Cache levels, inspection, copying transcodes back to the library |
| [auth.md](auth.md) | Authentication for `/api` |
| [transcode.md](transcode.md) | Encode a library video on request; the config switch that turns `/i/abr/` off |

## Conventions (proposed)

- Base path is `/api`. Requests and responses are JSON unless a file is being uploaded.
- Paths are library-relative, start with `/`, and follow the same validation as the streaming
  endpoints (see `pathsafety.py`): no `..`, no `,`, no empty segments.
- Anything that starts work returns `202 Accepted` and finishes in the background. Requests
  never block on an encode.
- Anything destructive or expensive requires authentication from the first release. See
  [auth.md](auth.md).
