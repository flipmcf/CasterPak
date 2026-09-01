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

        This manages the endoded renditions of 'filename' by 
          1. epecting to find a directory 'filename.transcodes' in the input file cache.
          2. renditions in the form of 'filename.transcodes/file_{suffix}.mp4'
          (e.g., 'filename.transcodes/filename_720p.mp4')
        """
        self.full_path_filename = filename
        (self.dir_path, self.filename) = os.path.split(self.full_path_filename)
        (self.file_basename, self.file_ext) = os.path.splitext(self.filename)
        
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

    def renditions_exist(self) -> bool:
        """
        Checks if the ABR encoding process has completed successfully.
        """
        return self._all_exist()
    

    def start_background_encoding(self) -> None:
        """
        Spawns the heavy FFmpeg ABR encoding process and returns immediately.
        Non-blocking.
        """
        self._ensure_transcode_dir()
        
        # We only start it if it isn't already running or finished
        if not self.renditions_exist():
            logger.info(f"Starting background ABR encoding for {self.full_path_filename}")
            self._trigger_encoding()

    def list_rendition_files(self) -> list[str]:

        ## Note that the order of the files matters.   
        # The list of bitrates maps to output filenames when the ffmpeg command runs
        # They must be specified in the same order, or you will get a 720p encoding in a file named '360p'
        files = []
        for label in self.bitrates:
            files.append(os.path.join(self.transcode_output_dir, f"{self.file_basename}_{label}{self.file_ext}"))
    
        if not len(files) > 0:
            logger.warning("No Renditions configured to auto-transcode check config for [encoding_ladder] section")
        
        return files

    def _all_exist(self):
        ## TODO - this is not that easy.
        ##  it's not uncommon for an encoding process to create a bunch of files and crash.
        ##  We can't just trust that the file exists.  It needs to be a valid, correct encoding.
        ##  At least make sure the files are a bit bigger than a few bytes.
        return all(os.path.exists(p) for p in self.list_rendition_files())

    def _ensure_transcode_dir(self):
        """ compute transcoding directory and ensure it exists, creating if it doesn't"""
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

        Each rendition is its own self-contained output stanza (audio settings, maps,
        video codec settings, then that rendition's output file) rather than one shared
        block of indexed (`-c:v:0`, `-c:v:1`, ...) options followed by all output
        filenames at once. ffmpeg attaches output options to the *next* output filename
        it sees, so options and their filename must stay adjacent - stacking every
        option first and every filename after it silently dumps all of them onto the
        first output file and leaves the rest with no options at all.

        Audio is mapped per-output with '0:a:0?' (the '?' makes it optional) so a
        silent source doesn't fail the whole command.
        """
        max_cpu = os.cpu_count() or 4  ## Fallback to 4 if cpu_count() returns None
        max_threads = max(1, max_cpu - 1)

        cmd = ["nice", "-n", "10",
            "ffmpeg", "-y",
            "-threads", str(max_threads),
            "-i", self.full_path_filename,
        ]

        files = self.list_rendition_files()

        # Each rendition gets its own complete output stanza, ending in its own file.
        for i, label in enumerate(self.bitrates):
            spec = self.ladder[label]
            cmd.extend([
                "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-s:v", spec['res'],
                "-b:v", spec['bit'],
                "-g", "60",
                "-keyint_min", "60",
                "-sc_threshold", "0",
                "-r", "30",
                "-f", "mp4",
                "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                files[i]
            ])

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

        logger.debug(f"Forking off encoding command\n {cmd}")

        #hold on tight!.... 
        self.trancode_process = subprocess.Popen(cmd)



