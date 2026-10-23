# Development guide

CasterPak is deployed as containers (see the [README](../Readme.md)). A local virtual environment is
for running the unit tests and for debugging with a single-threaded server, where tracebacks are
easy to read.

Related reading: [CONTRIBUTING.md](../CONTRIBUTING.md) for how to submit a change, and
[CLAUDE.md](../CLAUDE.md) for the architecture (request flows, storage layout, code map).

## Development install

You need Python 3.10 or newer (the Docker image uses 3.10).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp config_example.ini config.ini
```

`.venv/bin/python -m pip install --upgrade pip` 
`.venv/bin/pip install -r requirements-dev.txt`

`.venv/bin/pytest` is enough to run the unit tests: they need neither Docker nor the Bento4 binaries.
To actually serve video from a dev install you also need the Bento4 binaries (`mp42hls`, `mp4info`
and friends) and FFmpeg. The exact versions and install steps are in the `Dockerfile`. The
`sqlite3` command-line tool is optional and only useful for poking at the cache database.

### Configuration

`config.ini` is for development only; it is never baked into the container image. Edit at least:

- `[output] serverName` (`localhost:5000` by default)
- `[filesystem] videoParentPath`, where your full-length videos live (`/mnt/data/videos` by default)
- `[bento4] binaryPath`, the directory holding the Bento4 binaries
- `[application] debug = True`, which you almost certainly want while developing

Any key can be overridden by an environment variable named `CASTERPAK_<SECTION>_<KEY>` (for example
`CASTERPAK_FILESYSTEM_VIDEOPARENTPATH`). Environment variables win over `config.ini`. Containers are
configured entirely this way, through the `.env` file that `./setup` writes and
`docker-compose.yml`.

### Run the Flask development server

```bash
export CASTERPAK_FILESYSTEM_VIDEOPARENTPATH=/path/to/videos
./bin/python -m flask run
```

This serves on port 5000. With `/path/to/videos/test.mp4` in place:

```bash
curl -i http://localhost:5000/i/test.mp4/master.m3u8
```

returns a single-bitrate master manifest. A browser may just download the `.m3u8`; open the URL
in VLC (Media, Open Network Stream) to watch it. Follow the URLs inside the manifest with curl to
see the media playlist and segments.

Everything is under the hard-coded `/i/` root. There is no endpoint at `/i/test.mp4` itself (it
always returns 404 by design). See the endpoint reference in the README for the rest.

Cache cleanup and the encoding dispatcher are started by gunicorn's master process, so they do not
run under `flask run`. Run cleanup by hand when you need it (below).

## Cache cleanup

In the container, cleanup runs automatically: gunicorn's master process starts it as a background
thread every `[cache] cleanup_interval` seconds (300 by default). Its logs go to stdout with
everything else.

To run one pass by hand, run it **from the repo root, as a module**. `cleanup/cleaner.py` imports
top-level modules such as `config` and `cachedb` the same flat way every other file here does, and
that only resolves when the repo root is on `sys.path`. `-m` puts your current directory there;
running the file by its path does not.

```bash
.venv/bin/python -m cleanup.cleaner                              # dev install
docker exec -it casterpak_server python -m cleanup.cleaner   # running container
```

Either way it runs one pass and exits; it does not start the background loop.

Cleanup deletes only what the cache database records: imported source videos, media playlists and
segments, by age (`segment_file_age`, `input_file_age`, in minutes) and by cache size. It
deliberately leaves master playlists alone because they are tiny and are re-created on demand.

## Testing

Before you open a pull request:

1. Unit tests (a few seconds, no Docker):

   ```bash
   .venv/bin/pytest
   ```

2. If you touched routes, encoding, caching, nginx, `docker-compose.yml` or the `Dockerfile`, the
   container tests. They build and run the real stack and clear the caches between tests, and they
   refuse to start if a `docker-compose.override.yml` exists:

   ```bash
   .venv/bin/pytest tests/containertests/run_tests.py -vv
   ```

3. If you changed the `Dockerfile`, compose file or dependencies, make sure the images build and
   the stack serves video:

   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

   then follow the smoke test in the README.

`.ts` segment delivery has two modes, set by `[output] behind_nginx`. With nginx in front it is
`True` (set through `CASTERPAK_OUTPUT_BEHIND_NGINX` in `docker-compose.yml`); `flask run` has no
nginx in front, so the local default is `False`. Playback should work either way. The README's
"Segments" section explains the difference.

`tests/Human_Test_instructions.md` is a manual test walkthrough for humans.

### Testing cache cleanup

The whole cache can be expired with one SQL statement against the cache database, which sets every
entry's last-access time to 1970:

```bash
docker exec -it casterpak_server sqlite3 /var/lib/casterpak/data/cacheDB.db \
  "UPDATE segmentfile SET timestamp = 0; UPDATE inputfile SET timestamp = 0;"
```

The next cleanup pass (within `cleanup_interval`, or run it by hand) should wipe the cache.

## Debugging

These are techniques to start from; develop your own as you learn the code.

**Turn on debug logging:** `[application] debug = True` in `config.ini` for a dev install, or
`CASTERPAK_APPLICATION_DEBUG=True` for a container.

**Logs.** Gunicorn owns every log destination and the default is stdout:

```bash
docker logs -f casterpak_server
```

`./watch-casterpak.sh` opens several terminals to watch the logs, the cache, the database and a
shell in the container. Run it at your own risk.

**Flask dev server.** Run it as above and use curl. For example, a direct request for the video
file should log a 404 (direct access is deliberately unsupported):

```bash
curl -i http://localhost:5000/i/video.mp4
curl -i http://localhost:5000/i/video.mp4/master.m3u8
```

The second is the simplest real request: it packages one file as a single-bitrate stream.

**Threads and workers.** To rule gunicorn's concurrency in or out, run a single worker from the
repo root:

```bash
.venv/bin/python -m gunicorn -b :5000 --workers 1 app:app
```

(`gunicorn-debug.conf.py` exists but currently contains only the license header.)

**A debugger inside the container.** `docker-compose.override.yml.example` explains how to drop a
`pdb` breakpoint into the code and attach to the container.

**Watching the caches.** The cache volume is mounted from the host, so you can watch it from the
host. Use the path you gave `./setup` as `HOST_CACHE_PATH` (`/var/cache/casterpak` by default):

```bash
watch tree -L 2 /var/cache/casterpak/segments
```

Make some requests and watch the files appear. To see what the database thinks it holds:

```bash
docker exec -it casterpak_server sqlite3 /var/lib/casterpak/data/cacheDB.db \
  "SELECT filename, timestamp FROM segmentfile ORDER BY timestamp DESC LIMIT 10;"
```
