# CasterPak Roadmap

**MVP target:** end of Phase D — "something I can demo and show value."
Post-MVP feature ideas and risks live in `Todo.md` and are intentionally out of scope until
Phase D is done.

## Phase A: Correctness — IN PROGRESS

**Dev cycle:** Docker is the default test surface — it's what actually gets deployed, so it's
what the 1-5 checklist below is scored against. Local bare-metal is a debug tool only, never
the pass/fail check.

1. `docker-compose build --no-cache` → `docker-compose up -d` → run through checklist items 1-5.
2. If an item fails: drop to `./bin/python -m flask run` locally (single-threaded dev server,
   real tracebacks — see `Readme.md` Debugging section) to find and fix the bug.
3. Rebuild and re-verify the same item in Docker before checking it off. Never check off an
   item on the strength of a local-only pass.

1. [X] Single-bitrate baseline — `master.m3u8` on one file, confirm playback.
2. [X] `/abr/` Tier 2, warm cache — renditions AND HLS cache (manifest + `.ts`) already exist.
   Confirm the CSMIL redirect and playback work.
3. [X] `/abr/` Tier 2, cold HLS cache — renditions exist, but manifest/`.ts` deleted. Confirm
   Bento4 (`mp42hls`) regenerates correctly. Also: throttle the browser and confirm ABR
   actually switches bitrate, and that each rendition serves the correct file.
4. [ ] Renditions deleted entirely — hit `/abr/`, confirm `EncodingManager`/background
   encoding produces new renditions from scratch.
5. [ ] Emergency encoding (Tier 3) — hit `/abr/` with no cache and no renditions while
   encoding is still in flight, confirm the JIT low-quality stream serves instead of a
   stall/404. Informally time this as an early gut-check against an SLA (e.g. compare to
   Google Drive-class latency) — no committed number yet.

**Exit criteria:** all 5 reliably pass, locally and in Docker.

## Phase B: Deployability

Get the already-correct system reachable at a public URL on AWS.

**Decision (made, not yet executed):** container-centric — docker-compose on a single EC2
host, matching the README's documented "Simple Docker install" path (`docker-compose.yml` +
nginx sidecar already exist). Rejected: bare VM + gunicorn + systemd, to avoid maintaining
two equally-supported deploy paths.

Scope: scp files into the CasterPak cache volume, EC2 sizing/security groups, volume design
for segment cache + source video library, DNS/TLS in front via nginx.
Explicitly NOT in scope here: upload API, S3 source backend (Phase C/D).

## Phase C: Upload API

`POST /api/upload` (per `CLAUDE.md` Priority 3) — accept a video, return a playable URL.
Build and test against the Phase B deployment target, not locally-only, so upload semantics
and deployment aren't being solved at the same time.

## Phase D: S3-backed source library + stream-during-upload

Most speculative phase: S3 as a source backend, and streaming before an upload finishes
(partial-file reads mid-upload). Attempt only after Phase C is solid.

## Beyond MVP

See `Todo.md` for deferred feature ideas and risks (Z-mixing automation, additional input
methods, segment-level lazy-loading/priority-queue refinements to the emergency-transcode
path, DDoS/rate-limiting hardening, etc.).
