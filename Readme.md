# CasterPak

```bash
curl -sL https://raw.githubusercontent.com/flipmcf/casterpak/master/install | bash
```

The best way to approach this software is with a filesystem containing pre-encoded Adaptive Bitrate renditions that can be mounted over slow NFS or SSHFS.
This software creates a web server and predictable URLs based on YOUR library.

Let's say, your video archive has this already:
```
my_video.mp4.transcodes
  my_video_360p.mp4
  my_video_480p.mp4
  my_video_720p.mp4
  my_video_hidef.mp4
```
mount that into casterpak and hit this url for an HLS stream:

``` http://example.com/i/my_video.mp4.transcodes/my_video_,360p,480p,720p,hidef,.mp4.csmil/master.m3u8 ```

No migration needed.  It just works.  Read on for the details if this didn't immediately catch your attention.


## The CAching STrEam [R] PAcKager:

This software provides HLS Stream packaging for Video-On-Demand (VOD) with a built in cache.

The problem this solves is to balance your CPU and Storage costs for streaming Video-on-demand.
Creating an HLS (m3u8) stream from a video file (mp4, et. al.) is CPU cheap and fast compared to video encoding.

This is designed to be a migrationless "Just connect to your existing video library" solution for streaming video-on-demand.  Rather than pay someone to store, encode and deliver your videos, you can drop this into your stack yourself.

This was originally designed to only create HLS streams, but has grown to become both a rendition encoder and JIT encoder to make your videos play on any website.  You don't need to provide encoded renditions; encoding can happen on your server and this software will happily peg 16 CPU cores to serve an anonymous web request.  Tune your cache, save your renditions, learn the software. Watch your costs.  You have been warned.

It's a great fit for those who own a large 'archive' video file on inexpensive, slow-access storage like AWS S3 Glacier or Microsoft Azure Archive.  
CasterPak can retrieve source video files from network addresses, copy them locally, and then deliver.

Casterpak is a very good fit for use cases where videos serve the 'popular' model of access.  Videos that are frequently accessed remain cached at this server and videos that are not accessed are deleted from cache.

Bottom line: If you haven't encoded your videos for Adaptive Bitrate streaming yet, this package can do that for you too, on your own CPU and storage.  See [The ABR endpoint](#the-abr-endpoint---the-one-that-encodes-for-you).

This package is a good drop-in replacement for Akamai Media Services On Demand (MSOD) for video streaming.  It supports the '.csmil' endpoint that Akamai used to support to generate master manifests of renditions, and creates media playlists and segments from your renditions.


## Caching recipes & tuning

You don't want to store your HLS streams forever, neither do you want to re-create a stream package for every request.
This software lets you configure how long to keep original video files locally (`input_file_age`) and files ready for streaming (`segment_file_age`), both in minutes under `[cache]` in `config_example.ini`, and it creates stream packages on-demand from your encoded renditions if the files don't exist in the cache.

By design, master playlists are never cleaned up because they are very small to store.  Deleting them is not a problem, as casterpak will re-create them if necessary.

The easiest is no cache.  Start here.  Install this (or run the container) _on the same system_ that has your video files.  No network or high latency between your video files and this software.  It's not the best pattern, but it's a good way to understand what's happening.

Configure "cache_input = False" (the `[filesystem]` section of config.ini).  Container installs have a setup script that asks `Cache/copy input video files from library?` answer 'n' in this scenario.

And start streaming from the URL that CasterPak will serve.

The better model is to host this software on it's own server and mount your video library over the network.  Turn cache_input on and use the input_cache. Casterpak will copy your big video files onto it's local filesystem for encoding and stream packaging.

In the future, we will support directly configuring HTTP, SFTP, S3, and other remote file access so network mounts are not necessary inside containers. (see config_example.ini), but for now, you must mount the filesystem and map it to the container.

----

