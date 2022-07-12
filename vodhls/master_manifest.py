import os
import typing as t

from . import ConfigurationError

from config import get_config
from vodhls.factory import vodhls_media_playlist_factory
from vodhls.media_manifest_base import OptionsConfig

import logging
logger = logging.getLogger('vodhls_master')


class MultivariantManager(object):
    config = get_config()

    def __init__(self, files, output_dir):
        self.__master_playlist_name = None
        self.__master_playlist_dir = output_dir
        self.files: t.Iterable[t.Union[os.PathLike, str]] = files
        self.segment_managers = []
        self.baseurl = None
        self.input_files_processed = False

    def process_input_files(self):
        """ for each segment manager, pull the input file into cache and reset it's ttl
        """
        if len(self.segment_managers) == 0:
            for filename in self.files:
                manager = dict()
                manager['segment_manager'] = vodhls_media_playlist_factory(filename)
                manager['status'] = 'unprocessed'
                self.segment_managers.append(manager)

        fail_with_404 = True  # Raise a FileNotFound only if ALL managers fail.
        for manager in self.segment_managers:
            try:
                manager['segment_manager'].process_input()
                manager['status'] = 'ready'
            except FileNotFoundError:
                manager['status'] = 'failed'
            else:
                # one of the inputs processed successfully
                fail_with_404 = False

        self.input_files_processed = True

        if fail_with_404:
            raise FileNotFoundError

    def set_baseurl(self, url):
        [manager['segment_manager'].set_baseurl(url) for manager in self.segment_managers]
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

    def manifest_exists(self) -> bool:
        manifest_path = os.path.join(self.output_dir, self.master_playlist_name)
        try:
            logger.debug(f"stat: {manifest_path}")
            os.stat(manifest_path)
        except FileNotFoundError:
            return False
        return True

    @property
    def output_dir(self) -> t.Union[os.PathLike, str]:
        """
        :return:  the directory name that will contain the master manifest file.
        This is the full path to the specific hls stream of the input file.
        """
        try:
            path = self.config['output']['segmentParentPath']
        except KeyError:
            msg = "segmentParentPath not configured in casterpak config.ini 'output' section"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.__master_playlist_dir)

    @property
    def manifest_files(self):
        return [manager['segment_manager'].input_file for manager in self.segment_managers
                if manager['status'] == 'ready']

    def output_hls(self):
        """ output the master manifest file.
            write it as a sibling to all the segment directories
            created by media_manifest creators
        """
        if not self.input_files_processed:
            self.process_input_files()

        options_dict = {
            "hls_version": 3,
            "output_dir": self.output_dir,
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

        # create output directory from input file path
        try:
            os.makedirs(self.output_dir)
        except FileExistsError:
            pass

        # create output subdirectories for media:
        for manager in self.segment_managers:
            try:
                os.makedirs(manager['segment_manager'].output_dir)
            except FileExistsError:
                pass

        create_master_playlist(options, media_sources)


import shutil
import json

from bento4.mp4hls import AnalyzeSources
from bento4.mp4hls import ProcessSource
from bento4.mp4hls import SelectAudioTracks
from bento4.mp4hls import ComputeCodecName
from bento4.mp4hls import VERSION, SDK_REVISION
from bento4.mp4hls import CreateSubtitlesPlaylist
from bento4.mp4utils import MediaSource
from bento4.mp4utils import MakeNewDir
from bento4.subtitles import SubtitlesFile

bento4logger = logging.getLogger('output_master_playlist')


def create_master_playlist(options, media_sources):
    """ Code cut-and-pasted from bento4 mp4hls to create a master playlist
        without processing media sources into medis playlists and segment files.
    """

    mp4_sources = [media_source for media_source in media_sources if media_source.format == 'mp4']

    # analyze the media sources
    AnalyzeSources(options, media_sources)

    # select audio tracks
    audio_tracks = SelectAudioTracks(options, [media_source for media_source in mp4_sources if not media_source.spec.get('+audio_fallback')])

    # check if this is an audio-only presentation
    audio_only = True
    for media_source in mp4_sources:
        if media_source.has_video:
            audio_only = False
            break

    # check if the video has muxed audio
    video_has_muxed_audio = False
    for media_source in mp4_sources:
        if media_source.has_video and media_source.has_audio:
            video_has_muxed_audio = True
            break

    # audio-only presentations don't need alternate audio tracks
    if audio_only:
        audio_tracks = {}

    # we only need alternate audio tracks if there are more than one or if the audio and video are not muxed
    if video_has_muxed_audio and not audio_only and len(audio_tracks) == 1 and len(list(audio_tracks.values())[0]) == 1:
        audio_tracks = {}

    # process main media sources
    total_duration = 0
    main_media = []
    for media_source in mp4_sources:
        if not audio_only and not media_source.spec.get('+audio_fallback') and not media_source.has_video:
            continue
        media_index = 1+len(main_media)
        media_info = {
            'source':      media_source,
            'dir':         os.path.split(media_source.original_filename)[1]
        }
        if audio_only:
            media_info['video_track_id'] = 0
            if options.audio_format == 'packed':
                source_audio_tracks = media_source.mp4_file.find_tracks_by_type('audio')
                if len(source_audio_tracks):
                    media_info['audio_format']   = options.audio_format
                    if options.audio_format == 'packed':
                        media_info['file_extension'] = ComputeCodecName(source_audio_tracks[0].codec_family)

        # no audio if there's a type filter for video
        if media_source.spec.get('type') == 'video':
            media_info['audio_track_id'] = 0

        # deal with audio-fallback streams
        if media_source.spec.get('+audio_fallback') == 'yes':
            media_info['video_track_id'] = 0

        out_dir = os.path.join(options.output_dir, media_info['dir'])
        MakeNewDir(out_dir)
        ProcessSource(options, media_info, out_dir)

        # update the duration
        duration_s = int(media_info['info']['stats']['duration'])
        if duration_s > total_duration:
            total_duration = duration_s

        main_media.append(media_info)

    # process audio tracks
    if len(audio_tracks):
        MakeNewDir(os.path.join(options.output_dir, 'audio'))
    for group_id in audio_tracks:
        group = audio_tracks[group_id]
        MakeNewDir(os.path.join(options.output_dir, 'audio', group_id))
        for audio_track in group:
            audio_track.media_info = {
                'source':         audio_track.parent.media_source,
                'audio_format':   options.audio_format,
                'dir':            'audio/'+group_id+'/'+audio_track.language,
                'language':       audio_track.language,
                'language_name':  audio_track.language_name,
                'audio_track_id': audio_track.id,
                'video_track_id': 0
            }
            if options.audio_format == 'packed':
                audio_track.media_info['file_extension'] = ComputeCodecName(audio_track.codec_family)

    # start the master playlist
    master_playlist = open(os.path.join(options.output_dir, options.master_playlist_name), 'w', newline='\r\n')
    master_playlist.write('#EXTM3U\n')
    master_playlist.write('# Created with Bento4 mp4-hls.py version '+VERSION+'r'+SDK_REVISION+'\n')

    if options.hls_version >= 4:
        master_playlist.write('\n')
        master_playlist.write('#EXT-X-VERSION:'+str(options.hls_version)+'\n')

    # optional session key
    if options.signal_session_key:
        ext_x_session_key_line = '#EXT-X-SESSION-KEY:METHOD='+options.encryption_mode+',URI="'+options.encryption_key_uri+'"'
        if options.encryption_key_format:
            ext_x_session_key_line += ',KEYFORMAT="'+options.encryption_key_format+'"'
        if options.encryption_key_format_versions:
            ext_x_session_key_line += ',KEYFORMATVERSIONS="'+options.encryption_key_format_versions+'"'
        master_playlist.write(ext_x_session_key_line+'\n')

    # process subtitles sources
    subtitles_files = [SubtitlesFile(options, media_source) for media_source in media_sources if media_source.format in ['ttml', 'webvtt']]
    if len(subtitles_files):
        master_playlist.write('\n')
        master_playlist.write('# Subtitles\n')
        MakeNewDir(os.path.join(options.output_dir, 'subtitles'))
        for subtitles_file in subtitles_files:
            out_dir = os.path.join(options.output_dir, 'subtitles', subtitles_file.language)
            MakeNewDir(out_dir)
            media_filename = os.path.join(out_dir, subtitles_file.media_name)
            shutil.copyfile(subtitles_file.media_source.filename, media_filename)
            relative_url = 'subtitles/'+subtitles_file.language+'/subtitles.m3u8'
            playlist_filename = os.path.join(out_dir, 'subtitles.m3u8')
            CreateSubtitlesPlaylist(playlist_filename, subtitles_file.media_name, total_duration)

            master_playlist.write('#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subtitles",NAME="%s",LANGUAGE="%s",URI="%s"\n' % (subtitles_file.language_name, subtitles_file.language, relative_url))

    # process audio sources
    audio_groups = []
    if len(audio_tracks):
        master_playlist.write('\n')
        master_playlist.write('# Audio\n')
        for group_id in audio_tracks:
            group = audio_tracks[group_id]
            group_name = 'audio_'+group_id
            group_codec = group[0].codec
            default = True
            group_avg_segment_bitrate = 0
            group_max_segment_bitrate = 0
            for audio_track in group:
                avg_segment_bitrate = int(audio_track.media_info['info']['stats']['avg_segment_bitrate'])
                max_segment_bitrate = int(audio_track.media_info['info']['stats']['max_segment_bitrate'])
                if avg_segment_bitrate > group_avg_segment_bitrate:
                    group_avg_segment_bitrate = avg_segment_bitrate
                if max_segment_bitrate > group_max_segment_bitrate:
                    group_max_segment_bitrate = max_segment_bitrate
                extra_info = 'AUTOSELECT=YES,'
                if default:
                    extra_info += 'DEFAULT=YES,'
                    default = False
                master_playlist.write(('#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="%s",NAME="%s",LANGUAGE="%s",%sURI="%s"\n' % (
                                      group_name,
                                      audio_track.media_info['language_name'],
                                      audio_track.media_info['language'],
                                      extra_info,
                                      options.base_url+audio_track.media_info['dir']+'/'+options.media_playlist_name)))
            audio_groups.append({
                'name':                group_name,
                'codec':               group_codec,
                'avg_segment_bitrate': group_avg_segment_bitrate,
                'max_segment_bitrate': group_max_segment_bitrate
            })

        bento4logger.debug('Audio Groups:')
        bento4logger.debug(audio_groups)

    else:
        audio_groups = [{
            'name':                None,
            'codec':               None,
            'avg_segment_bitrate': 0,
            'max_segment_bitrate': 0
        }]

    # media playlists
    master_playlist.write('\n')
    master_playlist.write('# Media Playlists\n')
    for media in main_media:
        media_info = media['info']

        for group_info in audio_groups:
            group_name  = group_info['name']
            group_codec = group_info['codec']

            # stream inf
            codecs = []
            if 'video' in media_info:
                codecs.append(media_info['video']['codec'])
            if 'audio' in media_info:
                codecs.append(media_info['audio']['codec'])
            elif group_name and group_codec:
                codecs.append(group_codec)

            ext_x_stream_inf = '#EXT-X-STREAM-INF:AVERAGE-BANDWIDTH=%d,BANDWIDTH=%d,CODECS="%s"' % (
                                int(media_info['stats']['avg_segment_bitrate'])+group_info['avg_segment_bitrate'],
                                int(media_info['stats']['max_segment_bitrate'])+group_info['max_segment_bitrate'],
                                ','.join(codecs))
            if 'video' in media_info:
                ext_x_stream_inf += ',RESOLUTION='+str(int(media_info['video']['width']))+'x'+str(int(media_info['video']['height']))

            # audio info
            if group_name:
                ext_x_stream_inf += ',AUDIO="'+group_name+'"'

            # subtitles info
            if subtitles_files:
                ext_x_stream_inf += ',SUBTITLES="subtitles"'

            master_playlist.write(ext_x_stream_inf+'\n')
            master_playlist.write(options.base_url+media['dir']+'/'+options.media_playlist_name+'\n')

    # write the I-FRAME playlist info
    if not audio_only and options.hls_version >= 4:
        master_playlist.write('\n')
        master_playlist.write('# I-Frame Playlists\n')
        for media in main_media:
            media_info = media['info']
            if not 'video' in media_info: continue
            ext_x_i_frame_stream_inf = '#EXT-X-I-FRAME-STREAM-INF:AVERAGE-BANDWIDTH=%d,BANDWIDTH=%d,CODECS="%s",RESOLUTION=%dx%d,URI="%s"' % (
                                        int(media_info['stats']['avg_iframe_bitrate']),
                                        int(media_info['stats']['max_iframe_bitrate']),
                                        media_info['video']['codec'],
                                        int(media_info['video']['width']),
                                        int(media_info['video']['height']),
                                        options.base_url+media['dir']+'/'+options.iframe_playlist_name)
            master_playlist.write(ext_x_i_frame_stream_inf+'\n')





