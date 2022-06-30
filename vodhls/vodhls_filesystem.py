import typing as t
import os
import shutil
import logging

from vodhls.base import VODHLS_MediaManager_Base
from vodhls.base import ConfigurationError

logger = logging.getLogger('vodhls')

class VODHLSMediaManager_filesystem(VODHLS_MediaManager_Base):
    """
    Implements filesystem-input based VODHLS Manager
    """

    def __init__(self, filename):
        super(VODHLSMediaManager_filesystem, self).__init__(filename)
        logger.info(f"vodhls filesystem manager for {self.filename}")


    @property
    def input_file(self) -> t.Union[os.PathLike, str]:
        if self.input_cache_enabled:
            return self.cached_filename
        else:
            return self.source_file

    def manage_input_file(self):

        try:
            os.stat(self.input_file)
        except FileNotFoundError:
            if self.input_cache_enabled:
                logger.debug(f"Input File cache miss for {self.input_file}")
                self.fetch_and_cache()
            else:
                raise
        finally:
            self.db.addrecord(filename=self.filename, timestamp=None)

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

