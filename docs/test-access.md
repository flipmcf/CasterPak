# Testing against real S3 and real servers - without the risk

Claude (and CI) can test everything in this repo with **no AWS account and no access to production**:

- S3 code runs against [moto](https://github.com/getmoto/moto), an in-process fake (`pytest`), or
  against `moto_server` / MinIO as a real local endpoint (`CASTERPAK_S3_ENDPOINT_URL=...`).
- The library + CasterPak pair runs entirely on localhost (`library/README.md`), and
  `library/smoke_test.py` and the Postman collection exercise it over real HTTP.

What that can't prove is the last mile: real IAM permissions, real S3 latency, real TLS/nginx/DNS. Here
is how to give an automated session access to those *without* handing over the keys to the kingdom, in
order of preference.

## S3

**1. A throwaway bucket in a separate AWS account (best).** Create a new account under your AWS
Organization (or a fresh one) used only for testing. Whatever goes wrong - a leaked key, a runaway loop -
the blast radius is that account and its budget. Put a **Budget with a hard alert** ($5, $20) on it.

**2. Otherwise, a dedicated IAM user with a tightly scoped policy** on one test bucket:

```json
{ "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::casterpak-test-scratch/test/*" },
    { "Effect": "Allow", "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::casterpak-test-scratch",
      "Condition": { "StringLike": { "s3:prefix": "test/*" } } },
    { "Effect": "Deny", "Action": ["s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketAcl",
                                     "s3:DeleteObject", "s3:PutLifecycleConfiguration"],
      "Resource": "*" }
  ] }
```

Guard rails that matter more than the policy, because cost is what you're afraid of:

- **A bucket lifecycle rule that expires everything under `test/` after 1 day**, so nothing accumulates.
- **A tiny test fixture** (the 6-second `tests/assets/test-video.mp4`, or smaller). Data transfer *out*
  of S3 to the internet is the real bill; a few MB costs nothing, a mis-aimed loop over a 10 GB video
  does not. Keep videos out of the test bucket.
- **Same region as the machine running the tests**, so transfer is free.
- **Budget alert + a CloudWatch billing alarm.** An alert, not a cap - AWS has no hard cap - which is why
  a separate account (option 1) is the only real limit.
- **Short-lived credentials** (an IAM role assumed via SSO / `aws sts assume-role` with a 1-hour session)
  instead of a long-lived access key, so nothing in a container outlives the session. Pass them as the
  standard `AWS_*` environment variables; CasterPak's `[s3]` credential options can stay blank.
- **Never put the keys in `config.ini`.** They go in the environment of that one session
  (`CASTERPAK_S3_ACCESS_KEY_ID` / `CASTERPAK_S3_SECRET_ACCESS_KEY`, masked in CasterPak's startup log).

**3. Free alternatives to AWS**: MinIO in a container, Cloudflare R2 (no egress fees), or Backblaze B2 -
all speak the S3 API, so the code path is identical: set `[s3] endpoint_url` and
`addressing_style = path`. Not proof against AWS-specific behaviour (notably the 403-vs-404 `ListBucket`
rule in `docs/s3-input.md`), but it exercises real network I/O for cents.

## video.casterpak.com (production)

Nothing automated should touch production. To test the same deployment shape:

**1. A staging clone (best).** `docker compose --profile library up` on a small separate host or a second
compose project, behind its own name (`staging.casterpak.com`, or an unrouted IP), with its own
`HOST_VIDEO_PATH`, its own `CASTERPAK_LIBRARY_JWT_SECRET`, and `registration = open` or `invite`. The
Postman "staging" environment (`api/postman/casterpak-staging.postman_environment.json`) and
`smoke_test.py --library ... --casterpak ...` point straight at it. Tear it down after.

**2. If it must be production**: read-only only, and fenced.
- Give the session a **read-only** identity: a shell user with no docker/sudo and read access to logs
  (`journalctl`, `docker logs` via a wrapper), not a general SSH login.
- Test against a **dedicated test user directory** (`/mnt/data/_qa/`), with a library account whose
  username is that directory - never run the smoke test as an existing user.
- Restrict at the edge: an nginx `allow <test-ip>; deny all;` on a `/qa/` path, or a separate
  `server_name`, so test traffic can't be confused with (or reach) customer content.
- No `POST /api/upload`, no `/i/abr/` (it starts CPU-heavy encodes on the production box) unless you
  mean to.

**3. Observability instead of access.** Often the question is "what did production do?". A read-only
Grafana/CloudWatch dashboard or a log export answers it with no shell at all.

## Recommended setup for a Claude session

1. Local everything, moto for S3 (what was done here) - covers ~all logic.
2. Then a **separate-account scratch bucket** + short-lived role for one afternoon of real-S3 checks.
3. Then a **staging clone** for the browser/nginx/TLS pass.
4. Production stays human-only.
