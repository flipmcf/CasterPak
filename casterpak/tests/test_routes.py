import configparser
import unittest
from flask import Flask, Response
from unittest.mock import patch, MagicMock

# Import the Blueprint from your routes file
from casterpak.routes import bp


def make_test_config():
    """Create a configparser-based config matching the real app's config format."""
    config = configparser.ConfigParser()
    config.read_dict({
        'filesystem': {'videoParentPath': '/tmp/mock_videos'},
        'output': {'serverName': 'localhost', 'use_https': 'false'},
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
        mock_encoder.get_csmil_url_string.return_value = 'test_file_,1080p,720p,.mp4.csmil'
        mock_encoding_manager_class.return_value = mock_encoder

        # Simulate the user requesting the ABR manifest
        response = self.client.get('/i/abr/test_file.mp4/master.m3u8')

        # Assert it returns a 302 Redirect
        self.assertEqual(response.status_code, 302)
        
        # Assert the redirect points to the correct stateless CSMIL URL
        expected_url = '/i/test_file.mp4.transcodes/test_file_,1080p,720p,.mp4.csmil/master.m3u8'
        self.assertEqual(response.location, expected_url)

    @patch('casterpak.routes.trigger_emergency_encoding')
    @patch('casterpak.routes.vodhls_media_playlist_factory')
    @patch('casterpak.routes.EncodingManager')
    def test_abr_manifest_tier_3_emergency(self, mock_encoding_manager_class, mock_playlist_factory, mock_trigger_jit):
        # Mock the manager to say "No, encodings are missing"
        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = False
        mock_encoding_manager_class.return_value = mock_encoder

        # Mock the HLS factory so it doesn't try to read real files
        mock_hls_manager = MagicMock()
        mock_hls_manager.source_file = '/tmp/mock_videos/test_file.mp4'
        mock_hls_manager.output_dir = '/tmp/mock_output'
        mock_hls_manager.output_manifest_filename = '/tmp/mock_output/index_0_av.m3u8'
        mock_playlist_factory.return_value = mock_hls_manager

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
        
        # 2. Did it start the lightweight JIT emergency stream?
        mock_trigger_jit.assert_called_once_with(
            input_filepath=mock_hls_manager.source_file,
            output_dir=mock_hls_manager.output_dir,
            manifest_path=mock_hls_manager.output_manifest_filename
        )

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
        files_arg, dir_arg = args[0], args[1]
        self.assertEqual(dir_arg, 'mydir')
        self.assertIn('mydir/test-video_720.mp4', files_arg)
        self.assertIn('mydir/test-video_480.mp4', files_arg)

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
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            response = self.client.get('/i/foo/bar/baz/clip_,1080,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 200)
        args = mock_factory.call_args[0]
        files_arg, dir_arg = args[0], args[1]
        self.assertEqual(dir_arg, 'foo/bar/baz')
        self.assertEqual(len(files_arg), 3)


if __name__ == "__main__":
    unittest.main()
