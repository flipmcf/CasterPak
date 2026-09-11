#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
## Run this with ./bin/pytest path-to-this-file/run_tests.py -vv

import os
import time
import pytest
import docker
import requests
import subprocess
import hashlib
import concurrent.futures

client = docker.from_env()

test_env = os.environ.copy()

# when testing, use video files here as the source.
test_env["CASTERPAK_FILESYSTEM_VIDEOPARENTPATH"] = "/var/lib/casterpak/samples" 

# Define a custom encoding ladder. what the test encoder should build so it doesn't expect 1080p or 240p
test_env["CASTERPAK_ENCODING_LADDER_720"] = "1280x720, 2500k"
test_env["CASTERPAK_ENCODING_LADDER_480"] = "854x480, 1000k"
test_env["CASTERPAK_ENCODING_LADDER_360"] = "640x360, 750k"

# Must match [encoding] poll_interval in config.ini. The ABR encode no longer
# runs inside the request - EncodingManager just writes a queue row and the
# encoding_process_manager dispatcher picks it up on its next poll, up to this
# many seconds later. Tests that look for the ffmpeg process have to allow for
# that gap.
ENCODING_POLL_INTERVAL = 5

# The one test asset every fixture/test in this file should read from. Baked
# into the image at build time (Dockerfile: COPY tests/assets/test-video.mp4
# -> this path), from a file that's actually committed to the repo - so it's
# identical on every machine and in CI, unlike /mnt/data (the docker-compose
# HOST_VIDEO_PATH bind mount), which only has whatever happens to be in
# whoever's running the suite's own local video library.
TEST_VIDEO_PATH = "/var/lib/casterpak/samples/test-video.mp4"

def wait_for_log_signal(container_name, signal_text, timeout=30):
    """
    Streams logs from a container and returns only when signal_text is found.
    """
    container = client.containers.get(container_name)
    start_time = time.time()
    
    # .logs(stream=True) returns a generator that yields log lines as they appear
    for line in container.logs(stream=True, follow=True):
        print(line)
        if signal_text.encode('utf-8') in line:
            return True
        if time.time() - start_time > timeout:
            pytest.fail(f"Timeout: Did not find '{signal_text}' in {container_name} logs.")
    return False


# The Logic: find all files in the directory. 
# If it returns any output, the directory isn't empty.
def assert_dir_empty(container, path):
    # -mindepth 1 ensures we don't count the directory itself
    # -print -quit makes it fast: it stops as soon as it finds one item
    cmd = f"sh -c 'find {path} -mindepth 1 -print -quit'"
    _, out = container.exec_run(cmd)
    assert out.strip() == b"", f"{path} not empty."


def count_matching_processes(container, needle):
    """
    Counts running processes inside the container whose full command line
    contains `needle`. The minimal image has no `ps` binary, so this scans
    /proc directly instead - same technique used to manually diagnose the
    ABR/JIT duplicate-encode races.
    """
    cmd = "sh -c 'for p in /proc/[0-9]*; do tr \"\\0\" \" \" < \"$p/cmdline\" 2>/dev/null; echo; done'"
    _, out = container.exec_run(cmd)
    lines = out.decode(errors="replace").splitlines()
    return sum(1 for line in lines if needle in line)


