import os
import unittest
import configparser
from unittest.mock import patch

from encoding.encodingmanager import EncodingManager
from encoding import EncodingAlreadyInProgressError

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
    @patch.object(EncodingManager, 'in_progress')
    def test_renditions_exist(self, mock_in_progress, mock_all_exist):
        # in_progress() is EncodingManager's own concern for renditions_exist()'s
        # wiring here - it's tested against the real encoding_process_manager
        # separately (see test_encoding_process_manager.py), so it's mocked out
        # here rather than hitting the real queue db.
        mock_in_progress.return_value = False
        mock_all_exist.return_value = True
        self.assertTrue(self.manager.renditions_exist())
        mock_all_exist.assert_called_once()

    @patch.object(EncodingManager, '_ensure_transcode_dir')
    @patch.object(EncodingManager, 'queue_encoding_job')
    @patch('os.path.exists', return_value=True)
    def test_queue_background_encoding_claims_lock_and_creates_dir(
            self, mock_exists, mock_queue_encoding_job, mock_ensure_dir):
        # Happy path: builds the command, claims the lock with it, and
        # only then ensures the transcode dir exists. It does NOT spawn
        # anything itself anymore - that's encoding_process_manager's
        # dispatcher's job.
        self.manager.queue_background_encoding()

        mock_queue_encoding_job.assert_called_once()
        (command,), _ = mock_queue_encoding_job.call_args
        self.assertEqual(command, self.manager.get_ffmpeg_command())
        mock_ensure_dir.assert_called_once()

    @patch.object(EncodingManager, '_ensure_transcode_dir')
    @patch.object(EncodingManager, 'queue_encoding_job')
    @patch('os.path.exists', return_value=True)
    def test_queue_background_encoding_already_in_progress(
            self, mock_exists, mock_queue_encoding_job, mock_ensure_dir):
        # If queue_encoding_job says it's already claimed, that error should
        # propagate to the caller (routes.py catches it), and no
        # transcode dir should be created for a job we didn't win.
        mock_queue_encoding_job.side_effect = EncodingAlreadyInProgressError()

        with self.assertRaises(EncodingAlreadyInProgressError):
            self.manager.queue_background_encoding()

        mock_ensure_dir.assert_not_called()

    @patch('os.path.exists', return_value=False)
    def test_queue_background_encoding_missing_source_file(self, mock_exists):
        with self.assertRaises(FileNotFoundError):
            self.manager.queue_background_encoding()

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