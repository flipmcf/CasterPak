import os
import subprocess
import time

from config import get_config

import logging
logger = logging.getLogger('encoder')

class EncodingManager:
    def __init__(self, filename):
        """
        :param filename: The full path to the original video file (e.g., '/path/to/my_video')

        #This manages the endoded renditions of 'filename'
        # by 1. epecting to find a directory 'filename.transcodes' in the input file cache.
        # 2. renditions in the form of 'filename.transcodes/file_{suffix}.mp4'
        #  (e.g., 'filename.transcodes/filename_720p.mp4')

        """
        self.full_path_filename = filename
        (self.dir_path, self.filename) = os.path.split(self.full_path_filename)
        
        self.app_config = get_config()
        
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
        
        self.bitrates = list(self.ladder.keys())

        logger.debug("auto-bitrates from config:")
        logger.debug(self.bitrates)

        video_output_cache = self.app_config.get('input','videoCachePath')
        logger.debug(f"Video output cache path from config: {video_output_cache}") 

        self.transcode_output_dir = os.path.join(video_output_cache, f"{self.filename}.transcodes")
        
        # Calculate full paths
        self.rendition_paths = self.list_rendition_files()

    def get_renditions(self):
        """
        Main entry point. Returns paths if they exist, 
        otherwise triggers encoding and waits.
        """

        ## This is the function that can really make the reponse drag if encoding jobs are big
        ## Add logic here to:
        #     pick a rendition to get a few seconds of,
        #     pass that off to the hls stream encoder,
        #     give the user something to watch.
        ## This will be tricky.   It's easy just to make the user wait for all encoding to finish.

        if not self._all_exist():
            self._ensure_transcode_dir()
            self._trigger_encoding()
            self._wait_for_anchor()
            
        return self.list_rendition_files()
    
    def list_rendition_files(self):

        ## Note that the order of the files matters.   
        # The list of bitrates maps to output filenames when the ffmpeg command runs
        # They must be specified in the same order, or you will get a 720p encoding in a file named '360p'
        files = []
        for label in self.bitrates:
            files.append(os.path.join(self.transcode_output_dir, f"{self.filename}_{label}.mp4"))
    
        if not len(files) > 0:
            logger.warning("No Renditions configured to auto-transcode check config for [encoding_ladder] section")
        
        return files

    def _all_exist(self):
        ## TODO - this is not that easy.
        ##  it's not uncommon for an encoding process to create a bunch of files and crash.
        ##  We can't just trust that the file exists.  It needs to be a valid, correct encoding.
        ##  At least make sure the files are a bit bigger than a few bytes.
        return all(os.path.exists(p) for p in self.list_rendition_files())

    def _wait_for_anchor(self, timeout=600):
        """Blocks until the 720p/anchor file is ready for Bento4 to sniff."""

        # We want a size that represents roughly 5-10 seconds of 720p video.
        # At 2.5Mbps, 5 seconds is ~1.5MB. Let's be safe and wait for 1MB.
        MIN_SIZE = 1000000 

        anchor = self.rendition_paths[min(1, len(self.rendition_paths)-1)] # Usually 720p
        start = time.time()

        logger.debug(f"Waiting for anchor file {anchor} to be created...")

        current_size = 0
        while self.trancode_process.poll() is None:

            if os.path.exists(anchor):
                current_size = os.path.getsize(anchor)
            
            # Check if we have enough "meat" in the file to start segmenting
            if current_size > MIN_SIZE:
                # Wait one more second to ensure the last write call finished
                time.sleep(1) 
                logger.debug(f"Anchor ready ({current_size // 1024} KB). Handing to Bento4.")
                return 
            
            elapsed = time.time() - start
            if elapsed > timeout:
                raise TimeoutError("Encoding took too long.")
            
            # Simple progress heartbeat in the console
            if elapsed % 10 == 0:
                logger.debug(f"   ... still encoding ({elapsed}s elapsed) ...")
            
            #this gives gunicorn and the os time to breath.
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
       
        if not os.path.exists(self.full_path_filename):
            raise FileNotFoundError(f"Source video {self.full_path_filename} not found.")

        # Trigger non-blocking or blocking FFmpeg here
        # (Using the multi-output command discussed previously)
        self._run_ffmpeg()

    def get_ffmpeg_command(self) -> list[str]:
        """
        Generates the list-style command for subprocess.
        Target this with test frameworks to verify the command structure without running FFmpeg.
        """
        # Global inputs and audio settings
        # Note: We map the audio to all outputs using the '?' to avoid failing on silent videos

        max_cpu = os.cpu_count() or 4  ## Fallback to 4 if cpu_count() returns None
        max_threads = max(1, max_cpu - 1)

        cmd = ["nice", "-n", "10",
            "ffmpeg", "-y",
            "-threads", str(max_threads),
            "-i", self.full_path_filename,
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
        cmd.extend(self.list_rendition_files())

        return cmd
        

    def _run_ffmpeg(self):
        """
        Kicks off a single FFmpeg process to generate all rungs.
        GOP=60 and FPS=30 ensures 2-second segments.

        IN THEORY, This should be highly efficient, we rely of ffmpeg's threading.
        reading the input only once, and writing multiple outputs in one pass.
        """

        if not os.path.exists(self.transcode_output_dir):
            os.makedirs(self.transcode_output_dir, exist_ok=True)

        cmd = self.get_ffmpeg_command()

        #hold on tight!.... 
        self.trancode_process = subprocess.Popen(cmd)



