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

Casterpak a very good fit for use cases where videos serve the 'popular' model of access.  Videos that are frequently accessed remain cached at this server and videos that are not accessed are deleted from cache.

** New in version 0.9 **  Encoding of video renditions and JUST IN TIME encoding!   There is a new endpoint '/i/abr' that will do transcoding of renditions for you based on a configured Adaptive Bitrate Ladder.  Additionally, if CasterPak finds it has no encoding, it can create a stream in just a few seconds to deliver to your website while it does the encoding in the background.

Bottom line: If you haven't encoded your videos for Adaptive Bitrate streaming yet, this package can do that for you too, on your own CPU and storage.

** Caching **: You don't want to store your HLS streams forever, neither do you want to re-create a stream package for every request.  
This software provides the utilities to configure how long to store original video files locally (video input cache ttl), files ready for streaming (streaming cache ttl), and creates stream packages on-demand from your encoded renditions if the files don't exist in the cache.

This package is a good drop-in replacement for Akamai Media Services On Demand (MSOD) for video streaming.  It supports the '.csmil' endpoint that Akamai used to support to generate master manifests of renditions, and creates media playlists and segments your renditions.


## Basic Usage
The flagship feature is the client-side SMIL urls (.csmil) to get the master manifest.

A "Master Manifest" is a file that describes the quality of a stream (resolution, bandwidth, etc) and a URL to a stream that provides that video in the matching resolution.

It uses a similar syntax as Akamai's Media Services On Demand 'csmil' url construction:

```
http://example.com/i/path/<common_filename_prefix>,< bitrate >,< bitrate >,< bitrate >,< bitrate >,<common_filename_suffix>.csmil/master.m3u8
```

For example, if you have a master video with three stream qualities: "high", "medium" and "low" saved as 3 files named 'my_video_highdef.mp4', 'my_video_medium.mp4', and 'my_video_low.mp4' a very basic Master Manifest URL and contents would look like this:

http://example.com/i/my_video_,highdef,medium,low,.mp4.csmil/master.m3u8


    #EXTM3U
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=622044,RESOLUTION=854x480
    http://example.com/i/my_video_low.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=741318,RESOLUTION=960x540
    http://example.com/i/my_video_medium.mp4/index_0_av.m3u8
    #EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1156684,RESOLUTION=1280x720
    http://example.com/i/my_video_highdef.mp4/index_0_av.m3u8

Each one of those url's above will also be served by this application.  Each URL contains the definition of the video stream for that video resolution, saved at that file location.  We call these files 'media manifests' or 'segment manifests' This application will serve segment manifests and the actual segment data.

The caching server will determine if the m3u8 segment manifest is available on-disk, or needs to be created before being served.

For example, http://this_application/i/my_video_highdef.mp4/index_0_av.m3u8 will reply with

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

Each one of those .ts video segments will be available at this application's endpoint until they are removed by the cache cleanup.


### CACHING RECIPES & Tuning

The easiest is no cache.  Start here.  Install this (or run the container) _on the same system_ that has your video files.  No network or high latency between your video files and this software.  It's not the best pattern, but it's a good way to understand what's happening.

configure "cache_input = False" in config.ini.  Container installs have a setup script that ask `Cache/copy input video files from library?` answer 'n' in this scenario.

And start streaming from the URL that CasterPak will serve.

The better model is to host this software on it's own server and mount your video library over the network.  Turn cache_input on and use the input_cache. Casterpak will copy your big video files onto it's local filesystem for encoding and stream packaging.

In the future, we will support directly configuring HTTP, SFTP, S3, and other remote file access so network mounts are not necessary inside containers. (see config.ini), but for now, you must mount the filesystem and map it to the container.

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
step, and it's the cheap one.
 
### Segments
 
```
http://example.com/i/<path>/my_video_720p.mp4/segment1_0_av.ts
```
 
The video data itself.  Again, the player asks for these, not you.  If a segment is requested
and the stream hasn't been packaged yet, CasterPak packages it on the spot rather than 404ing.
 
Delivery of these is controlled by `[output] behind_nginx`.  With nginx in front, Flask returns
an empty body and an `X-Accel-Redirect` header, and nginx serves the file directly off disk -
much more efficient, and the reason the container ships with an nginx sidecar.  Without nginx,
Flask serves the bytes itself.  Playback works either way.
 
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
  Filenames** above.  Most often this is a space or a comma in a filename.
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

# Simple Docker install:

after cloning this repository:

`./setup`

`docker compose up -d --build`

Stop the server with:

`docker compose down`

And get a clean build with:
`docker compose down --rmi all --volumes --remove-orphans`