## URL Endpoints for streaming.
Every streaming URL lives under the hard-coded root path `/i/`.  There are really only two
endpoints you need to care about as a user: the `.csmil` endpoint, which is the one you should
be pointing your website at, and the `/i/abr/` endpoint, which is the one that does the work
for you if you haven't encoded anything yet.  The rest of the endpoints exist because a video
player asks for them - you generally don't type them by hand.
 
### The CSMIL endpoint - use this one.
 
```
http://example.com/i/<path>/<prefix>,<bitrate>,<bitrate>,<bitrate>,<suffix>.csmil/master.m3u8
```
 
This is the flagship.  Point your public website here.
 
This endpoint assumes you have already encoded your Adaptive Bitrate renditions and they are
sitting in your library.  It does no encoding, ever.  It reads your rendition files, packages
them into HLS (which is CPU cheap and fast), caches the result, and serves it.  That's the
whole deal: your CPU does almost nothing, your storage does the work, and your costs stay
predictable.
 
Given a library that looks like this:
 
```
my_video.mp4.transcodes
  my_video_360p.mp4
  my_video_480p.mp4
  my_video_720p.mp4
```
 
the URL is:
 
```
http://example.com/i/my_video.mp4.transcodes/my_video_,360p,480p,720p,.mp4.csmil/master.m3u8
```
 
Read that comma-separated list as "everything before the comma group is the filename prefix,
everything after is the suffix, and each item in between is one rendition."  This is the same
URL grammar Akamai MSOD used, which is deliberate - if you're migrating off Akamai, your
existing URLs mostly just work.
 
If the renditions aren't there, you get a 404.  This endpoint will not go encode them for you.
That's the point.

**What you get back.** The master manifest is a file that describes each quality of a stream
(resolution, bandwidth, etc) and the URL of the stream that provides it.  For a flat library
with three files, `my_video_highdef.mp4`, `my_video_medium.mp4` and `my_video_low.mp4`, the URL
`http://example.com/i/my_video_,highdef,medium,low,.mp4.csmil/master.m3u8` returns:

    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    http://example.com/i/my_video_low.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    http://example.com/i/my_video_medium.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    http://example.com/i/my_video_highdef.mp4/index_0_av.m3u8

Each of those URLs is also served by this application: it is the definition of the video stream
for that resolution, which we call a 'media manifest' or 'segment manifest'.  See below.
 
### The ABR endpoint - the one that encodes for you.
 
```
http://example.com/i/abr/<path>/my_video.mp4/master.m3u8
```
 
Use this when you have a source video and no renditions yet.  It's a state manager, and it
does one of three things depending on what it finds on disk:
 
**Renditions already exist** - it issues a `302` redirect straight to the `.csmil` URL above
and gets out of the way.  Nothing is encoded.  This is the happy path, and it's why the
`.csmil` endpoint is the one that actually serves your traffic.
 
**No renditions, nothing in progress** - it queues a full background ABR encode of your
configured bitrate ladder, and then, so your viewer isn't staring at a spinner for ten
minutes, it fires off a fast, low-quality JIT (Just In Time) encode and hands back a
single-rendition master manifest pointing at that.  Your viewer starts watching in a few
seconds.  The good renditions keep building in the background.
 
**Encode already in progress** - it returns that same JIT stream.  It will not queue a second
encode of the same file.
 
The JIT stream is a stopgap, not a product.  It's one rendition, it is not adaptive, and it is
advertised at a fixed `BANDWIDTH=1000000, RESOLUTION=854x480` regardless of what your source
actually is.  It exists so the first viewer of an un-encoded video gets pixels instead of a
404.  Once the real renditions land, subsequent requests to `/i/abr/` redirect to `.csmil` and
the JIT stream stops being used.
 
**Where the encodings go, and what you should do about it.**
 
Renditions produced by `/i/abr/` are written to your *cache* (`videoCachePath`), not to your
library.  The cache is a cache - it has a TTL and a size limit, and the cleanup task will
eventually delete things out of it.  If you let `/i/abr/` be your production endpoint, you are
signing up to re-encode the same videos forever, every time the cache evicts them, on your own
CPU, triggered by anonymous web requests.  Do not do this.
 
