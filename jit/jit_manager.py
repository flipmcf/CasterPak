import os
import subprocess
import time

import logging
logger = logging.getLogger('jit')

from vodhls import EncodingError


class JitManager:
    """
    Manages a single "just-in-time" emergency HLS stream: a fast, low-quality,
    live-appendable rendition generated on the fly when no pre-encoded renditions
    (single-bitrate or ABR) exist yet for a source video.

    This is a failsafe. It's preferred that files be provided pre-transcoded for
    ABR support. But if CasterPak discovers there is only a source file, it will
    attempt to transcode a low-quality stream on the fly so playback isn't blocked
    on the (much slower) real encoding ladder.

    If you're reading this, you're probably spending too much money and it's
    time to optimize your video library.
    """

    def __init__(self, dir_name, input_filepath, output_dir, manifest_path):
        """
        :param dir_name: the URL-facing path segment the client requested (e.g.
            'projects/2024/video.mp4') - kept as-is, straight from the caller,
            so the URL this manager hands back can't drift from the one that's
            already resolved everywhere else for this video.
        :param input_filepath: full path to the source video to transcode
        :param output_dir: directory where JIT segments will be written
        :param manifest_path: full path to the JIT media playlist (.m3u8) to generate
        """
        self.dir_name = dir_name
        self.input_filepath = input_filepath
        self.manifest_path = manifest_path

        # We prefix the output directory with "JIT_" to avoid colliding with any pre-encoded renditions that may exist in the same directory.
        parent, name = os.path.split(output_dir)
        self.output_dir = os.path.join(parent, f"JIT_{name}")

        # and then we also prefix the dir_name with "JIT_" so that the URL path matches the output directory name, and we don't collide with any pre-encoded renditions that may exist in the same directory.
        parent, name = os.path.split(dir_name)
        self.dir_name = os.path.join(parent, f"JIT_{name}")

        # We must match Bento4's exact naming convention from media_manifest_base.py
        self.segment_template = os.path.join(self.output_dir, "segment-%d.ts")
        self.first_segment_path = os.path.join(self.output_dir, "segment-0.ts")

    def get_m3u8_index_url(self) -> str:
        """
        Public URL for the JIT media playlist - routes back to the existing
        child_manifest route via `dir_name`, and takes the filename from
        `manifest_path` rather than a second hardcoded literal, so this can't
        drift from the file FFmpeg is actually told to write to.
        """

        

        return f"/i/{self.dir_name}/{os.path.basename(self.manifest_path)}"

    def first_segment_exists(self) -> bool:
        """
        True once the first JIT segment has been written to disk - our signal
        that a JIT stream for this video is already up and running (or finished),
        so callers shouldn't start another one.
        """
        return os.path.exists(self.first_segment_path)

    def get_ffmpeg_command(self) -> list[str]:
        """
        Generates the list-style command for subprocess.
        Target this with test frameworks to verify the command structure without running FFmpeg.
        """
        return [
            "ffmpeg", "-y", "-i", self.input_filepath,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-vf", "scale=-2:480",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "0",
            "-hls_playlist_type", "event",
            "-hls_segment_filename", self.segment_template,
            self.manifest_path,
        ]
    
    def trigger_jit_encoding(self, timeout: float = 5.0) -> bool:
        """
        Spawns a detached FFmpeg process to generate a live, appendable HLS stream.
        Blocks (polling) until the first segment appears, or raises EncodingError
        if it doesn't show up within `timeout` seconds.

        This will also block if it finds a JIT encode already in progress.
        """
        ## Directory is the lockfile, if the directory exists, skip 
        process = None

        try:
            os.makedirs(self.output_dir, exist_ok=False)
        except FileExistsError:
            # The directory already exists, which means a JIT encode is already in progress.
            logger.info("JIT directory already exists, skipping creation.")
        else:
            # The directory was created successfully, which means we need to kick off encoding.
            logger.info(f"Created JIT directory: {self.output_dir}")
            cmd = self.get_ffmpeg_command()
            logger.info(f"Spawning Emergency JIT Transcode for {self.input_filepath}")

            # Popen detaches the process. stdout/stderr to DEVNULL keeps Docker logs clean.
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        finally:
            start_time = time.time()

            while True:

                if self.first_segment_exists():
                    logger.info("First JIT segment detected! Releasing request to Nginx.")
                    return True

                if time.time() - start_time > timeout:
                    logger.error("JIT Transcoding timed out.")
                    if process is not None:
                        process.kill()
                    os.rmdir(self.output_dir)  # clean up the directory if the process failed
                    raise EncodingError("JIT Transcoding failed to start in time.")

                #poll the process to make sure we didn't get an error
                if process is not None:
                    retcode = process.poll()
                    if retcode is not None and retcode != 0:
                        logger.error(f"JIT Transcoding process exited with code {retcode}.")
                        os.rmdir(self.output_dir)  # clean up the directory if the process failed
                        raise EncodingError(f"JIT Transcoding process exited with code {retcode}.")

                time.sleep(0.1)