Things should work right out of the box.

open VNC or a browser capable of native HLS streaming, and hit the url where your video is:

http://localhost/i/abr/VIDEOFILENAME.mp4/master.m3u8

or better yet, the bench test that is part of this build:
http://localhost/testing/test_player.html   ( security people don't like this - firewall it off from the dmz )


## TODO - make the bench test url optional when building the nginx container.

### 3. Check the logs

`docker logs -f casterpak_server`

There is also a 'watcher' script './watch-casterpak.sh' you may run at your own risk.  It will open up a bunch of terminal windows to watch the logs, the cache filesystem, the database, and a cli into the container for your own debugging.


# Development Installs 

For dev installs, it's best to get things working without a container, then do a 'docker compose' to make sure containers still build.

as a developer, you are responsible for running the flask app 'casterpak' and the cache cleanup process separately helps debug stuff.

### configuration
for development, the 'config.ini' is your best place, but for containerised production installs, use env vars. The setup script will help setup the bare minimum config in .env for you.   
Config values in the environment take presidence over config.ini values. Think of config.ini as 'hard coded' defaults, and .env as production configurations if you are a developer.


### Install System Dependencies:


#### Bento4 https://www.bento4.com/

Bento4 binary install is required.  Specifically the `mp42hls` and `mp4info` commands and possibly more.
best to look at 'docker-compose' and manually follow the instructions there.

#### Sqllite3
   kind of standard quick-and-dirty low fingerprint SQL server to maintain cache state. Go google it or just use 'apt' or 'yum' to install it.  

`apt-get update && apt-get install -y sqlite3`

    
### Development Installation of casterpak

Once your dependencies are met...

1.  install a python virtual environment for it:

   `python3 -m venv .`

sometimes you gotta force pip - `python -m pip install --upgrade pip`

3. install python dependencies

   `./bin/pip install -r requirements.txt`

4. configure this application
   
   `cp config_example.ini config.ini`

   `vi config.ini`

This config file is ONLY for development.  It will not be copied into the container 
when building a container, config_example.ini contains defaults, and .env contains user overrides.

You must configure:
  a servername (localhost:5000 by default)
  videoParentPath for where to find your full-lenght videos (/mnt/data/videos default)
  path to the bento4 binaries
  and if you're reading this, you probably want Debug = True
   

5. run the flask application (development and testing only)
   ```
   export CASTERPAK_FILESYSTEM_VIDEOPARENTPATH=/path/to/videos
   ./bin/python -m flask run
   ```

Now, you can test flask is working by hitting port 5000
Depending on how you configured your  'videoParentPath' - construct your url.

By default, it will look in /mnt/data:
videoParentPath = /mnt/data

and a file /mnt/data/test.mp4 will have the url:

http://localhost:5000/i/test.mp4/index.m3u8

A browser may only download the .m3u8 file, but using VLC or any media player will show the video.
Congrats!  you're now developing.

### Scaling with gunicorn 

What this is doing is taking that single flask thread and creating workers so we can serve multiple requests.

6. configure gunicorn

   `vi gunicorn.conf.py`


7. run the application (production)

   `./bin/gunicorn`

It's up to the user to setup a web proxy with nginx or any other webserver. 
See documentation here https://flask.palletsprojects.com/en/2.1.x/deploying/uwsgi/




### Setting up the cache cleanup task

Currently, casterpak will cleanup imported video files from remote sources and generated segment files and media playlists.
By design (currently) casterpak will not cleanup master playlists because they are very small to store.  This might change in the future.
Deleting master playlists is not a problem, as casterpak will re-create them if necessary.

What caching server is complete without deleting old stuff?

Cleanup runs automatically - there's nothing to set up. Gunicorn's master process starts it as a
background thread on a schedule (see `[cache] cleanup_interval` in config.ini, 5 minutes by
default) as soon as the container starts. Its logs go to stdout, the same stream as everything
else - see "Check the logs" above.

### Running cleanup manually

For a one-off pass, or to debug it if it's misbehaving, you can also run it by hand. It has to be
run **from the repo root**, as a module, not as a script - `cleanup/cleaner.py` imports top-level
modules like `config` and `cachedb` the same flat way every other file in this project does, and
that only resolves when the repo root itself is on `sys.path`. `-m` puts your current directory
there; running the file directly by its path does not.

Locally, from the repo root:

```
./bin/python -m cleanup.cleaner
```

In a running Docker container (its working directory is already the repo root):

```
docker exec -it casterpak_server python -m cleanup.cleaner
```

