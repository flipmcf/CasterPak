# Transcode

Status: **draft / planned.**

## What we want

An endpoint that takes a video from the user's library and transcodes it into an adaptive bitrate
ladder, on request, without needing a viewer to trigger it.

Today the only way to get CasterPak to encode is to request `/i/abr/<video>/master.m3u8`. That
couples encoding to playback: the first viewer starts a CPU-heavy job, and the person paying for
the server does not control when. An explicit endpoint separates the two.

This fits the architecture: streaming and packaging are the core; encoding is an add-on. With this
endpoint, and `/i/abr/` switched off (below), a site can run CasterPak as a pure packager and
encode only what it chooses to, when it chooses to.

## Endpoint

```http
POST /api/transcode
Content-Type: application/json

{
  "path": "/projects/2024/final_cut.mp4",
  "ladder": ["720p", "480p", "360p"]      // optional; default is every label in [encoding_ladder]
}
```

```http
Response 202 Accepted
{
  "path": "/projects/2024/final_cut.mp4",
  "status": "queued",                      // "queued" | "running" | "ready" | "error"
  "renditions": ["720p", "480p", "360p"],
  "urls": {
    "status": "/api/transcode?path=/projects/2024/final_cut.mp4",
    "csmil": "http://casterpak/i/projects/2024/final_cut.mp4.transcodes/final_cut_,360p,480p,720p,.mp4.csmil/master.m3u8"
  }
}
```

The `csmil` URL is where the result will be playable once `status` is `ready`.

### Status

```http
GET /api/transcode?path=/projects/2024/final_cut.mp4
```

Returns the same shape, with `status` and, per rendition, whether its file exists. It answers
"is it done, and where is it" without anyone having to request the stream.

### Errors

| Code | When |
|---|---|
| `401` / `403` | Not authenticated / not allowed |
| `404` | The source video is not in the library |
| `409` | This video is already queued or encoding. Nothing new is started. |
| `422` | Invalid path, or a `ladder` label that is not configured |

## Behavior

- **Asynchronous.** The request queues the job and returns. It reuses the existing encoding queue
  and dispatcher, so `[encoding] max_concurrent_encodes` applies.
- **Same output as `/i/abr/`.** Renditions are written to `<video>.transcodes/` in the transcode
  cache as `<basename>_<label><ext>`, so every existing way of serving them keeps working.
- **No emergency stream.** `/i/abr/` hands the first viewer a low-quality JIT stream while the real
  encode runs. This endpoint does not, because nobody is watching.
- **Idempotent.** Requesting a video whose renditions already exist does not re-encode. Whether
  a `force` option should exist is an open question.
- **The library is never written to.** Copying finished transcodes back into the library is a
  separate feature.

## Turning off `/i/abr/`

We want a config switch that disables the `/i/abr/` endpoint. A host that only wants
predictable-cost packaging, or that encodes through `/api/transcode`, should not have a public URL
that can start an encode.

```ini
[encoding]
# When False, /i/abr/... does not start encoding. Default True (current behavior).
abr_enabled = True
```

Environment override, following the existing convention: `CASTERPAK_ENCODING_ABR_ENABLED=False`.

- With `abr_enabled = False`, requests to `/i/abr/...` return an error and start nothing: no queue
  row, no JIT stream.
- The encoding dispatcher keeps running. `/api/transcode` still needs it.
- Everything else is unaffected. `.csmil` URLs and single-bitrate streaming never encode.

## Open questions

1. **What does a disabled `/i/abr/` return?** `404` (as if it does not exist) or `403` (it exists but
   is off)? Leaning `404`, with a body that says why.
2. **Is "off" one switch or two?** `/i/abr/` does two things: it redirects to `.csmil` when
   renditions exist (cheap), and it starts encoding when they do not (expensive). A third mode,
   redirect only, would keep the cheap half. `abr_mode = full | redirect_only | off` instead of a boolean.
3. **`force` re-encode.** Needed to replace renditions, for example after a ladder change. Should it
   delete existing files first?
4. **Cancel.** Should `DELETE /api/transcode?path=` cancel a queued or running job?
5. **Per-video ladders.** `ladder` here is a per-request subset. A ladder stored per video is a
   SMIL file, decided in [cache.md](cache.md).
6. **Authentication.** Encoding is expensive, so this endpoint must be authenticated. The scheme is
   decided in the API-wide conventions.
