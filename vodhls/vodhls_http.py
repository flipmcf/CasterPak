import os
import re

import requests
import urllib
import logging

from vodhls.media_base import MediaManager_Base
logger = logging.getLogger('vodhls')


class MediaManager_http(MediaManager_Base):
    """
    Implements http based VODHLS Manager
    gets the input file from a http:// url and saves it to local input cache.
    """

    def fetch_and_cache(self):
        logger.debug(f"requesting {self.source_url}")
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)

        with requests.get(self.source_url, timeout=self.fetch_timeout, stream=True) as response:
            if response.status_code != 200:
                logger.error(f"error {response.status_code} while requesting {self.source_url}")
                raise FileNotFoundError

            with open(self.cached_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)


    @property
    def fetch_timeout(self) -> float:
        """
        :return: number of seconds to wait for a response from remote server when transferring input files
        """
        return 1.0

    @property
    def source_url(self):
        url_base: str = self.config['http']['url']

        #make sure baseurl ends in a '/'
        if not url_base.endswith('/'):
            url_base += '/'

        return urllib.parse.urljoin(url_base, self.filename)
