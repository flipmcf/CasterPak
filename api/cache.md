# Cache

Status: **draft / planned.** Not implemented.

This document describes the cache features we want as a hierarchy of capabilities. It does not
define URLs or HTTP verbs yet. Where a point is a proposal rather than something we decided, it is
marked **Proposed** and repeated under Open questions.

## What is cached today

| Layer | Config | Contents | Cleaned by the cleaner today? |
|---|---|---|---|
| HLS output cache | `[output] segmentParentPath` | Segment directories and media playlists, one per rendition | Yes, by age and by size. They are tracked in the cache DB. |
| HLS output cache | same | **Master manifests**, one per distinct CSMIL string | **No.** They are never recorded in the DB, so they are never removed. |
| Input cache | `[input] videoCachePath` | Copies of videos fetched from the library, and the `<video>.transcodes/` renditions that `/i/abr/` encodes | Input copies: yes, by age and size. |

Master manifests and files that are not in the DB are invisible to the cleaner. See
"Master manifests never expire" below.

## Feature hierarchy

Each level of cache removal removes more and creates CPU usage. Level 3 removals will create
significant CPU usage.

1. **Manifests**: master and media manifests. Takes a video (by filename) or `all`.
   Cheap and always safe: manifests are rebuilt on the next request.
2. **Segments**: segment data. Takes a video or `all`. **Also removes the manifests** (level 1),
   because they describe those segments.
3. **Input cache**: the copy of a video fetched from the library. Takes a video by filename or
   `all`. **Also removes that video's segments and manifests** (levels 1 and 2), because they
   derive from the input.

Level 3 does **not** remove transcodes. That takes a separate argument, described next.

### Level 3 is expensive, and `all` is dangerous

Removing an input copy is cheap. Paying for it later is not: the next request for each video
fetches it from the library again (ingress bandwidth) and, for videos served through `/i/abr/`,
may transcode it again (CPU). With `all`, that happens for every video in the cache.

Because of that, level 3 with `all` needs a **confirmation**. It takes a few requests to complete,
not one.

**Proposed:** the inspection request (below) returns a confirmation token that identifies exactly
what it reported, and the deletion must present that token. Nobody can clear the whole cache by
sending one request by accident.

### Removing transcodes is a separate request

Deleting a file from the input cache is not the same as deleting its transcodes. Transcodes take
real encode time to recreate and are the only copy. A request to remove them must say so with a
separate argument. Removing an input copy never removes transcodes on its own.

## Inspection mirrors deletion

Every cache operation has an inspection form. The same path and the same arguments, requested with
`GET`, report what `DELETE` would remove, without removing it: what would go, how many files, how
many bytes. The response shape is the same in both cases, so a `GET` shows exactly what the
matching `DELETE` will do.

The same data could also fill the `hls_cache` block of `GET /api/video`.

## Copy transcodes back to the library

A cache feature that fetches transcodes out of the input cache and copies them back into the
user's library, next to the source video as `<video>.transcodes/`.

Why: people who use `/i/abr/` to do their encoding probably want to keep the result. Those
renditions live in the cache, where a transcode removal deletes them. Once copied back, they
follow the bring-your-own layout and belong to the user.

### When it is available

Only for input setups that can be written to:

- The input source must have `readonly` set to `false`. This is a new config item. It is added to
  the input source adapters that could plausibly be written to, such as S3 or rsync, and to
  writable filesystems.
- HTTP sources are read-only by design. Copy-back on an HTTP source returns an error.
- Otherwise copy-back is refused. The library stays read-only to CasterPak unless you opt in.

`GET /api/backends` already carries a `readonly` field per backend (see [backends.md](backends.md)),
which is the same setting.

## Removing a rendition

Some cases the cache levels cannot solve. When a video goes viral, the owner may need to remove the
720p on purpose because they can no longer afford its bandwidth. That is not cache expiry. It means:

- delete the rendition file, and
- discard every manifest and segment that lists it.

How this works depends on the URL style:
- **`/i/abr/` URLs:** the ladder is server-side, so the server can change it.
- **Hand-built `.csmil` URLs:** the ladder is written in the URL. The server can only remove the
  file, and a URL that still lists 720p serves whatever remains.

### Per-video ladders: the SMIL file is the ladder

A video's ladder is a SMIL file stored with its transcodes, and that file is the only copy. A
`.smil` URL names no renditions, so the ladder can change without changing any embedded URL.

- **The cache DB is ephemeral.** It may hold an index derived from SMIL files, such as which videos
  have which renditions. That index is rebuilt by scanning the files, and is never the only copy of
  anything.
- **Editing means writing the file.** The API edits the SMIL. Someone editing it by hand is an
  equally valid edit. Concurrent edits are last write wins.
