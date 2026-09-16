#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
import re

import requests
import urllib
import logging

from vodhls.media_manifest_base import MediaManager_Base
logger = logging.getLogger('vodhls')


class MediaManager_http(MediaManager_Base):
    """
    Implements http based VODHLS Manager
    gets the input file from a http:// url and saves it to local input cache.
    """

    def fetch_and_cache(self):
        logger.debug(f"requesting {self.source_url}")
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)

        with requests.get(self.source_url, (self.connect_timeout, self.transfer_timeout), stream=True) as response:
            if response.status_code != 200:
                logger.error(f"error {response.status_code} while requesting {self.source_url}")
                raise FileNotFoundError

            with open(self.cached_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)


    @property
    def transfer_timeout(self) -> float:
        """
        :return: number of seconds to wait for the entire transfer of a video file.
        """
        return self.config.get('http', "transfer_timeout")

    @property
    def connect_timeout(self) -> float:
        """
        :return: number of seconds to wait for a connection to the http host - first bytes.
        """
        return self.config.get('http', "connect_timeout")
    

    @property
    def source_url(self):
        url_base: str = self.config['http']['url']

        #make sure baseurl ends in a '/'
        if not url_base.endswith('/'):
            url_base += '/'

        return urllib.parse.urljoin(url_base, self.filename)