Either way this runs one cleanup pass and exits - it does not start the background loop. Log
output always goes to stdout - `docker exec` prints it straight to your terminal, and a local run
just prints it directly.


## Testing

Hopefully, a lot of this will be automated soon, but here is the basic testing path.
Before a commit to main:

first, do a developent install - see above.

you can run all unit tests by simply typing `./bin/pytest`

then do integration testing with containers:
`./bin/pytest tests/containertests/run_tests.py -vv`

1. execute `run.sh` at the root of the repository with your testing setup.  
    Make sure videos are served (use VLC "media->open network stream" and hit a master.m3u8 url)

    **Note:** `.ts` segment delivery has two modes, controlled by `[output] behind_nginx`
    in `config.ini`. When `True` (set via `CASTERPAK_OUTPUT_BEHIND_NGINX` in
    `docker-compose.yml`), Flask hands nginx an internal path via `X-Accel-Redirect` and
    nginx serves the file directly off disk (see `nginx/conf.d/default.conf`, location
    `/protected_media/`) - efficient, but only works with nginx actually in front. When
    `False` (the local default, since `run.sh`/`flask run` has no nginx in front), Flask
    serves the segment file itself - works anywhere, just less efficient. Either way,
    playback should work; only the delivery mechanism differs.

2. execute `docker compose build --no-cache` to make sure the containers build.
3. execute `docker compose up -d` to run the server

- make sure videos are served.


note that there is a hard coded root path for url's called "i" so all testing must be to http://127.0.0.1/i/path/to/the/files
This 'feature' may go away in the future.

Place an mp4 file directly under "videoParentPath" or in any subdirectory below "videoParentPath"
  example videoParentPath: /mnt/media/files/
  example mp4 file: /mnt/media/files/videos/video.mp4

Request the CasterPak "childManifestFilename" endpoint:
  curl http://127.0.0.1/i/videos/video.mp4/index_0_av.m3u8

you should get a result that looks like an m3u8 manifest
you should see a new directory and files created in  'segmentParentPath'

you can also point VLC or any other video player that can open a network path to http://127.0.0.1/i/videos/video.mp4/index_0_av.m3u8 and make sure the video plays.

### Testing Cache Cleanup.

the entire cache can be invalidated with a single SQL query:
 `sqlite3 /var/lib/casterpak/data/cacheDB.db "UPDATE segmentfile SET timestamp = 0; UPDATE inputfile SET timestamp = 0;"`

setting everything to a timestamp of last access, Jan 1, 1970.   Cleanup should wake up every 300 seconds by default, and wipe the cache.



## Debugging

turn debug logs on in config.ini
```
[application]
debug = True
```

Note that these are techniques to begin learning from.  Use these hints to develop your own strategies on how to debug the app.

diagnosis of the flask application itself is easy enough.  configure to listen on localhost and run the app: 

`./bin/python -m flask run` 

then, use curl to create some requests.

Assuming your video path is configured to point to a directory that directly contains video files:

1. `curl -i http://localhost:5000/i/video.mp4`

You should see a debug log "DEBUG in casterpak: caught 404 for test.mp4"   
  - direct access to mp4 files without streaming is handled, but not supported

2 `http://localhost:5000/i/video.mp4/master.m3u8`
  
  The simplest of calls.
  This does some work, calling that one file and creating a single-bitrate stream.
  the log should show: 
  INFO in _internal: 127.0.0.1 - - [03/Feb/2026 13:33:23] "GET /i/JonBike.MP4/master.m3u8 HTTP/1.1" 200 -

Taking that same url and opening it up in VLC as a "Network Stream" should now play that file as an HLS stream.


gunicorn and thread issues are a bit harder.  Included is a sample gunicorn config `gunicorn-debug.conf.py` that launches the flask application in a single thread you can debug.

`sudo ./venv/bin/python3 -m gunicorn -b :5000 --config gunicorn-debug.conf.py`

Please configure the debug configuration to your needs.

### Cache debugging
This is best to do with a container.

Run casterpak container:


`docker exec -it casterpak_server /bin/bash`

you can watch the actual cache of segment files.  If you configured to write your segments to /tmp/segments, run this command:

     `watch tree -L 2 /tmp/segments`

And leave it open - as requests happen, you'll see the files fill up.

2. you can watch the cache database - this tells what files were created when.

    `watch date +%s && cat cacheDB.json`

3. you can watch the log (turn on debug in config.ini for best results):

    `tail -f /var/log/casterpak.log`

and it's always nice to do some requests to fill up the cache.

    curl http://localhost:5000/i/video.mp4/index_0_av.m3u8

## License

Licensed under GPLv2 — see [LICENSE](LICENSE).



