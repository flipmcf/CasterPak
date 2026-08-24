import unittest
from flask import Flask
from unittest.mock import patch, MagicMock

# Import the Blueprint from your routes file
from casterpak.routes import bp

class TestABRRoute(unittest.TestCase):
    def setUp(self):
        # Create a blank Flask app and register your routing blueprint
        self.app = Flask(__name__)
        self.app.register_blueprint(bp)
        
        # Inject the mock config required by the route logic
        self.app.config['filesystem'] = {'videoParentPath': '/tmp/mock_videos'}
        self.app.config['output'] = {'serverName': 'localhost', 'use_https': False}
        
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
        mock_encoder.bitrates = ['1080p', '720p']
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

if __name__ == "__main__":
    unittest.main()