def fire_concurrent_requests(url, count=8):
    """Fires `count` GET requests at `url` as concurrently as possible."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(requests.get, url) for _ in range(count)]
        return [f.result() for f in futures]



@pytest.fixture(scope="module", autouse=True)
def casterpak_stack():

    print("\n🚀 Building and starting CasterPak...")
    subprocess.run(["docker", "compose", "build", "--no-cache" ], check=True, env=test_env)
    subprocess.run(["docker", "compose", "up", "-d", "--remove-orphans"] , check=True, env=test_env)

    # 1. Wait for Flask Backend (adjust signal to match your actual startup log)
    # Common Gunicorn/Flask signal: "Listening at: http://0.0.0.0:5000"
    print("⏳ Waiting for Flask backend signal...")
    assert wait_for_log_signal("casterpak_server", "[INFO] Listening at: http://0.0.0.0:5000"), "casterpak crashed"


    # 2. Wait for Nginx (adjust signal to match your actual startup log)
    # Common Nginx signal: "start worker process" or "ready for connections"
    print("⏳ Waiting for Nginx proxy signal...")
    assert wait_for_log_signal("casterpak_nginx", "start worker process"), "Nginx crashed" 

    print("✅ Stack is fully initialized and signaling health.")

    container = client.containers.get("casterpak_server")
    exit_code, _ = container.exec_run(f"test -f {TEST_VIDEO_PATH}")

    assert exit_code == 0, f"Critical failure: {TEST_VIDEO_PATH} not found in container."
    print(f"✅ Verified test asset: {TEST_VIDEO_PATH}")
    
    yield 

    print("\n🧹 Tearing down...")
    subprocess.run(["docker", "compose", "down", "-v"], check=True)


## run this to cleanup after each test
@pytest.fixture(scope="function")
def casterpak_clean():

    print("entering casterpak cleanup fixture")
    yield
    print("leaving casterpak cleanup fixture")
    #truncate the database tables
    SEGMENT_FILE_CACHE = 'segmentfile'
    INPUT_FILE_CACHE = 'inputfile'
    # The ABR encode queue. It survives across tests otherwise (casterpak_clean
    # used to wipe files but not this), and a leftover row makes in_progress()
    # true for the next test's video - see encoding/encoding_process_manager.py.
    ENCODING_QUEUE = 'encodingqueue'

    container = client.containers.get("casterpak_server")

    # Kill any ffmpeg still encoding from the test that just ran. casterpak_clean
    # wipes state, not processes, and a background ABR encode outlives the request
    # that started it. The minimal image has no pkill/pidof, so walk /proc (same
    # technique as count_matching_processes). `kill` is a shell builtin. Match on
    # 'preset' - both the ABR and JIT ffmpeg commands pass -preset, and this
    # cleanup script itself does not, so the loop won't kill its own shell.
    container.exec_run(
        "sh -c 'for d in /proc/[0-9]*; do "
        "grep -qa preset \"$d/cmdline\" 2>/dev/null && kill \"${d#/proc/}\"; done'"
    )

    for table in [SEGMENT_FILE_CACHE, INPUT_FILE_CACHE, ENCODING_QUEUE]:
        _, out = container.exec_run(f'sqlite3 /var/lib/casterpak/data/cacheDB.db "DELETE FROM {table}"')


    #remove any files generated
    # Instead of: container.exec_run("rm /path/*.txt") explicity call shell to expand the '*'
    container.exec_run("sh -c 'rm -rf /tmp/segments/* /tmp/video_input/*'")

    assert_dir_empty(container, "/tmp/segments")
    assert_dir_empty(container, "/tmp/video_input")


@pytest.fixture(scope="function")
def with_encodings(casterpak_clean):
    """
    This fixture takes the test video and creates encodings to test MBR manifests
    Since we're not in production, we're going to really cheat and run ffmpeg with speed, not quality
    # -t 5: Only process 5 seconds of the video
    # -preset ultrafast: Skip heavy compression algorithms
    # -r 15: Drop framerate to 15 fps to halve the workload
    # set -g and -keyint_min to 30 to get 30frames/15fps = 2 second keyframes for segmentation.

    NOTE: rendition labels here ('720p'/'480p'/'360p') must match config.ini's
    [encoding_ladder] labels exactly - this fixture writes files by hand, it
    doesn't go through EncodingManager, so nothing enforces that agreement
    for you. The CASTERPAK_ENCODING_LADDER_* env vars set at the top of this
    file do NOT actually reach the container (docker-compose.yml doesn't
    forward them - they're not referenced anywhere in its `environment:`
    section), so the container always runs the real config.ini ladder
    regardless of what's set here. If you change config.ini's ladder labels,
    update RENDITION_LABELS below to match.
    """

    RENDITION_LABELS = ['720p', '480p', '360p']

    container = client.containers.get("casterpak_server")
    test_dir = test_env["CASTERPAK_FILESYSTEM_VIDEOPARENTPATH"]
    encoding_output_dir = f"{test_dir}/test-video.mp4.transcodes"

    check_cmd = f"test -f {encoding_output_dir}/test-video_360p.mp4"
    exit_code, _ = container.exec_run(check_cmd)

    if exit_code == 0:
        print("✨ Transcoded variants already exist. Skipping FFmpeg...")
    else:
        exit_code, _ = container.exec_run(f"mkdir {encoding_output_dir}")

        test_file = TEST_VIDEO_PATH

        #be nice  use half available cpu's
        max_cpu = os.cpu_count() or 4  ## Fallback to 4 if cpu_count() returns None
        max_threads = max(1, int(max_cpu/2))
        threads = f"-threads {max_threads}"
        nice = "nice -n 19"

        #create a few encodings manually using our test asset:
        ffmpeg_cmd = (
            f"{nice} ffmpeg -y {threads} -t 5 -i {test_file} "
            f"-vf scale=-2:720 -c:v libx264 -preset ultrafast -b:v 2500k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_720p.mp4 "
            f"-vf scale=-2:480 -c:v libx264 -preset ultrafast -b:v 1200k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_480p.mp4 "
            f"-vf scale=-2:360 -c:v libx264 -preset ultrafast -b:v 600k  -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_360p.mp4 "
        )

        print("🎬 Transcoding test variants...")
        exit_code, output = container.exec_run(f"sh -c '{ffmpeg_cmd}'")
        assert exit_code == 0, f"FFmpeg failed: {output.decode()}"


@pytest.fixture(scope="function")
def with_abr_cache_encodings(casterpak_clean):
    """
    Like with_encodings, but for EncodingManager's own cache instead of the
    source library. These are NOT the same directory:

    - with_encodings writes into videoParentPath (the source library) -
      that's what the CSMIL route (MultivariantManager -> vodhls_media_
      playlist_factory -> source_file) reads pre-provided renditions from.
    - EncodingManager.renditions_exist(), which is what /abr/ actually
      checks, looks in videoCachePath instead (encoding/encodingmanager.py:
      transcode_output_dir). Different directory entirely, by design - see
      CLAUDE.md: CSMIL is for operator-provided renditions already on disk;
      /abr/ is CasterPak's own auto-encode cache.

    Route tests exercising /abr/'s "renditions already exist" state need
    THIS fixture, not with_encodings, or renditions_exist() will always be
    False regardless of what with_encodings wrote elsewhere.
    """
    RENDITION_LABELS = ['720p', '480p', '360p']

    container = client.containers.get("casterpak_server")
    cache_output_dir = "/tmp/video_input/test-video.mp4.transcodes"

    exit_code, _ = container.exec_run(f"mkdir -p {cache_output_dir}")

    test_file = TEST_VIDEO_PATH

    max_cpu = os.cpu_count() or 4
    max_threads = max(1, int(max_cpu / 2))
    threads = f"-threads {max_threads}"
    nice = "nice -n 19"

    ffmpeg_cmd = (
        f"{nice} ffmpeg -y {threads} -t 5 -i {test_file} "
        f"-vf scale=-2:720 -c:v libx264 -preset ultrafast -b:v 2500k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {cache_output_dir}/test-video_720p.mp4 "
        f"-vf scale=-2:480 -c:v libx264 -preset ultrafast -b:v 1200k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {cache_output_dir}/test-video_480p.mp4 "
        f"-vf scale=-2:360 -c:v libx264 -preset ultrafast -b:v 600k  -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {cache_output_dir}/test-video_360p.mp4 "
    )

    print("🎬 Transcoding ABR-cache test variants...")
    exit_code, output = container.exec_run(f"sh -c '{ffmpeg_cmd}'")
    assert exit_code == 0, f"FFmpeg failed: {output.decode()}"


#nginx tests

def test_nginx_config():
    """
    Verify NginX configuration is sane.
    """
    container = client.containers.get("casterpak_nginx")
    
    
    # Verify configuration of nginx
    inspect_cmd = "nginx -T"
    _, config_output = container.exec_run(inspect_cmd)

    #allgood
    assert b"syntax is ok" in config_output

    #make sure any debugging timeouts are turned off
    assert b"proxy_read_timeout 600s;" not in config_output
    assert b"proxy_connect_timeout 600s;" not in config_output
    assert b"proxy_send_timeout 600s;" not in config_output

def test_nginx_proxy_to_flask():
    """Verify that Nginx successfully proxies to the Flask backend."""
    response = requests.get("http://localhost:80/")

    #there is nothing at the root of nginx or at the root of flask.
    assert response.status_code == 404

    #a failure is a 'cannot connect' or any other response.
    
def test_nginx_static_testing_route():
    """Verify the /testing/ alias is serving the test player."""
    response = requests.get("http://localhost:80/testing/test_player.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]



## Casterpak Route tests

def test_route_single_bitrate_manifest(casterpak_clean):
    ## use test asset video to generate a single-bitrate manifest
    ##  http://localhost/i/test-video.mp4/master.m3u8
    
    #Request the single bitrate manifest:
    response = requests.get("http://localhost:80/i/test-video.mp4/master.m3u8")
    
    assert response.status_code == 200
    assert "http://localhost/i/test-video.mp4/index_0_av.m3u8" in response.text


# The big honkin functional test.
def test_route_csmil_parent_manifest(with_encodings):
   
    """test the route /i/test_video_encodings/test_video_,480p,720p,1080p,.mp4.csmil/master.m3u8
    assuming a directory /test_video_encodings/
    containing test_video_480p.mp4, test_video_720p.mp4 and test_video_1080p.mp4
    should return an adaptive bitrate master.m3u8
    follow the links in that also, and test a few segments exist, exercising bento4
    then actually look at the binary that comes from the url, and compare to the on-disk binary.
    """
    # The fixture created our encodings.

    # 1. Exercise the CSMIL route
    response = requests.get("http://localhost:80/i/test-video.mp4.transcodes/test-video,360p,480p,720p,.mp4.csmil/master.m3u8")

    assert response.status_code == 200

    # Assert that all three variants are present in the master manifest
    assert "test-video_720p.mp4" in response.text
    assert "test-video_480p.mp4" in response.text
    assert "test-video_360p.mp4" in response.text

    print("✅ CSMIL Master Manifest verified with 3 bitrates.")

    # Assert that the url's are well-formed
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/index_0_av.m3u8" in response.text

    response = requests.get("http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/index_0_av.m3u8")

    assert response.status_code == 200
    #make sure all the segments are there, and they are 2 seconds long.

    # Normalize the response into a list of strings, stripping \r\n
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]

    # 1. Assert the required HLS structure
    assert lines[0] == "#EXTM3U"
    assert "#EXT-X-VERSION:3" in lines
    assert "#EXT-X-TARGETDURATION:2" in lines
    assert lines[-1] == "#EXT-X-ENDLIST" # Ensure the VOD playlist is closed

    # 2. Assert the strict GOP segments (first two should be exactly 2 seconds)
    # We expect this exact string to appear at least twice.
    #  The final segment will not be 2 seconds, and will likely be a float like 1.066667 - forget testing that.
    assert lines.count("#EXTINF:2.000000,") >= 2

    # 3. Assert the actual segment files are correctly pathed
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts" in lines
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-1.ts" in lines
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-2.ts" in lines
    
    # 4. Optional: Assert the terminal segment exists and is a float > 0
    # We know segment-2 exists, we just don't care about its exact fractional length.

    # 5. Test that nginx hasn't corrupted the binary (by gzip, bad mime header, or something else)
    # The paths to the exact same file
    container = client.containers.get("casterpak_server")
    segment_path = "/tmp/segments/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts"
    segment_url = "http://localhost/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts"
    
    exit_code, output = container.exec_run(f"sha256sum {segment_path}")
    assert exit_code == 0, f"Could not hash file on disk: {output.decode()}"
    
    # sha256sum outputs "hash  filename\n", so we split it to just get the hash string
    expected_hash = output.decode().split()[0]

    # 2. Download the segment via Nginx or whatever serves as the proxy
    response = requests.get(segment_url)
    assert response.status_code == 200

    actual_hash = hashlib.sha256(response.content).hexdigest()

    assert actual_hash == expected_hash, "❌ Binary mismatch! HTTP proxy altered the data stream."

def test_nginx_to_flask_x_accel_handoff(casterpak_stack):
    """
    Verify Flask sends the X-Accel-Redirect header to Nginx.
    Executed from inside the Nginx container to simulate the proxy network path.
    """
    flask_container = client.containers.get("casterpak_server")
    nginx_container = client.containers.get("casterpak_nginx")
    
    # 1. Setup the fake segment file environment
    video_dir = "/tmp/segments/test-video.mp4.transcodes/test-video_360p.mp4"
    segment_file = f"{video_dir}/segment-0.ts"
    
    flask_container.exec_run(f"mkdir -p {video_dir}")
    flask_container.exec_run(f"sh -c 'echo \"test binary data\" > {segment_file}'")

    # We query the upstream Flask server exactly how Nginx does it via proxy_pass
    internal_flask_url = "http://casterpak_server:5000/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts"
    
    # Use curl to fetch only the headers (-I) from the upstream app
    exit_code, output = nginx_container.exec_run(f"curl -s -I {internal_flask_url}")
    
    assert exit_code == 0, f"Nginx container could not reach Flask. Network issue? Output: {output.decode()}"
    
    headers = output.decode('utf-8')
    
    # 1. Assert Flask returns 200 OK
    assert "200 OK" in headers, f"Flask did not return a 200 OK status. Headers:\n{headers}"
    
    # 2. Assert the handoff header is present
    assert "X-Accel-Redirect:" in headers, f"The X-Accel-Redirect header is missing! Headers:\n{headers}"
    
    # 3. Verify the exact internal routing path
    expected_path = "/protected_media/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts"
    assert expected_path in headers, f"Wrong internal path. Expected to find: {expected_path}"
    
    # 4. Verify the MIME type
    assert "Content-Type: video/MP2T" in headers, "MIME type is not set to video/MP2T"
    
    print("✅ Nginx successfully reached Flask and received the X-Accel-Redirect instructions.")


def test_child_manifest(casterpak_clean):
    """Verify requesting an index directly invokes Bento4 and returns a valid VOD manifest."""
    response = requests.get("http://localhost:80/i/test-video.mp4/index_0_av.m3u8")
    
    assert response.status_code == 200
    assert "#EXTM3U" in response.text
    assert "#EXT-X-TARGETDURATION" in response.text
    assert "segment-0.ts" in response.text
    assert "#EXT-X-ENDLIST" in response.text
   

def test_segment(casterpak_clean):
    """Verify requesting a segment directly creates it via Flask 404 fallback."""
    # Hit segment-1 directly, simulating a cached manifest but purged disk)
    response = requests.get("http://localhost:80/i/test-video.mp4/segment-0.ts")
    
    assert response.status_code == 200
    # Confirm Nginx successfully delivered the binary stream
    assert response.headers['Content-Type'] == 'video/MP2T'
    # Ensure it's not a 0-byte file
    assert len(response.content) > 1000
    

def test_route_abr_manifest_emergency(casterpak_clean):
    """
    Test Tier 3: Encodings are missing. 
    Should return a 200 OK with a dynamic JIT manifest.
    """
    response = requests.get("http://localhost:80/i/abr/test-video.mp4/master.m3u8")
    
    assert response.status_code == 200
    
    # Verify it generated the Emergency Master Manifest
    assert "#EXTM3U" in response.text
    assert "RESOLUTION=854x480" in response.text
    # JIT writes to its own JIT_-prefixed directory, kept separate from the
    # plain single-bitrate route's directory (see jit/jit_manager.py) -
    # the child manifest URL reflects that.
    assert "/i/JIT_test-video.mp4/index_0_av.m3u8" in response.text

    # We could also optionally check the container to ensure the FFmpeg process started,
    # but receiving the emergency manifest proves the routing logic fired correctly.

def test_route_abr_manifest_redirect(with_abr_cache_encodings):
    """
    Test Tier 2: Encodings exist. 
    Should return a 302 Found redirecting to the .csmil endpoint.
    """
    # allow_redirects=False is critical here so we can inspect the 302 response itself
    response = requests.get(
        "http://localhost:80/i/abr/test-video.mp4/master.m3u8", 
        allow_redirects=False
    )
    
    assert response.status_code == 302
    
    # Verify the Location header was built correctly
    expected_redirect = "/i/test-video.mp4.transcodes/test-video,360p,480p,720p,.mp4.csmil/master.m3u8"
    assert response.headers['Location'] == expected_redirect


def test_route_abr_manifest_concurrent_requests_dont_race(casterpak_clean):
    """
    Regression test for two duplicate-encode races found during manual
    concurrent-load testing, both closed by an atomic "did I win the race"
    check instead of a plain check-then-act:

    - ABR background encode: the encodingqueue table's lock_name PRIMARY KEY.
      8 concurrent enqueue()s -> 1 INSERT wins, 7 raise
      EncodingAlreadyInProgressError (encoding/encoding_process_manager.py).
    - JIT emergency stream: JitManager's os.makedirs()-as-lock
      (jit/jit_manager.py: trigger_jit_encoding()).

    The ABR guarantee now lives in the DB, and the ABR ffmpeg does NOT start
    inside the request anymore - the dispatcher spawns it up to
    ENCODING_POLL_INTERVAL seconds later. So: assert the DB claim immediately,
    then give the dispatcher up to 3x the poll interval to produce exactly one
    ABR ffmpeg. JIT still spawns synchronously in the request.
    """
    url = "http://localhost:80/i/abr/test-video.mp4/master.m3u8"
    container = client.containers.get("casterpak_server")

    responses = fire_concurrent_requests(url, count=8)

    assert all(r.status_code == 200 for r in responses), \
        [r.status_code for r in responses]

    # 1. The dedup guarantee, checked directly on the queue, right now -
    #    before the dispatcher has even polled. Exactly one row for this video.
    _, out = container.exec_run(
        "sqlite3 /var/lib/casterpak/data/cacheDB.db "
        "\"SELECT COUNT(*) FROM encodingqueue WHERE lock_name LIKE '%/test-video.mp4'\""
    )
    queue_rows = out.decode().strip()
    assert queue_rows == "1", \
        f"expected exactly 1 encodingqueue row from 8 concurrent requests, found {queue_rows}"

    # 2. JIT spawns synchronously inside the request - it's already there, once.
    jit_ffmpeg_count = count_matching_processes(container, "-preset ultrafast")
    assert jit_ffmpeg_count == 1, \
        f"expected exactly 1 JIT ffmpeg process from 8 concurrent requests, found {jit_ffmpeg_count}"

    # 3. The ABR encode is dispatched asynchronously. Poll up to 3x the poll
    #    interval for it to appear, asserting it never exceeds one.
    dispatch_wait = ENCODING_POLL_INTERVAL * 3
    deadline = time.time() + dispatch_wait
    abr_ffmpeg_count = 0
    while time.time() < deadline:
        abr_ffmpeg_count = count_matching_processes(container, "-preset veryfast")
        assert abr_ffmpeg_count <= 1, \
            f"more than one ABR ffmpeg process spawned: {abr_ffmpeg_count}"
        if abr_ffmpeg_count == 1:
            break
        time.sleep(1)

    assert abr_ffmpeg_count == 1, \
        f"no ABR ffmpeg process started within {dispatch_wait}s of 8 concurrent requests"


## ROADMAP.md Phase A item 4:
## "Renditions deleted entirely - hit /abr/, confirm EncodingManager/background
## encoding produces new renditions from scratch."
def test_route_abr_manifest_produces_renditions_from_scratch(casterpak_clean):
    """
    End-to-end: hit /abr/ for a video with NO cache and NO renditions at all,
    wait for the real background EncodingManager encode to finish (polling
    the same URL, not the fixture-faked with_abr_cache_encodings shortcut),
    then confirm it redirects to a working CSMIL manifest built from
    genuinely-encoded renditions.
    """
    url = "http://localhost:80/i/abr/test-video.mp4/master.m3u8"

    start_time = time.time()
    timeout = 120

    location = None
    while time.time() - start_time < timeout:
        response = requests.get(url, allow_redirects=False)
        if response.status_code == 302:
            location = response.headers['Location']
            break
        assert response.status_code == 200, \
            f"expected 200 (still encoding) or 302 (done), got {response.status_code}"
        time.sleep(2)

    elapsed = time.time() - start_time
    print(f"⏱  Background encode -> CSMIL redirect took {elapsed:.1f}s")

    assert location is not None, \
        f"EncodingManager never finished producing renditions within {timeout}s"
    assert location == "/i/test-video.mp4.transcodes/test-video,360p,480p,720p,.mp4.csmil/master.m3u8"

    # Confirm the redirect target is real, not just a plausible-looking URL -
    # fetch it and check all three renditions genuinely exist in the manifest.
    csmil_response = requests.get(f"http://localhost:80{location}")
    assert csmil_response.status_code == 200
    for label in ("360p", "480p", "720p"):
        assert f"test-video_{label}.mp4" in csmil_response.text

    # And confirm the renditions ffmpeg produced are real, playable files, not
    # empty placeholders - fetch one child manifest and one segment.
    child_response = requests.get(
        "http://localhost:80/i/test-video.mp4.transcodes/test-video_360p.mp4/index_0_av.m3u8"
    )
    assert child_response.status_code == 200
    assert "#EXTM3U" in child_response.text
    assert "segment-0.ts" in child_response.text

    segment_response = requests.get(
        "http://localhost:80/i/test-video.mp4.transcodes/test-video_360p.mp4/segment-0.ts"
    )
    assert segment_response.status_code == 200
    assert len(segment_response.content) > 1000


def test_route_abr_manifest_deep_directory_produces_reachable_renditions(casterpak_clean):
    """
    Same shape as test_route_abr_manifest_produces_renditions_from_scratch, but
    the source video lives in a SUB-DIRECTORY of videoParentPath.

    abr_manifest builds the CSMIL redirect with the full sub-path
    (/i/deep/dir/test-video.mp4.transcodes/...csmil/...). For that redirect to
    work, EncodingManager must write - and renditions_exist() must check -
    renditions at the matching sub-path under videoCachePath.

    Regression guard: EncodingManager.__init__ once built transcode_output_dir
    from the basename only, so a nested video's encode wrote to
    {cache}/test-video.mp4.transcodes/ while the redirect pointed at
    {cache}/deep/dir/test-video.mp4.transcodes/ - the 302 landed on a 404.
    """
    container = client.containers.get("casterpak_server")

    # a nested copy of the source video, under videoParentPath
    container.exec_run("mkdir -p /var/lib/casterpak/samples/deep/dir")
    rc, out = container.exec_run(
        "cp /var/lib/casterpak/samples/test-video.mp4 "
        "/var/lib/casterpak/samples/deep/dir/test-video.mp4"
    )
    assert rc == 0, out.decode()

    url = "http://localhost:80/i/abr/deep/dir/test-video.mp4/master.m3u8"

    start_time = time.time()
    timeout = 120
    location = None
    while time.time() - start_time < timeout:
        response = requests.get(url, allow_redirects=False)
        if response.status_code == 302:
            location = response.headers['Location']
            break
        assert response.status_code == 200, \
            f"expected 200 (still encoding) or 302 (done), got {response.status_code}"
        time.sleep(2)

    assert location is not None, \
        f"/abr/ for a nested video never redirected within {timeout}s"
    assert location == (
        "/i/deep/dir/test-video.mp4.transcodes/"
        "test-video,360p,480p,720p,.mp4.csmil/master.m3u8"
    )

    # The redirect target must actually serve - i.e. the renditions were
    # written where the sub-path'd URL looks for them.
    csmil_response = requests.get(f"http://localhost:80{location}")
    assert csmil_response.status_code == 200, (
        f"CSMIL from the /abr/ redirect is unreachable ({csmil_response.status_code}); "
        "renditions were written with the sub-directory dropped"
    )
    for label in ("360p", "480p", "720p"):
        assert f"test-video_{label}.mp4" in csmil_response.text

    child_response = requests.get(
        "http://localhost:80/i/deep/dir/test-video.mp4.transcodes/"
        "test-video_360p.mp4/index_0_av.m3u8"
    )
    assert child_response.status_code == 200
    assert "#EXTM3U" in child_response.text
    assert "segment-0.ts" in child_response.text


## ROADMAP.md Phase A item 5:
## "Emergency encoding (Tier 3) - hit /abr/ with no cache and no renditions
## while encoding is still in flight, confirm the JIT low-quality stream
## serves instead of a stall/404. Informally time this as an early gut-check
## against an SLA."
def test_route_abr_manifest_emergency_stream_is_actually_playable(casterpak_clean):
    """
    test_route_abr_manifest_emergency (above) only checks that the initial
    /abr/ response LOOKS like a valid emergency manifest. This test goes
    further: it follows that manifest's own child_url and fetches a real
    segment, proving the JIT stream is actually generating playable content -
    "instead of a stall/404" - not just that the routing logic fired. It also
    times the whole round trip as the roadmap's informal SLA gut-check (no
    committed threshold - this only fails on genuine timeout/error, the
    timing is reported for a human to judge).
    """
    start_time = time.time()

    response = requests.get("http://localhost:80/i/abr/test-video.mp4/master.m3u8")
    assert response.status_code == 200
    assert "#EXTM3U" in response.text

    # Pull the child manifest URL out of the emergency manifest text - the
    # last non-empty line, per the m3u8 this route generates. Unlike the
    # CSMIL/single-bitrate manifests (which use get_base_url() for absolute
    # URLs), the JIT emergency manifest's child_url is deliberately relative
    # (see jit_manager.get_m3u8_index_url()) - test_route_abr_manifest_
    # emergency's own passing assertion checks the same bare '/i/...' form.
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    child_url = lines[-1]
    assert child_url.startswith("/i/JIT_test-video.mp4/")

    # Real background ABR encoding is now also running in the background
    # (started by this same /abr/ request) - fetching the JIT child manifest
    # right now exercises "while encoding is still in flight" honestly,
    # rather than waiting and accidentally testing the warm-cache path instead.
    child_response = requests.get(f"http://localhost:80{child_url}")
    assert child_response.status_code == 200, \
        "JIT child manifest did not serve - this is the stall/404 this test exists to catch"
    assert "#EXTM3U" in child_response.text
    assert "segment-0.ts" in child_response.text

    segment_url = child_url.rsplit('/', 1)[0] + '/segment-0.ts'
    segment_response = requests.get(f"http://localhost:80{segment_url}")
    assert segment_response.status_code == 200, \
        "JIT first segment did not serve - this is the stall/404 this test exists to catch"
    assert segment_response.headers['Content-Type'] == 'video/MP2T'
    assert len(segment_response.content) > 1000, "JIT segment served but looks empty/truncated"

    elapsed = time.time() - start_time
    print(f"⏱  /abr/ request -> playable JIT segment took {elapsed:.2f}s (informal SLA gut-check, no hard threshold)")