The intended workflow is:
 
1. Hit `/i/abr/your_video.mp4/master.m3u8` once.  Let it encode.
2. Find the renditions in your cache directory.
3. **Copy them back into your video library**, alongside your source file, in the
   `your_video.mp4.transcodes/` layout shown above.
4. Point your public website at the `.csmil` URL from now on.

`/i/abr/` is a tool for producing renditions and for surviving the case where a video hasn't
been encoded yet.  `.csmil` is what you ship.
 
### Single-bitrate master manifest
 
```
http://example.com/i/<path>/my_video.mp4/master.m3u8
```
 
Takes one video file and gives you a master manifest with exactly one rendition in it - the
source file itself, no bitrate suffix, no ladder, no adaptation.  Under the hood it's just a
CSMIL with a single unlabeled rendition.
 
Useful for testing, for a quick look at whether a file packages at all, and for the case where
you genuinely only have one quality and don't care about adaptive delivery.  It is not
adaptive bitrate streaming, so don't put it on a page where viewers have varying bandwidth and
then wonder why it buffers.
 
### Media (child) manifest
 
```
http://example.com/i/<path>/my_video_720p.mp4/index_0_av.m3u8
```
 
This is the per-rendition playlist - the list of `.ts` segments for one specific quality.  You
don't request this yourself; every master manifest above contains URLs pointing here, and the
player follows them.
 
If the segments don't exist yet, requesting this creates them.  That's the actual packaging
step, and it's the cheap one.  The caching server decides whether the playlist is already on
disk or has to be created before it is served.

For example, `http://this_application/i/my_video_highdef.mp4/index_0_av.m3u8` replies with

    #EXTM3U
    #EXT-X-TARGETDURATION:2
    #EXT-X-ALLOW-CACHE:YES
    #EXT-X-PLAYLIST-TYPE:VOD
    #EXT-X-VERSION:3
    #EXT-X-MEDIA-SEQUENCE:1
    #EXTINF:2.000,
    http://this_application/i/my_video_highdef.mp4/segment1_0_av.ts
    #EXTINF:2.000,
    http://this_application/i/my_video_highdef.mp4/segment2_0_av.ts
    #EXTINF:2.000,
    http://this_application/i/my_video_highdef.mp4/segment3_0_av.ts
    #EXTINF:2.000,
    ...
    #EXTINF:1.186,
    http://this_application/i/my_video_highdef.mp4/segment19_0_av.ts
    #EXT-X-ENDLIST
 
### Segments
 
```
http://example.com/i/<path>/my_video_720p.mp4/segment1_0_av.ts
```
 
The video data itself.  Again, the player asks for these, not you.  If a segment is requested
and the stream hasn't been packaged yet, CasterPak packages it on the spot rather than 404ing.
Segments stay available at this endpoint until the cache cleanup removes them.
 
Delivery of these is controlled by `[output] behind_nginx`.  With nginx in front, Flask returns
an empty body and an `X-Accel-Redirect` header, and nginx serves the file directly off disk
(see `nginx/conf.d/default.conf`, location `/protected_media/`) - much more efficient, and the
reason the container ships with an nginx sidecar.  Without nginx, Flask serves the bytes itself.
Playback works either way.
 
### Endpoints that deliberately do nothing
 
```
http://example.com/i/<path>/my_video.mp4
```
 
A direct request for the video file, with no stream path after it, always returns `404`.
CasterPak is a stream packager, not a file server.  If you want to hand people the raw MP4,
use a normal web server.
 
`/d/...` (DASH) and `/c/...` (CMAF) are registered but not implemented.  They're placeholders
for a future where this does more than HLS.
 
### Response codes you'll actually see
 
- `302` - you hit `/i/abr/` and renditions exist; follow the redirect to the `.csmil` URL.
- `404` - source video or renditions not found where CasterPak expected them.  Check
  `videoParentPath` and check your filename.
