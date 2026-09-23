# S3 as the source library

`input_type = s3` makes CasterPak read source videos from an S3 bucket (or anything that speaks the
S3 API: MinIO, Wasabi, Cloudflare R2). Code: `vodhls/media_manifest_s3.py`.

```ini
[input]
input_type = s3

[s3]
bucket = my-video-library
prefix = videos/
region = us-east-1
```

## How a URL becomes an S3 key

Plain concatenation - the same rule as `videoParentPath` for the filesystem input:

```
key = [s3] prefix + <path in the URL>

URL   http://video.example.com/i/alice/holiday.mp4/master.m3u8
key   videos/alice/holiday.mp4                (prefix = videos/)
```

S3 has no directories. `/` is just a character in the key, and a "folder" is a set of keys that
share a prefix - which is exactly what makes a per-user layout (`videos/<user>/...`) cheap: nothing
to create, nothing to walk. This is the same trick Google Drive-style path resolvers use, minus the
folder-ID lookups, because S3 lets the path *be* the key.

Consequences worth knowing:

- **The URL is the key.** Nothing to keep in sync, no database. A file uploaded to the right key by
  *any* tool (console, `aws s3 cp`, another service) is streamable immediately.
- **Names are limited by `pathsafety.py`**, same as every backend: letters, digits, `_ - + .`. An
  object whose key contains a space or comma is simply unreachable through CasterPak.
- **Case matters.** S3 keys are case-sensitive, so `Clip.mp4` and `clip.mp4` are different videos.
- `prefix` may be empty (bucket root). Leading/trailing slashes on it are ignored.

## Slow network, billed bytes: fetch once

Every byte read from S3 costs latency and (out of AWS) money, so the object is downloaded **once**
into the input cache (`[input] videoCachePath`) and everything after that - Bento4, ffmpeg,
re-packaging - reads the local copy. That is the same mechanism the `http` input uses, with three
hardening steps the `http` one does not have:

- The file appears in the cache **atomically** (temp name, then rename), so a half-downloaded video
  is never mistaken for a cache hit.
- A per-object **file lock** means several gunicorn workers hitting the same cold video download it
  once, not once each.
- Large objects download with parallel range requests (`max_concurrency`).

The cleaner ages cached copies out (`[cache] input_file_age` / `input_file_cache_size`), so a video
that is popular stays local and one that isn't costs one re-download the next time it is asked for.
Size the cache volume for your hot set.

## Credentials

**Best: put nothing in `config.ini`.** On EC2/ECS, leave `access_key_id` / `secret_access_key`
blank and attach an IAM role to the instance/task; boto3 picks it up. There is then no secret to
leak, rotate, or commit.

Otherwise use the environment (`CASTERPAK_S3_ACCESS_KEY_ID`, `CASTERPAK_S3_SECRET_ACCESS_KEY`)
rather than the file. CasterPak logs its whole config at startup; option names containing
`secret`, `password`, `token`, `access_key` or `_code` are masked in that log.

### Least-privilege policy

CasterPak only ever reads. This is all it needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-video-library/videos/*" },
    { "Effect": "Allow", "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::my-video-library",
      "Condition": { "StringLike": { "s3:prefix": "videos/*" } } }
  ]
}
```

`s3:ListBucket` looks unnecessary and is not: **without it S3 answers 403, not 404, for a key that
does not exist.** CasterPak cannot tell that from a real permissions problem, so it reports it as a
backend error (HTTP 500 plus an `access denied` line in the log) rather than as a missing video.
With `ListBucket` granted, a missing video is a clean 404.

(The upload side - the library service - needs `s3:PutObject` on the same prefix. Give it its own
role; do not widen this one.)

## What works, what does not (yet)

| Endpoint | With `input_type = s3` |
|---|---|
| `/i/<path>/master.m3u8` single bitrate | works |
| `/i/<path>_,360p,720p,.mp4.csmil/master.m3u8` (renditions already in the bucket) | works; a rendition missing from the bucket is skipped, as on the filesystem |
| `/i/abr/<path>/master.m3u8` auto-encode | **not supported.** The route and `EncodingManager` read `[filesystem] videoParentPath` directly. Making them go through the input backend is the next step (Phase D). |

## Errors

| Situation | Response |
|---|---|
| Object does not exist (and `ListBucket` granted) | 404 |
| Bad credentials, access denied, throttled, S3 unreachable | 500, reason in the log (`InputFetchError`) |
| `[s3] bucket` not set | 500, `ConfigurationError` in the log |

## Why boto3 and not FUSE or HTTP

- **FUSE (`mountpoint-s3`, `s3fs`)** would let the *filesystem* input read S3 with no new code. It
  needs `/dev/fuse` and `SYS_ADMIN` (or a privileged container), which is a real hole to punch in
  an otherwise unprivileged container; and mp4 packaging seeks around inside the file, which is
  the access pattern network-backed mounts are worst at. Rejected.
- **HTTP (`input_type = http`)** already works for a *public* bucket or a CloudFront/presigned base
  URL with zero code. Fine for a public demo library. It cannot do private buckets, IAM roles, or
  tell "missing" from "forbidden".
- **boto3** turned out to be small (~150 lines) because `MediaManager_Base` was already built around
  "fetch to the input cache, then read locally". It is the only option that gives private buckets
  and IAM roles.

## Testing without AWS (no cost)

- `vodhls/tests/test_media_manifest_s3.py` uses [moto](https://github.com/getmoto/moto), an
  in-process S3. Nothing leaves the machine.
- For a real running CasterPak against a fake S3: `moto_server -p 5599`, then set
  `CASTERPAK_S3_ENDPOINT_URL=http://127.0.0.1:5599`, `CASTERPAK_S3_ADDRESSING_STYLE=path`.
  MinIO works the same way.
- See `docs/test-access.md` for how to get a *real* bucket safely.
