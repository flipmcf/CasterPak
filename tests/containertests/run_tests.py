import time
import pytest
import docker
import requests
import subprocess

client = docker.from_env()

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

@pytest.fixture(scope="module", autouse=True)
def casterpak_stack():
    print("\n🚀 Building and starting CasterPak...")
    subprocess.run(["docker", "compose", "build", "--no-cache"], check=True)
    subprocess.run(["docker", "compose", "up", "-d"], check=True)

    # 1. Wait for Flask Backend (adjust signal to match your actual startup log)
    # Common Gunicorn/Flask signal: "Listening at: http://0.0.0.0:5000"
    print("⏳ Waiting for Flask backend signal...")
    wait_for_log_signal("casterpak_server", "[INFO] Listening at: http://0.0.0.0:5000")


    # 2. Wait for Nginx (adjust signal to match your actual startup log)
    # Common Nginx signal: "start worker process" or "ready for connections"
    print("⏳ Waiting for Nginx proxy signal...")
    wait_for_log_signal("casterpak_nginx", "start worker process")

    print("✅ Stack is fully initialized and signaling health.")
    
    yield 

    print("\n🧹 Tearing down...")
    subprocess.run(["docker", "compose", "down", "-v"], check=True)


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

def test_route_single_bitrate_manifest():
    ## drop a video test into (or bake in an easter egg video) to the container
    ##  http://localhost/i/test_video.mp4/master.m3u8
    pass

def test_route_csmil_parent_manifest():
    ## Must upload encodings first, then test
    ## /i/test_video_encodings/test_video_,480p,720p,1080p,.mp4.csmil/master.m3u8
    ## assuming a directory /test_video_encodings/
    ##  containing test_video_480p.mp4, test_video_720p.mp4 and test_video_1080p.mp4
    ##  should return an adaptive bitrate master.m3u8
    ##
    ## follow the links in that also, and test a few segments exist, exercising bento4
    pass

def test_child_manifest():
    ## /i/test_video.mp4/index_0_av.m3u8
    ## explicitly do this as the first request.
    ## we want this to work without calling master.m3u8 in case of a cache miss or server restart
    pass

def test_segment():
    ## /i/test_video.mp4/segment-1.ts
    ## explicitly do this as the first request - assume the browswer had a cached index_0_av and we just woke up.
    pass

def test_route_abr_manifest():
    ## Big test - do an encoding with a specified ladder
    pass


