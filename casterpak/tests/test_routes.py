import configparser
import unittest
from flask import Flask, Response
from unittest.mock import patch, MagicMock

# Import the Blueprint from your routes file
from casterpak.routes import bp, get_base_url


def make_test_config():
    """Create a configparser-based config matching the real app's config format."""
    config = configparser.ConfigParser()
    config.read_dict({
        'filesystem': {'videoParentPath': '/tmp/mock_videos'},
        'output': {'serverName': 'localhost', 'use_https': 'false', 'segmentParentPath': '/tmp/mock_segments'},
    })
    return config

class TestABRRoute(unittest.TestCase):
    def setUp(self):
        # Create a blank Flask app and register your routing blueprint
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)

        # Inject configparser-based config matching the real app's format
        config = make_test_config()
        self.app.config['filesystem'] = config['filesystem']
        self.app.config['output'] = config['output']
        
        # The test_client allows us to send simulated HTTP requests
        self.client = self.app.test_client()
        
        # Push an app context so things like 'current_app.logger' work correctly
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    @patch('casterpak.routes.EncodingManager')
    def test_abr_manifest_tier_2_redirect(self, mock_encoding_manager_class):
        # Mock the manager to say "Yes, encodings are finished"
        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = True
        mock_encoder.in_progress.return_value = False
        mock_encoder.bitrates = ['1080p', '720p']
        mock_encoding_manager_class.return_value = mock_encoder

        # Simulate the user requesting the ABR manifest
        response = self.client.get('/i/abr/test_file.mp4/master.m3u8')

        # Assert it returns a 302 Redirect
        self.assertEqual(response.status_code, 302)
        
        # Assert the redirect points to the correct stateless CSMIL URL
        expected_url = '/i/test_file.mp4.transcodes/test_file,1080p,720p,.mp4.csmil/master.m3u8'
        self.assertEqual(response.location, expected_url)

    @patch('casterpak.routes.jit_manager_factory')
    @patch('casterpak.routes.vodhls_media_playlist_factory')
    @patch('casterpak.routes.EncodingManager')
    def test_abr_leading_dash(self, mock_encoding_manager_class, mock_playlist_factory, mock_jit_manager_factory):
        """Tests weather a filename with a leading dash will trick ffmpeg into seeing an argument rather than a filename
        """
        # Mock the manager to say "Yes, encodings are finished"
        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = True
        mock_encoder.bitrates = ['1080p', '720p']
        mock_encoding_manager_class.return_value = mock_encoder

        # Simulate the user requesting the ABR manifest
        response = self.client.get('/i/abr/-test_file.mp4/master.m3u8')

        assert response.status_code == 422


    @patch('casterpak.routes.jit_manager_factory')
    @patch('casterpak.routes.vodhls_media_playlist_factory')
    @patch('casterpak.routes.EncodingManager')
    def test_abr_manifest_tier_3_emergency(self, mock_encoding_manager_class, mock_playlist_factory, mock_jit_manager_factory):
        # Mock the manager to say "No, encodings are missing, and none are in progress"
        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = False
        mock_encoder.in_progress.return_value = False
        mock_encoding_manager_class.return_value = mock_encoder

        # Mock the HLS factory so it doesn't try to read real files
        mock_hls_manager = MagicMock()
        mock_hls_manager.source_file = '/tmp/mock_videos/test_file.mp4'
        mock_hls_manager.output_dir = '/tmp/mock_output'
        mock_hls_manager.output_manifest_filename = '/tmp/mock_output/index_0_av.m3u8'
        mock_playlist_factory.return_value = mock_hls_manager

        # Mock the JIT manager so it doesn't try to spawn real ffmpeg
        mock_jit_manager = MagicMock()
        mock_jit_manager.first_segment_exists.return_value = False
        mock_jit_manager.get_m3u8_index_url.return_value = '/i/test_file.mp4/index_0_av.m3u8'
        mock_jit_manager_factory.return_value = mock_jit_manager

        # Simulate the user requesting the ABR manifest
        response = self.client.get('/i/abr/test_file.mp4/master.m3u8')

        # Assert it returns a 200 OK
        self.assertEqual(response.status_code, 200)

        # Assert the response body contains a valid HLS manifest pointing to the single stream
        self.assertIn(b'#EXTM3U', response.data)
        self.assertIn(b'index_0_av.m3u8', response.data)

        # VERIFY GATEKEEPER LOGIC:
        # 1. Did it start the heavy background worker?
        mock_encoder.start_background_encoding.assert_called_once()

        # 2. Did it build a JIT manager for this video, and start the lightweight JIT emergency stream?
        mock_jit_manager_factory.assert_called_once_with(
            dir_name='test_file.mp4',
            input_filepath=mock_hls_manager.source_file,
            output_dir=mock_hls_manager.output_dir,
            manifest_path=mock_hls_manager.output_manifest_filename
        )
        mock_jit_manager.trigger_jit_encoding.assert_called_once()

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    @patch('casterpak.routes.EncodingManager')
    def test_abr_redirect_and_csmil_preserve_special_characters_in_filename(
        self, mock_encoding_manager_class, mock_csmil_factory, mock_cachedb
    ):
        """
        Regression test for the filename-sanitization divergence bug: a filename
        containing a character `filenameRE` strips (here, '+') must produce a
        CSMIL redirect - and everything parsed from it - that still matches the
        exact identity EncodingManager was built from, not a silently-mangled
        copy that points at a directory nothing ever wrote to.

        This exercises TWO independent copies of the same sanitization regex:
        the one in casterpak/routes.py (abr_manifest) and the one in
        vodhls/csmil.py (CsmilDescriptor.from_string) - see the '## TODO - this
        is duplicated' comment at the top of routes.py. Both have to preserve
        '+' for this to pass; fixing only one isn't enough.
        """
        dir_name = 'test+plus+in+filename.mp4'

        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = True
        mock_encoder.in_progress.return_value = False
        mock_encoder.bitrates = ['720p', '480p']
        mock_encoding_manager_class.return_value = mock_encoder

        # 1. Hit the ABR route - this is where the divergence happens today.
        response = self.client.get(f'/i/abr/{dir_name}/master.m3u8')
        self.assertEqual(response.status_code, 302)

        redirect_location = response.location

        # The redirect must point at the SAME file identity EncodingManager was
        # constructed with - i.e. it must still contain the '+' characters, not
        # a stripped copy that doesn't match anything EncodingManager wrote.
        self.assertIn('test+plus+in+filename', redirect_location)
        self.assertNotIn('testplusinfilename', redirect_location)

        # 2. Follow the redirect into the CSMIL route, and inspect the REAL
        #    CsmilDescriptor it parses from that URL (mocking only the manifest
        #    generation/serving, same pattern as TestCsmilRoute below).
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_csmil_factory.return_value = mock_manager

        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            csmil_response = self.client.get(redirect_location)

        self.assertEqual(csmil_response.status_code, 200)

        # The CsmilDescriptor that csmil_parent_manifest actually parsed from
        # the URL - not a mock - must still carry the '+' in both the
        # directory and every rendition filename.
        csmil_data = mock_csmil_factory.call_args[0][0]
        self.assertIn('+', csmil_data.dirname)
        self.assertTrue(csmil_data.rendition_filenames, "no rendition filenames parsed")
        for rendition_filename in csmil_data.rendition_filenames:
            self.assertIn('+', rendition_filename)

        # 3. The child-manifest URL a client would actually fetch for each
        #    rendition must resolve back to the same '+'-containing directory
        #    EncodingManager wrote to - i.e. it would hit something real on
        #    disk, not 404 like the mismatched version does today.
        base_url = get_base_url(csmil_data.dirname)
        for rendition_filename in csmil_data.rendition_filenames:
            child_manifest_url = f"{base_url}{rendition_filename}/index_0_av.m3u8"
            self.assertIn('test+plus+in+filename', child_manifest_url)


class TestCsmilRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)

        config = make_test_config()
        self.app.config['filesystem'] = config['filesystem']
        self.app.config['output'] = config['output']

        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_csmil_manifest_cache_hit(self, mock_factory, mock_cachedb):
        """When the manifest already exists on disk, serve it directly without re-encoding."""
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        with patch('casterpak.routes.send_from_directory', return_value=Response('cached manifest')) as mock_send:
            response = self.client.get('/i/mydir/test-video_,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 200)

        # Factory should have been called with the correct parsed files and directory
        mock_factory.assert_called_once()
        args = mock_factory.call_args[0]
        csmil_arg = args[0]
        self.assertEqual(csmil_arg.dirname, 'mydir')
        self.assertEqual(len(csmil_arg.rendition_filenames), 2)

        # Should NOT have called output_hls since manifest already exists
        mock_manager.output_hls.assert_not_called()

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_csmil_manifest_cache_miss(self, mock_factory, mock_cachedb):
        """When the manifest does not exist, generate it and register segments in the cache db."""
        mock_segment_manager = MagicMock()
        mock_segment_manager.filename = 'test-video_720.mp4'

        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = False
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_manager.segment_managers = [
            {'status': 'ready', 'segment_manager': mock_segment_manager},
        ]
        mock_factory.return_value = mock_manager

        mock_db_instance = MagicMock()
        mock_cachedb.CacheDB.return_value = mock_db_instance

        with patch('casterpak.routes.send_from_directory', return_value=Response('new manifest')):
            response = self.client.get('/i/mydir/test-video_,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 200)

        # Should have generated the manifest
        mock_manager.set_baseurl.assert_called_once()
        mock_manager.output_hls.assert_called_once()

        # Should have registered the ready segment in the cache
        mock_cachedb.CacheDB.assert_called()
        mock_db_instance.addrecord.assert_called_with(filename='test-video_720.mp4')

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_csmil_manifest_cache_miss_skips_not_ready_segments(self, mock_factory, mock_cachedb):
        """Segments that are not 'ready' should not be registered in the cache."""
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = False
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_manager.segment_managers = [
            {'status': 'pending', 'segment_manager': MagicMock()},
        ]
        mock_factory.return_value = mock_manager

        mock_db_instance = MagicMock()
        mock_cachedb.CacheDB.return_value = mock_db_instance

        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            response = self.client.get('/i/mydir/test-video_,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 200)
        mock_db_instance.addrecord.assert_not_called()

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_csmil_manifest_file_not_found(self, mock_factory, mock_cachedb):
        """When the source video is missing, return 404."""
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = False
        mock_manager.output_hls.side_effect = FileNotFoundError
        mock_factory.return_value = mock_manager

        response = self.client.get('/i/mydir/test-video_,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 404)

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_csmil_deep_path(self, mock_factory, mock_cachedb):
        """Test that deeply nested directory paths are parsed correctly."""

        #mock a situation where the files appear to be in the cache, and we get a parent / master manifest
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        #send a url '/i/foo/bar/baz/clip_,1080,720,480,.mp4.csmil/master.m3u8' to flask.
        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            response = self.client.get('/i/foo/bar/baz/clip_,1080,720,480,.mp4.csmil/master.m3u8')

        #expect a 200 reply
        self.assertEqual(response.status_code, 200)

        #make sure args were passed correctly - should be a CsmilDescriptor
        args = mock_factory.call_args[0]
        csmil_arg = args[0]
        self.assertEqual(csmil_arg.dirname, 'foo/bar/baz')
        self.assertEqual(len(csmil_arg.rendition_filenames), 3)


class TestSingleBitrateRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)

        config = make_test_config()
        self.app.config['filesystem'] = config['filesystem']
        self.app.config['output'] = config['output']

        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_missing_source_file_returns_404_not_500(self):
        """
        Deliberately does NOT mock vodhls_master_playlist_factory. The bug this is
        meant to catch lives inside how single_bitrate_manifest builds its
        CsmilDescriptor and inside MultivariantManager itself -- mocking the factory
        away (like the other route tests do) hides exactly this class of bug.

        A request for a source file that doesn't exist should fail gracefully with
        404, not crash with an unhandled exception (500).
        """
        response = self.client.get('/i/nonexistent_dir/nonexistent_video.mp4/master.m3u8')
        self.assertEqual(response.status_code, 404)

    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_single_bitrate_manifest_cache_hit(self, mock_factory):
        """When the manifest already exists on disk, serve it directly without
        re-encoding -- and verify the CsmilDescriptor built for a single-bitrate
        request is the one-unlabeled-rendition shape, not a multi-bitrate CSMIL."""
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            response = self.client.get('/i/mydir/test-video.mp4/master.m3u8')

        self.assertEqual(response.status_code, 200)

        mock_factory.assert_called_once()
        csmil_arg = mock_factory.call_args[0][0]
        self.assertEqual(csmil_arg.dirname, 'mydir')
        self.assertEqual(csmil_arg.basename, 'test-video')
        self.assertEqual(csmil_arg.ext, '.mp4')
        self.assertEqual(csmil_arg.bitrates, [''])
        self.assertEqual(csmil_arg.rendition_filenames, ['test-video.mp4'])

        # Should NOT have called output_hls since manifest already exists
        mock_manager.output_hls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
