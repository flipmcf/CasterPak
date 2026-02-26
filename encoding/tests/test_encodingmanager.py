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

    def test_get_csmil_url_string(self):
        expected = "test_file_,1080p,720p,480p,360p,240p,.mp4.csmil"
        result = self.manager.get_csmil_url_string()
        self.assertEqual(result, expected)

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

if __name__ == "__main__":
    unittest.main()