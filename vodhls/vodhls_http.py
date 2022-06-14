import os
import requests
import urllib
import logging

from vodhls.base import VODHLSManager_Base
logger = logging.getLogger('vodhls')


class VODHLSManager_http(VODHLSManager_Base):
    """
    Implements http based VODHLS Manager
    gets the input file from a http:// url and saves it to local input cache.
    """

    def fetch_and_cache(self):
        logger.debug(f"requesting {self.source_url}")
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)
        response = requests.get(self.source_url)
        if response.status_code != 200:
            logger.error(f"error {response.status_code} while requesting {self.source_url}")
            raise FileNotFoundError

        with open(self.cached_filename, "wb") as f:
            f.write(response.content)

    @property
    def source_url(self):
        url_base: str = self.config['http']['url']

        #make sure baseurl ends in a '/'
        if not url_base.endswith('/'):
            url_base += '/'

        return urllib.parse.urljoin(url_base, self.filename)
