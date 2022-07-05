import os
import typing as t

from bento4.mp4hls import OutputHls
from bento4.mp4utils import MediaSource
from config import get_config
from vodhls.factory import vodhls_media_playlist_factory
from vodhls.media_manifest_base import OptionsConfig


class MultivariantManager(object):
    config = get_config()

    def __init__(self, files):
        self.__master_playlist_name = None

        self.files: t.Iterable[t.Union[os.PathLike, str]] = files
        self.segment_managers = []
        self.baseurl = None

        for filename in self.files:
            manager = vodhls_media_playlist_factory(filename)
            self.segment_managers.append(manager)

        # Make sure all input files are local and ready.
        self.process_input_files()

    def process_input_files(self):
        """ for each segment manager, pull the input file into cache and reset it's ttl
        """
        [manager.process_input() for manager in self.segment_managers]

    def set_baseurl(self, url):
        [manager.set_baseurl(url) for manager in self.segment_managers]
        self.baseurl = url

    @property
    def master_playlist_name(self):
        if self.__master_playlist_name is not None:
            return self.__master_playlist_name
        else:
            raise ValueError

    @master_playlist_name.setter
    def master_playlist_name(self, value: str):
        self.__master_playlist_name = value
        if not self.__master_playlist_name.endswith('.m3u8'):
            self.__master_playlist_name += '.m3u8'

    @property
    def manifest_files(self):
        return [manager.input_file for manager in self.segment_managers]

    def output_hls(self):
        options_dict = {
            "hls_version": 3,
            "output_dir": self.config['output']['segmentParentPath'],
            "master_playlist_name": self.master_playlist_name,
            "media_playlist_name": "index_0_av.m3u8",
            "exec_dir": self.config['bento4']['binaryPath'],
            "force_output": True,
            'debug': True,
            'verbose': False,
            'min_buffer_time': 0.0,
            'base_url': self.baseurl,

        }

        options = OptionsConfig(options_dict)

        media_sources = [MediaSource(options, source) for source in self.manifest_files]
        for media_source in media_sources:
            media_source.has_audio = False
            media_source.has_video = False

        OutputHls(options, media_sources)
