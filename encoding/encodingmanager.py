import os
import subprocess
import time

from config import get_config

import logging
logger = logging.getLogger('encoder')

class EncodingManager:
    def __init__(self, filename):
        """
        :param filename: The full path to the file (e.g., 'my_video')
        :param suffixes: List of bitrates/identifiers (e.g., ['high', 'low'])
        :param extension: The file extension (e.g., '.mp4')

        #This manages the endoded renditions of 'filename'
        # by 1. epecting to find a directory 'filename.transcodes' in the input file cache.
        # 2. renditions in the form of 'filename.transcodes/file_{suffix}.mp4'
        #  (e.g., 'filename.transcodes/file_720p.mp4')

        """
        self.full_path_filename = filename
        self.app_config = get_config()
        
        ##Debugging: print the config to verify it's loaded correctly
        config_dict = {section: dict(self.app_config[section]) for section in self.app_config.sections()}
        logger.debug(config_dict)

        self.ladder = {}
        if 'encoding_ladder' in self.app_config:
            for label, values in self.app_config['encoding_ladder'].items():
                res, bit = [v.strip() for v in values.split(',')]
                self.ladder[label] = {'res': res, 'bit': bit}

        else:
            self.ladder = {
                '1080p': {'res': '1920x1080', 'bit': '5000k'},
                '720p': {'res': '1280x720', 'bit': '2500k'},
                '480p': {'res': '854x480', 'bit': '1000k'},
                '360p': {'res': '640x360', 'bit': '750k'},
                '240p': {'res': '426x240', 'bit': '400k'},
            }
        
        self.bitrates = self.suffixes = list(self.ladder.keys())

        (self.dir_path, self.filename) = os.path.split(self.full_path_filename)

        video_output_cache = self.app_config.get('input','videoCachePath')
        logger.debug(f"Video output cache path from config: {video_output_cache}") 

        self.transcode_output_dir = os.path.join(video_output_cache, f"{self.filename}.transcodes")

        filename, extension = os.path.splitext(self.filename)
        
        # Calculate full paths
        self.rendition_paths = [
            os.path.join(self.transcode_output_dir, f"{filename}{s}.{extension}")
            for s in self.suffixes
        ]

    def get_renditions(self):
        """
        Main entry point. Returns paths if they exist, 
        otherwise triggers encoding and waits.
        """
        if not self._all_exist():
            self._ensure_transcode_dir()
            self._trigger_encoding()
            self._wait_for_anchor()
            
        return self.rendition_paths

    def _all_exist(self):
        return all(os.path.exists(p) for p in self.rendition_paths)

    def _wait_for_anchor(self, timeout=300):
        """Blocks until the 720p/anchor file is ready for Bento4 to sniff."""
        anchor = self.rendition_paths[min(1, len(self.rendition_paths)-1)] # Usually 720p
        start = time.time()

        logger.debug(f"Waiting for anchor file {anchor} to be created...")

        while not os.path.exists(anchor):
            elapsed = time.time() - start
            if elapsed > timeout:
                raise TimeoutError("Encoding took too long.")
            # Simple progress heartbeat in the console
            if elapsed % 10 == 0:
                logger.debug(f"   ... still encoding ({elapsed}s elapsed) ...")
            
            time.sleep(2)

    def _ensure_transcode_dir(self):
        if not os.path.exists(self.transcode_output_dir):
            os.makedirs(self.transcode_output_dir, exist_ok=True)

    def _trigger_encoding(self):
        """
        Finds the original source file and kicks off the FFmpeg multi-output.
        If the original is 'test_video.mp4', it assumes it's one level up
        from the '.transcodes' folder.
        """
        # Logic to find original: if we are in 'test.mp4.transcodes', 
        # the original is likely ../test.mp4
        source_file = os.path.abspath(os.path.join(self.dir_path, "..", self.prefix.rstrip('_')))
        if not source_file.endswith(self.extension):
             source_file += self.extension
             
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Source video {source_file} not found.")

        # Trigger non-blocking or blocking FFmpeg here
        # (Using the multi-output command discussed previously)
        self._run_ffmpeg()

    def get_ffmpeg_command(self):
        """
        Generates the list-style command for subprocess.
        Target this with test frameworks to verify the command structure without running FFmpeg.
        """
        # Global inputs and audio settings
        # Note: We map the audio to all outputs using the '?' to avoid failing on silent videos
        cmd = [
            "ffmpeg", "-y", "-i", self.full_path_filename,
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"
        ]

        # Dynamically build the video rungs
        for i, label in enumerate(self.bitrates):
            spec = self.ladder[label]
            cmd.extend([
                "-map", "0:v:0",
                f"-c:v:{i}", "libx264",
                f"-preset:{i}", "veryfast",
                f"-s:v:{i}", spec['res'],
                f"-b:v:{i}", spec['bit'],
                f"-g:{i}", "60",
                f"-keyint_min:{i}", "60",
                f"-sc_threshold:{i}", "0",
                f"-r:{i}", "30"
            ])

        # Add the output paths in the same order as the maps
        for label in self.bitrates:
            cmd.append(os.path.join(self.transcode_output_dir, f"file_{label}.mp4"))

        return cmd
        

    def _run_ffmpeg(self):
        """
        Kicks off a single FFmpeg process to generate all rungs.
        GOP=60 and FPS=30 ensures 2-second segments.

        IN THEORY, This should be highly efficient, we rely of ffmpeg's threading.
        reading the input only once, and writing multiple outputs in one pass.
        """


        cmd = self.get_ffmpeg_command(source_path)  

        if not os.path.exists(self.transcode_outputdir):
            os.makedirs(self.transcode_output_dir, exist_ok=True)

        cmd = self.get_ffmpeg_command(source_path)
        subprocess.run(cmd, check=True)


