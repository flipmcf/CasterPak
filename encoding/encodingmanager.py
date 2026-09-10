import os
from werkzeug.utils import safe_join

from config import get_config
from pathsafety import InvalidPathError

from . import EncodingAlreadyInProgressError, EncodingManagerError
from . import encoding_process_manager

import logging
logger = logging.getLogger('encoder')

class EncodingManager:
    def __init__(self, filename):
        """
        :param filename: The full path to the original video file (e.g., '/path/to/my_video.mp4')

        This manages the endoded renditions of 'filename' by 
          1. epecting to find a directory '/path/to/my_video.mp4.transcodes' in the input file cache.
          2. renditions in the form of my_video.{suffix}.mp4'
          (e.g., '/path/to/my_video.mp4.transcodes/my_video_720p.mp4')
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

        # Defense-in-depth: routes.py already validates the filename this
        # was built from (see pathsafety.py), so this should never actually
        # reject anything - but if it ever does, refuse to escape
        # videoCachePath rather than silently joining an absolute path or
        # '..' segment onto it.
        transcode_output_dir = safe_join(video_output_cache, f"{self.filename}.transcodes")
        if transcode_output_dir is None:
            raise InvalidPathError(f"unsafe path: {self.filename!r} escapes {video_output_cache!r}")
        self.transcode_output_dir = transcode_output_dir

    def renditions_exist(self) -> bool:
        """
        Checks if the ABR encoding process has completed successfully.
        """
        return not self.in_progress() and self._all_exist()
    
    @property
    def _process_name(self):
        return self.full_path_filename
    
    def queue_encoding_job(self, command: list[str]) -> None:
        """
        Writes to the database that a lock is in place for this video,
        along with the ffmpeg command to run for it. Writing the process ID
        of the process that actually runs that command comes later, once
        encoding_process_manager's dispatcher picks the job up.
        """
        # ###### SECURITY TODO (see banner in encoding/encoding_process_manager.py):
        # `command` leaves trusted code here - it is persisted to sqlite and later
        # exec'd verbatim by the dispatcher ######
        encoding_process_manager.lock_encoding(self._process_name, command)

    def in_progress(self) -> bool:
        """
        Checks if the ABR encoding process is currently running.
        """
        return encoding_process_manager.in_progress(self._process_name)

    def queue_background_encoding(self) -> None:
        """
        Requests a heavy FFmpeg ABR encode for this video and returns
        immediately. Non-blocking, and doesn't spawn anything itself:
        EncodingManager's job is building the ffmpeg command; actually
        running it is encoding_process_manager's dispatcher's job.

        Builds the command first (cheap, pure), then tries to claim the
        lock with it. If another request already claimed this video,
        lock_encoding raises EncodingAlreadyInProgressError before any
        directory gets created - losing the race should be a no-op, not
        wasted work.
        """
        if not os.path.exists(self.full_path_filename):
            raise FileNotFoundError(f"Source video {self.full_path_filename} not found.")

        # ###### SECURITY TODO (see banner in encoding/encoding_process_manager.py):
        # get_ffmpeg_command() is the ONLY trusted builder of encode argv. Its
        # output is about to be persisted and later exec'd from the DB, so this
        # must stay the only source of that argv until the dispatcher rebuilds it
        # itself instead of trusting a stored command. ######
        command = self.get_ffmpeg_command()

        try:
            self.queue_encoding_job(command)
        except EncodingAlreadyInProgressError:
            logger.info(f"ABR encoding already queued for {self.full_path_filename}, not queuing another.")
            raise

        self._ensure_transcode_dir()
        logger.info(f"Queued background ABR encoding for {self.full_path_filename}")


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
                files[i]
            ])

        return cmd

