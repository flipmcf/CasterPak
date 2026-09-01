#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import typing as t
import os
import shutil
import logging

from vodhls.media_manifest_base import MediaManager_Base
from vodhls.media_manifest_base import ConfigurationError

logger = logging.getLogger('vodhls')


class MediaManager_filesystem(MediaManager_Base):
    """
    Implements filesystem-input based VODHLS Manager
    """

    def __init__(self, filename):
        super(MediaManager_filesystem, self).__init__(filename)
        logger.info(f"vodhls filesystem manager for {self.filename}")


    @property
    def input_file(self) -> t.Union[os.PathLike, str]:
        #this should be simple - if input_cache_enabled, then look for the file in the input cache. 
        # Otherwise, look for it at the source.  (see input caching)
        # 
        #however, auto-encoding threw a wrench into that.  
        # If input caching is off, but auto-transcoding is on, the files WILL be in the input cache
        # When we finally can signal that auto-encoded variants are created and somewhere else, 
        #   -auto encoding cache - 
        # this 'stat' hack can go away.

        if self.input_cache_enabled:
            return self.cached_filename
        else:
            #Input cache disabled, file MUST be at the origin library.
            try: 
                os.stat(self.source_file)
            except FileNotFoundError:
                #At this point, we know the input rendition file is not in the origin library
                # Maybe it was auto-transcoded with 'input_cache_enabled == False'
                return self.cached_filename
            
            return self.source_file

    def manage_input_file(self):
        logger.debug(f"manage_input_file for {self.input_file}")

        try:
            os.stat(self.input_file)
        except FileNotFoundError:
            if self.input_cache_enabled:
                logger.debug(f"Input File cache miss for {self.input_file}")
                self.fetch_and_cache()
                self.db.addrecord(filename=self.filename, timestamp=None)
            else:
                raise

        return #documenting end of function only

    process_input = manage_input_file

    def fetch_and_cache(self):
        logger.debug(f"copy {self.source_file}, {self.cached_filename}")
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)
        shutil.copy(self.source_file, self.cached_filename)

    @property
    def source_file(self) -> t.Union[os.PathLike, str]:
        try:
            path = self.config['filesystem']['videoParentPath']
        except KeyError:
            msg = "videoParentPath not configured in casterpak config.ini, 'filesystem' section"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.filename)

    @property
    def input_cache_enabled(self):
        return self.config['filesystem'].getboolean('cache_input')

