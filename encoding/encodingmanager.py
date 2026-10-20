#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
from werkzeug.utils import safe_join

from config import get_config
from pathsafety import InvalidPathError

from . import EncodingAlreadyInProgressError, EncodingManagerError
from . import encoding_process_manager

import logging
logger = logging.getLogger('encoder')

class EncodingManager:
    def __init__(self, library_path):
        """
        :param library_path: the video's path in the library, which is also its URL path
            (e.g. 'shows/2024/episode.mp4'). It is not a filesystem path: where the source
            file actually lives is the input layer's business, and the caller hands the
            local file to queue_background_encoding().

        This manages the encoded renditions of 'library_path' by
          1. expecting to find a directory '<videoCachePath>/shows/2024/episode.mp4.transcodes'
             in the input file cache.
          2. renditions in the form of episode_720p.mp4
          (e.g., '<videoCachePath>/shows/2024/episode.mp4.transcodes/episode_720p.mp4')
        """
        self.library_path = library_path
        (self.dir_path, self.filename) = os.path.split(self.library_path)
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

        video_output_cache = self.app_config.get('input', 'videoCachePath')
        logger.debug(f"Video output cache path from config: {video_output_cache}")

        # The transcode cache is keyed by the library path, whatever the input type:
        # 'shows/2024/episode.mp4' gets its renditions under
        #     {videoCachePath}/shows/2024/episode.mp4.transcodes/
        # This has to agree with what casterpak/routes.py:abr_manifest builds for the
        # CSMIL redirect and with where the input layer resolves renditions coming back in.
        #
        # Defense-in-depth: routes.py already validates the path this was built from
        # (see pathsafety.py), so this should never actually reject anything - but if
        # the path somehow escapes videoCachePath, safe_join returns None; refuse.
        transcode_output_dir = safe_join(video_output_cache, f"{self.library_path}.transcodes")
        if transcode_output_dir is None:
            raise InvalidPathError(
                f"unsafe path: {self.library_path!r} escapes {video_output_cache!r}"
            )
        self.transcode_output_dir = transcode_output_dir

    def renditions_exist(self) -> bool:
        """
        Checks if the ABR encoding process has completed successfully.
        """
        return not self.in_progress() and self._all_exist()
    
    @property
    def _process_name(self):
        return self.library_path
    
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

    def queue_background_encoding(self, source_file: str) -> None:
        """
        :param source_file: the local file to encode - what the input layer's
            MediaManager.input_file returns once process_input() has run.

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
        if not os.path.exists(source_file):
            raise FileNotFoundError(f"Source video {source_file} not found.")

        # ###### SECURITY TODO (see banner in encoding/encoding_process_manager.py):
        # get_ffmpeg_command() is the ONLY trusted builder of encode argv. Its
        # output is about to be persisted and later exec'd from the DB, so this
        # must stay the only source of that argv until the dispatcher rebuilds it
        # itself instead of trusting a stored command. ######
        command = self.get_ffmpeg_command(source_file)

        try:
            self.queue_encoding_job(command)
        except EncodingAlreadyInProgressError:
            logger.info(f"ABR encoding already queued for {self.library_path}, not queuing another.")
            raise

        self._ensure_transcode_dir()
        logger.info(f"Queued background ABR encoding for {self.library_path}")

    """ delimiter for renditions defined here."""
    rendition_delimiter = "_"

    @property
    def rendition_prefix(self) -> str:
        """
        The filename prefix of every rendition this manager writes: the source
        basename plus the '_' that separates it from the ladder label.
        foo.mp4 will now have previxes foo_high.mp4, foo_mid.mp4 and foo_low.mp4 
        """
        return f"{self.file_basename}{self.rendition_delimiter}"

    def list_rendition_files(self) -> list[str]:

        ## Note that the order of the files matters.   
        # The list of bitrates maps to output filenames when the ffmpeg command runs
        # They must be specified in the same order, or you will get a 720p encoding in a file named '360p'
        files = []
        for label in self.bitrates:
            files.append(os.path.join(self.transcode_output_dir, f"{self.rendition_prefix}{label}{self.file_ext}"))
    
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

    def get_ffmpeg_command(self, source_file: str) -> list[str]:
        """
        Generates the list-style command for subprocess, encoding the local file `source_file`.
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
            "-i", source_file,
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