- **A bad SMIL does not break streaming.** CasterPak validates the file when it reads it. If a SMIL
  is malformed or unreadable, streaming for that video falls back to the default ladder from
  `[encoding_ladder]` and writes an error to the error log. It never crashes the server.
- **A read-only library takes edits in the cache.** Editing the ladder of a video whose transcodes
  are in a read-only library writes a SMIL in the cache. The library's own SMIL is never modified.
  A SMIL in the cache is cache: it can be deleted along with the cache, and the library's ladder
  applies again.
- **Durability follows the transcodes.** An ABR ladder lives beside its transcodes in the cache.
  Copy-back moves the transcodes and their SMIL into the library.

#### Protecting a SMIL file

Setting a SMIL read-only stops CasterPak from editing it. An edit request for a protected file is
refused with a clear error, logged, and CasterPak carries on.

Read-only mode bits are not enough. Replacing a file by writing a temporary file and renaming it
over the original ignores the original's permission bits. For an ordinary user, a file with mode
`444` reports as not writable, and a rename still replaces it. CasterPak therefore checks
writability before it replaces a file, and treats any permission error as a refusal.

On Linux, the stronger protection is the immutable attribute:

```
sudo chattr +i <file>     # protect
sudo chattr -i <file>     # allow edits again
```

An immutable file cannot be written, deleted or renamed over, even by root. It needs Linux and a
filesystem that supports it, such as ext4, xfs or btrfs.

#### SMIL specification

The ladder is SMIL 3.0, exactly as defined in Chapter 6:
[SMIL 3.0 Content Control](https://www.w3.org/TR/REC-smil/smil-content.html). Only what that
chapter defines is used, with nothing added.

The chapter has five modules: BasicContentControl, CustomTestAttributes, PrefetchControl,
SkipContentControl and RequiredContentControl.

What in it is useful to us:

| Feature | What it does | Use for us |
|---|---|---|
| `switch` with `systemBitrate` | `switch` picks the first child whose tests pass. `systemBitrate` is the approximate bandwidth available to the system, in bits per second. | The core of a ladder: one child per rendition, each with its bitrate. CasterPak reads **all** the children, since it builds a manifest from the whole set and does not choose one. |
| `system-bitrate` | The SMIL 1.0 hyphenated spelling. SMIL 3.0 calls it deprecated. | Accept both spellings when reading, since older SMIL files use the hyphenated form. |
| `systemScreenSize` | Syntax is `Screen-height "X" Screen-width`, height first. | Rendition resolution. 720p is `720X1280`, not `1280X720`. |
| `allowReorder` on `switch` | Lets the player pick the best match, not the first. Added in SMIL 3.0. | Signals that child order is not a preference order. |
| `customAttributes` and `customTest` | Author-defined named tests. `customTest` has `defaultState` (`true` or `false`), `override` (`visible` or `hidden`) and `uid`. | **Idea:** mark a rendition as switched off without deleting its file. It stays listed but its test is false, so it is skipped. That is a reversible answer to the viral-video case. |

## Master manifests never expire

The cleaner works only from the cache DB. Master manifests are written without a DB record, so they
are never cleaned. The Readme documents this as intentional for now, on the grounds that they are
small.

The consequence is staleness, not size. A master manifest built while a rendition was missing is
served indefinitely, even after the rendition is added. Requesting a CSMIL URL that lists a
missing rendition produces a manifest without it, and that manifest stays.

Decision: **timestamp comparison is enough** to fix staleness. A cached manifest is rebuilt when it
is older than the ladder file (SMIL) or any rendition it lists. This is a change to manifest
serving, separate from the API. It does not solve the "remove a rendition on purpose" case above.

## Authentication

Every operation here is destructive or reveals server layout. See [auth.md](auth.md).

## Open questions

1. **URL and verb layout.** Deliberately undecided.
2. **Confirmation for level 3 `all`.** How many requests, and is the token proposal above right?
   Does the same confirmation apply to `all` at levels 1 and 2, or only level 3?
3. **Removing transcodes.** The separate argument is deliberately undefined: this is architecture,
   not implementation.
   - Can it be used on its own, removing transcodes while leaving the input copy?
   - Does it accept `all`? If so, does it need the same confirmation?
   - Should it warn, or refuse, when the transcodes were never copied back to the library?
4. **Copy-back details.**
   - Copy or move? Does it overwrite existing files in the library?
   - After a successful copy, can the cache copies be removed automatically?
   - Is `readonly` true by default, so nothing writes unless it is set to `false`?
   - Which sources get `readonly`: local filesystem, S3, rsync, all writable ones?
5. **Manifest cleanup.** Timestamp comparison fixes stale manifests but not accumulation: each
   distinct CSMIL string still leaves a file behind forever. Should master manifests also be
   recorded in the cache DB so the cleaner ages them out?