- `422` - the filename or directory in your URL didn't pass validation.  See **Valid
  Filenames** below.  Most often this is a space or a comma in a filename.
- `500` - packaging failed.  Check the logs; usually Bento4 refusing the source file.
- `504` - encoding failed or timed out on the `/i/abr/` path.

 

## Valid Filenames

Every filename and directory segment that reaches CasterPak from a URL is **validated, never mutated**. A name that doesn't meet the rules below is rejected outright (HTTP 422) - it is never silently rewritten into something else.

Allowed characters, in filenames and in each `/`-separated directory segment:

- Letters and digits (`A-Z`, `a-z`, `0-9`)
- Hyphen `-` (but not as the first character - see below)
- Underscore `_`
- Plus `+`
- Period `.` - freely, for the base filename and the extension. Multiple periods are allowed (`my.video.final.mp4` is fine); a segment that is *exactly* `.` or `..` is not, since those are directory-traversal tokens, not filenames.

Rejected outright, regardless of character set:

- A segment starting with `-` 
- A literal comma `,` anywhere in a name (reserved as the CSMIL rendition-list delimiter - see `vodhls/csmil.py`)
- An empty segment (produced by a leading, trailing, or doubled `/` in the path)

**Spaces are not a valid filename character and are not converted to anything.** If your source library or upload tooling produces filenames with spaces, convert spaces to underscores *before* the file reaches CasterPak.

----

## Running with Docker

CasterPak runs as two containers, the app and an nginx proxy.  There are two ways to start them:

- **The installer** (the `curl` command at the top) is the easiest.  It downloads
  `docker-compose.yml` and the setup script, asks a few questions, pulls the published images and
  starts them.
- **From a clone** is for when you want to build or change the code yourself:

  ```
  ./setup
  docker compose up -d --build
  ```

Either way, you need a cache directory on the host that your user can read and write (the setup
script asks where).  See `docs/Hosting-instructions` for the volume layout, and
`docs/deploying_casterpak.md` for notes on building a server on AWS.

Stop the server with:

`docker compose down`

And get a clean build with:

`docker compose down --rmi all --volumes --remove-orphans`

### Smoke test

Put an mp4 file directly under your video directory, or in any subdirectory below it.  If the
directory is `/mnt/media/files/` and the file is `/mnt/media/files/videos/video.mp4`, the URL path
is `/videos/video.mp4`.  Then request the ABR endpoint:

```
curl -i http://localhost/i/abr/videos/video.mp4/master.m3u8
```

The first call returns the JIT stream's manifest; once encoding finishes it returns a `302` to the
`.csmil` URL.  Open the same URL in VLC (Media, Open Network Stream) or a browser capable of native
HLS streaming and make sure the video plays.  You should also see new directories and files appear
under the `segments` directory of your cache.

Or use the bench test that is part of this build:
http://localhost/testing/test_player.html   ( security people don't like this - firewall it off from the dmz )

### Check the logs

`docker logs -f casterpak_server`

There is also a 'watcher' script './watch-casterpak.sh' you may run at your own risk.  It will open up a bunch of terminal windows to watch the logs, the cache filesystem, the database, and a cli into the container for your own debugging.

Cache cleanup needs no setup: it runs automatically as a background task of the app's gunicorn
process (see `[cache] cleanup_interval` in `config_example.ini`, 5 minutes by default), and its logs
go to the same place as everything else.


## Development and contributing

Want to hack on CasterPak?  Contributions are welcome, including first-time ones.

- [CONTRIBUTING.md](CONTRIBUTING.md) - how to submit a change
- [docs/development.md](docs/development.md) - dev install, running the tests, debugging
- [CLAUDE.md](CLAUDE.md) - architecture: request flows, storage layout, code map
- [ROADMAP.md](ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md) - where it's going, where it's been

## License

Licensed under GPLv2 — see [LICENSE](LICENSE).
