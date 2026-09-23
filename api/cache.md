# Cache

Status: **draft / planned.** Not implemented.

This document describes the cache API features. It does not
define URLs or HTTP verbs yet. 

Where a point is a proposal rather than something decided, it is marked **Proposed** and repeated under Open questions.

## What is cached today

| Layer | Config | Contents | Cleaned by the cleaner today? |
|---|---|---|---|
| HLS output cache | same | **Master manifests**, one per distinct CSMIL string | **No.** They are never recorded in the DB, so they are never removed. |
| HLS output cache | `[output] segmentParentPath` | Segment directories and media playlists, one per rendition | Yes, by age and by size. They are tracked in the cache DB. |
| Input cache | `[input] videoCachePath` | Copies of videos fetched from the library, and the `<video>.transcodes/` renditions that `/i/abr/` encodes | Input copies: yes, by age and size. |
| Input cache transcodes | `[input] videoCachePath` | renditions that `/i/abr/` encodes | unknown, I think so.  We probably shouldn't. |

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
4. Transcodes.  You can do it to clean the cache if necessary.

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

Every API DELETE operation has a dupiclate GET inspection form. Same path, same arguments.
`GET`, report what `DELETE` would remove, without removing it: what would go, how many files, how
many bytes. The response shape is the same in both cases, so a `GET` shows exactly what the
matching `DELETE` will do.



## Copy transcodes back to the library

A cache feature that fetches transcodes out of the input cache and copies them back into the
user's library, next to the source video as `<video>.transcodes/`.

Why: people who use `/i/abr/` to do their encoding probably want to keep the result. Those renditions live in the cache, where a transcode removal deletes them. Once copied back, they
follow the "bring-your-own layout" and belong to the user.

### When it is available

Only for input setups that can be written to:

- The input source must have `readonly` set to `false`. This is a new config item that defaults to true to protect the user's video library.  It is added to
  the input source adapters that could plausibly be written to, such as S3 or rsync, and to
  writable filesystems.
- HTTP sources are read-only by design. Copy-back on an HTTP source returns an error.
- Otherwise copy-back is refused. The library stays read-only to CasterPak unless you opt in.

`GET /api/backends` already carries a `readonly` field per backend (see [backends.md](backends.md)),
which is the same setting.

## Removing a rendition

Some cases the cache levels cannot solve. When a video goes viral, the owner may chose to remove an HD rendition on purpose because they can no longer afford its bandwidth. That is not cache expiry. It means we need to discard every manifest and segment that lists it in a stream.

How this works depends on the URL style:
an SMIL file is written to the transcodes directory. 
- **`/i/abr/` URLs:** redirect to a new .CSMIL that does not include the new rendition.
- **Hand-built `.csmil` URLs:** the ladder is written in the URL. Only valid renditions mentioned in the server config or smil will be served, and a 'deactivated' custom SMIL attribute will be honored.

The rendition is not deleted from disk but might be cleaned by the cache rules.

### Per-video ladders: the SMIL file is the ladder

A custom video ladder is a SMIL file stored with its transcodes, and that file is the only copy. A
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
refused with a clear error, logged, and CasterPak carries on.  If the SMIL is writeable, then casterpak does an atomic write to the file by creating a temporary new file with the changes and renames it to replace the old one.   


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
| `customAttributes` and `customTest` | Author-defined named tests. `customTest` has `defaultState` (`true` or `false`), `override` (`visible` or `hidden`) and `uid`. |  mark a rendition as switched off without deleting its file. It stays listed but its test is false, so it is skipped. That is a reversible answer to the viral-video case. |

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


4. **Copy-back details.**
   - Copy or move? Does it overwrite existing files in the library?
   - After a successful copy, can the cache copies be removed automatically?
   - Is `readonly` true by default, so nothing writes unless it is set to `false`?
   - Which sources get `readonly`: local filesystem, S3, rsync, all writable ones?

   
5. **Manifest cleanup.** Timestamp comparison fixes stale manifests but not accumulation: each
   distinct CSMIL string still leaves a file behind forever. Should master manifests also be
   recorded in the cache DB so the cleaner ages them out?
