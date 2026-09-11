# CasterPak Roadmap

**MVP target:** end of Phase D — "something I can demo and show value."
Post-MVP feature ideas and risks live in `Todo.md` and are intentionally out of scope until
Phase D is done.

## Phase A: Correctness — SIGNED OFF (2026-09-08)

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
4. [X] Renditions deleted entirely — hit `/abr/`, confirm `EncodingManager`/background
   encoding produces new renditions from scratch.
5. [X] Emergency encoding (Tier 3) — hit `/abr/` with no cache and no renditions while
   encoding is still in flight, confirm the JIT low-quality stream serves instead of a
   stall/404. Informally time this as an early gut-check against an SLA (e.g. compare to
   Google Drive-class latency) — no committed number yet.


**Exit criteria:** all 5 reliably pass, locally and in Docker.

V 0.8.1-alpha.

## Phase B: Deployability

Get the already-correct system reachable at a public URL on AWS.

ABR race condition - test_route_abr_manifest_concurrent_requests_dont_race - needs solving
  - CHECKED - this is solved.  V 0.8.2-alpha.

**Decision (made, not yet executed):** container-centric — docker-compose on a single EC2
host, matching the README's documented "Simple Docker install" path (`docker-compose.yml` +
nginx sidecar already exist). Rejected: bare VM + gunicorn + systemd, to avoid maintaining
two equally-supported deploy paths.

    Deployed.  casterpak.com   

Scope: 
  scp files into the CasterPak cache volume - DONE
  EC2 sizing/security groups - DONE
  volume design for segment cache + source video library - DO.
  DNS - DONE  casterpak.com
     But I want to separate the video from the website, so I will create 'video.casterpak.com to point to nginx
  TLS in front via nginx - TODO - letsencrypt
  
   IN PROGRESS..



Explicitly NOT in scope here: upload API, S3 source backend (Phase C/D).

Then - publish 0.9.0-alpha to dockerhub, and create a deployment that is simple, like hosting the install script on openforgesolutions.com

`install`/`setup` need fixing before that publish is actually usable (found while checking whether they were up to date):
- Both still use the old `docker-compose` (hyphenated) syntax — `docker compose` works better here, already fixed everywhere else this applies.
- `install` does `docker-compose pull` — that only works once 0.9.0-alpha images are actually published to Docker Hub, not just tagged in docker-compose.yml.
- `setup`'s wizard writes `CASTERPAK_INPUT_INPUT_TYPE` and `CASTERPAK_FILESYSTEM_CACHE_INPUT` to `.env`, but docker-compose.yml's `environment:` list never references either — both questions are currently asked, answered, and then silently ignored.
- `setup` also writes `APP_PORT` to `.env`, but the only line that would use it (the `ports:` mapping) is commented out in docker-compose.yml — dead as well.

Reproduce a bug from /abr/ where first-hit serves a JIT stream, encoding happens, segments are created, and then the docker container is brought down (maybe ./setup is run again) and then brought back up and the cache is preserved.   The senario is to intentionally misconfigure the server with ./setup and place a bad hostname in "Server Name for manifests"  - the CASTERPAK_OUTPUT_SERVERNAME env variable.  This generates bad m3u8 master manifests and index_0 files can't be found because servername is wrong.  bring down container, reconfigure to have correct name, and bring back up container.  hit the same /abr/ url - NOTE THAT JIT STREAM IS RETURNED - cache should have been preserved.  I checked the cache, and the old m3u8 was still there with the bad hostname. 


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
