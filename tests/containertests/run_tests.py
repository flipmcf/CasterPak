import os
import time
import pytest
import docker
import requests
import subprocess
import hashlib

client = docker.from_env()

test_env = os.environ.copy()

# when testing, use video files here as the source.
test_env["CASTERPAK_FILESYSTEM_VIDEOPARENTPATH"] = "/var/lib/casterpak/samples" 

def wait_for_log_signal(container_name, signal_text, timeout=30):
    """
    Streams logs from a container and returns only when signal_text is found.
    """
    container = client.containers.get(container_name)
    start_time = time.time()
    
    # .logs(stream=True) returns a generator that yields log lines as they appear
    for line in container.logs(stream=True, follow=True):
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



@pytest.fixture(scope="module", autouse=True)
def casterpak_stack():

    print("\n🚀 Building and starting CasterPak...")
    subprocess.run(["docker", "compose", "build", "--no-cache" ], check=True, env=test_env)
    subprocess.run(["docker", "compose", "up", "-d", "--remove-orphans"] , check=True, env=test_env)

    # 1. Wait for Flask Backend (adjust signal to match your actual startup log)
    # Common Gunicorn/Flask signal: "Listening at: http://0.0.0.0:5000"
    print("⏳ Waiting for Flask backend signal...")
    wait_for_log_signal("casterpak_server", "[INFO] Listening at: http://0.0.0.0:5000")


    # 2. Wait for Nginx (adjust signal to match your actual startup log)
    # Common Nginx signal: "start worker process" or "ready for connections"
    print("⏳ Waiting for Nginx proxy signal...")
    wait_for_log_signal("casterpak_nginx", "start worker process")

    print("✅ Stack is fully initialized and signaling health.")

    container = client.containers.get("casterpak_server")
    target_file = "/var/lib/casterpak/samples/test-video.mp4"
    exit_code, _ = container.exec_run(f"test -f {target_file}")
    
    assert exit_code == 0, f"Critical failure: {target_file} not found in container."
    print(f"✅ Verified test asset: {target_file}")
    
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
    
    container = client.containers.get("casterpak_server")
    
    for table in [SEGMENT_FILE_CACHE, INPUT_FILE_CACHE]:
        _, out = container.exec_run(f'sqlite3 sqlite.db "DELETE FROM {table}"')

    
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
    """

    container = client.containers.get("casterpak_server")
    test_dir = test_env["CASTERPAK_FILESYSTEM_VIDEOPARENTPATH"]
    encoding_output_dir = f"{test_dir}/test-video.mp4.transcodes"

    check_cmd = f"test -f {encoding_output_dir}/test-video_360.mp4"
    exit_code, _ = container.exec_run(check_cmd)

    if exit_code == 0:
        print("✨ Transcoded variants already exist. Skipping FFmpeg...")
    else:
        exit_code, _ = container.exec_run(f"mkdir {encoding_output_dir}")

        test_file = "/mnt/data/test_video.mp4"

        #be nice  use half available cpu's
        max_cpu = os.cpu_count() or 4  ## Fallback to 4 if cpu_count() returns None
        max_threads = max(1, int(max_cpu/2))
        threads = f"-threads {max_threads}"
        nice = "nice -n 19"

        #create a few encodings manually using our test asset:
        ffmpeg_cmd = (
            f"{nice} ffmpeg -y {threads} -t 5 -i {test_file} "
            f"-vf scale=-2:720 -c:v libx264 -preset ultrafast -b:v 2500k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_720.mp4 "
            f"-vf scale=-2:480 -c:v libx264 -preset ultrafast -b:v 1200k -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_480.mp4 "
            f"-vf scale=-2:360 -c:v libx264 -preset ultrafast -b:v 600k  -r 15 -g 30 -keyint_min 30 -sc_threshold 0 {encoding_output_dir}/test-video_360.mp4 "
        )
        
        print("🎬 Transcoding test variants...")
        exit_code, output = container.exec_run(f"sh -c '{ffmpeg_cmd}'")
        assert exit_code == 0, f"FFmpeg failed: {output.decode()}"


#nginx tests

def test_nginx_proxy_to_flask():
    """Verify that Nginx successfully proxies to the Flask backend."""
    response = requests.get("http://localhost:80/")

    #there is nothing at the root of nginx
    assert response.status_code == 404

    #a failure is a 'cannot connect'
    
def test_nginx_static_testing_route():
    """Verify the /testing/ alias is serving the test player."""
    response = requests.get("http://localhost:80/testing/test_player.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]

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
    response = requests.get("http://localhost:80/i/test-video.mp4.transcodes/test-video_,360,480,720,.mp4.csmil/master.m3u8")
    
    assert response.status_code == 200
    
    # Assert that all three variants are present in the master manifest
    assert "test-video_720.mp4" in response.text
    assert "test-video_480.mp4" in response.text
    assert "test-video_360.mp4" in response.text
    
    print("✅ CSMIL Master Manifest verified with 3 bitrates.")

    # Assert that the url's are well-formed
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/index_0_av.m3u8" in response.text

    response = requests.get("http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/index_0_av.m3u8")

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
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/segment-0.ts" in lines
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/segment-1.ts" in lines
    assert "http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/segment-2.ts" in lines
    
    # 4. Optional: Assert the terminal segment exists and is a float > 0
    # We know segment-2 exists, we just don't care about its exact fractional length.

    # 5. Test that nginx hasn't corrupted the binary (by gzip, bad mime header, or something else)
    # The paths to the exact same file
    container = client.containers.get("casterpak_server")
    segment_path = "/tmp/segments/test-video.mp4.transcodes/test-video_360.mp4/segment-0.ts"
    segment_url = "http://localhost/i/test-video.mp4.transcodes/test-video_360.mp4/segment-0.ts"
    
    exit_code, output = container.exec_run(f"sha256sum {segment_path}")
    assert exit_code == 0, f"Could not hash file on disk: {output.decode()}"
    
    # sha256sum outputs "hash  filename\n", so we split it to just get the hash string
    expected_hash = output.decode().split()[0]

    # 2. Download the segment via Nginx or whatever serves as the proxy
    response = requests.get(segment_url)
    assert response.status_code == 200

    actual_hash = hashlib.sha256(response.content).hexdigest()

    assert actual_hash == expected_hash, "❌ Binary mismatch! HTTP proxy altered the data stream."

def test_child_manifest(casterpak_clean):
    ## /i/test_video.mp4/index_0_av.m3u8
    ## explicitly do this as the first request.
    ## we want this to work without calling master.m3u8 in case of a cache miss or server restart
    pass

def test_segment(casterpak_clean):
    ## /i/test_video.mp4/segment-1.ts
    ## explicitly do this as the first request - assume the browswer had a cached index_0_av and we just woke up.
    pass

def test_route_abr_manifest(casterpak_clean):
    ## Big test - do an encoding with a specified ladder
    pass


