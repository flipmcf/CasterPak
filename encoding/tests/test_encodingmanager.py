import os
import unittest
import configparser
from unittest.mock import patch

from encoding.encodingmanager import EncodingManager

class TestEncodingManagerMethods(unittest.TestCase):
    def setUp(self):
        self.input_dir = '/tmp/test_input'
        self.output_dir = '/tmp/test_output'
        self.video_name = 'test_file.mp4'

        # Mock the config
        self.patcher = patch('encoding.encodingmanager.get_config')
        self.mock_get_config = self.patcher.start()

        self.mock_config = configparser.ConfigParser()
        self.mock_config.add_section('input')
        self.mock_config.set('input', 'videoCachePath', self.output_dir)
        self.mock_config.add_section('filesystem')
        self.mock_config.set('filesystem', 'videoParentPath', self.input_dir)
        self.mock_get_config.return_value = self.mock_config
        
        self.manager = EncodingManager(
            filename=os.path.join(self.input_dir, self.video_name)
        )

    def tearDown(self):
        self.patcher.stop()

    @patch.object(EncodingManager, '_all_exist')
    def test_renditions_exist(self, mock_all_exist):
        mock_all_exist.return_value = True
        self.assertTrue(self.manager.renditions_exist())
        mock_all_exist.assert_called_once()

    @patch.object(EncodingManager, '_trigger_encoding')
    @patch.object(EncodingManager, '_ensure_transcode_dir')
    @patch.object(EncodingManager, 'renditions_exist')
    def test_start_background_encoding_when_missing(self, mock_renditions_exist, mock_ensure_dir, mock_trigger):
        # If renditions don't exist, it should trigger the encoding
        mock_renditions_exist.return_value = False
        
        self.manager.start_background_encoding()
        
        mock_ensure_dir.assert_called_once()
        mock_trigger.assert_called_once()

    @patch.object(EncodingManager, '_trigger_encoding')
    @patch.object(EncodingManager, '_ensure_transcode_dir')
    @patch.object(EncodingManager, 'renditions_exist')
    def test_start_background_encoding_when_exists(self, mock_renditions_exist, mock_ensure_dir, mock_trigger):
        # If renditions DO exist, it should gracefully skip the trigger
        mock_renditions_exist.return_value = True
        
        self.manager.start_background_encoding()
        
        mock_ensure_dir.assert_called_once()
        mock_trigger.assert_not_called()

    @patch('encoding.encodingmanager.get_config')
    def test_custom_encoding_ladder_labels(self, mock_get_config):
        """
        Prove that EncodingManager respects custom labels like 'high', 'medium', 'low'
        instead of defaulting to the standard '1080p', '720p' format.
        """
        # 1. Build a custom ConfigParser object
        custom_config = configparser.ConfigParser()
        custom_config.add_section('input')
        custom_config.set('input', 'videoCachePath', '/tmp/test_output')
        
        # 2. Add the custom ladder!
        custom_config.add_section('encoding_ladder')
        custom_config.set('encoding_ladder', 'high', '1920x1080, 5000k')
        custom_config.set('encoding_ladder', 'medium', '1280x720, 2500k')
        custom_config.set('encoding_ladder', 'low', '426x240, 400k')
        
        # 3. Tell get_config() to return our custom config
        mock_get_config.return_value = custom_config
        
        # 4. Instantiate the manager and check the generated filenames
        manager = EncodingManager('/tmp/test_input/test_video.mp4')
        
        files = manager.list_rendition_files()
        
        # Assert the manager generated exact filenames matching our custom labels
        self.assertIn('/tmp/test_output/test_video.mp4.transcodes/test_video_high.mp4', files)
        self.assertIn('/tmp/test_output/test_video.mp4.transcodes/test_video_medium.mp4', files)
        self.assertIn('/tmp/test_output/test_video.mp4.transcodes/test_video_low.mp4', files)
        
        # Assert it completely ignored the fallback defaults
        self.assertEqual(len(files), 3)


if __name__ == "__main__":
    unittest.main()