import itertools
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from jit import jit_manager_factory
from jit.jit_manager import JitManager
from vodhls import EncodingError


class TestJitManagerFactory(unittest.TestCase):
    def test_factory_returns_configured_jit_manager(self):
        manager = jit_manager_factory(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

        self.assertIsInstance(manager, JitManager)
        self.assertEqual(manager.dir_name, 'videos/video.mp4')
        self.assertEqual(manager.input_filepath, '/in/video.mp4')
        self.assertEqual(manager.output_dir, '/out/dir')
        self.assertEqual(manager.manifest_path, '/out/dir/index_0_av.m3u8')


class TestJitManagerInit(unittest.TestCase):
    def test_derives_segment_paths_from_output_dir(self):
        manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

        self.assertEqual(manager.segment_template, os.path.join('/out/dir', 'segment-%d.ts'))
        self.assertEqual(manager.first_segment_path, os.path.join('/out/dir', 'segment-0.ts'))


class TestGetM3u8IndexUrl(unittest.TestCase):
    def test_builds_url_from_dir_name_and_manifest_filename(self):
        manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

        self.assertEqual(manager.get_m3u8_index_url(), '/i/videos/video.mp4/index_0_av.m3u8')

    def test_url_reflects_actual_manifest_filename_not_a_hardcoded_one(self):
        # If the manifest is ever named something other than index_0_av.m3u8,
        # the URL must follow it rather than silently pointing at a stale name.
        manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/custom_name.m3u8',
        )

        self.assertEqual(manager.get_m3u8_index_url(), '/i/videos/video.mp4/custom_name.m3u8')


class TestJitManagerFirstSegmentExists(unittest.TestCase):
    def setUp(self):
        self.manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

    @patch('jit.jit_manager.os.path.exists')
    def test_true_when_segment_present(self, mock_exists):
        mock_exists.return_value = True
        self.assertTrue(self.manager.first_segment_exists())
        mock_exists.assert_called_once_with(self.manager.first_segment_path)

    @patch('jit.jit_manager.os.path.exists')
    def test_false_when_segment_missing(self, mock_exists):
        mock_exists.return_value = False
        self.assertFalse(self.manager.first_segment_exists())


class TestGetFfmpegCommand(unittest.TestCase):
    def test_get_ffmpeg_command(self):
        manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

        expected = [
            "ffmpeg", "-y", "-i", "/in/video.mp4",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-vf", "scale=-2:480",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "0",
            "-hls_playlist_type", "event",
            "-hls_segment_filename", os.path.join('/out/dir', 'segment-%d.ts'),
            "/out/dir/index_0_av.m3u8",
        ]

        self.assertListEqual(manager.get_ffmpeg_command(), expected)


class TestTriggerJitEncoding(unittest.TestCase):
    def setUp(self):
        self.manager = JitManager(
            dir_name='videos/video.mp4',
            input_filepath='/in/video.mp4',
            output_dir='/out/dir',
            manifest_path='/out/dir/index_0_av.m3u8',
        )

    @patch('jit.jit_manager.subprocess.Popen')
    @patch('jit.jit_manager.os.makedirs')
    @patch.object(JitManager, 'first_segment_exists')
    def test_returns_true_once_first_segment_appears(self, mock_first_segment, mock_makedirs, mock_popen):
        mock_first_segment.return_value = True
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        result = self.manager.trigger_jit_encoding()

        self.assertTrue(result)
        mock_makedirs.assert_called_once_with('/out/dir', exist_ok=True)
        mock_popen.assert_called_once_with(
            self.manager.get_ffmpeg_command(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        mock_process.kill.assert_not_called()

    @patch('jit.jit_manager.time.sleep')
    @patch('jit.jit_manager.time.time')
    @patch('jit.jit_manager.subprocess.Popen')
    @patch('jit.jit_manager.os.makedirs')
    @patch.object(JitManager, 'first_segment_exists')
    def test_polls_again_when_not_ready_but_not_yet_timed_out(
        self, mock_first_segment, mock_makedirs, mock_popen, mock_time, mock_sleep
    ):
        # Not ready on the first check, ready on the second - exercises the
        # "still within timeout, sleep and check again" path.
        mock_first_segment.side_effect = [False, True]
        mock_popen.return_value = MagicMock()
        mock_time.side_effect = itertools.chain([100.0, 101.0], itertools.repeat(101.0))

        result = self.manager.trigger_jit_encoding(timeout=5.0)

        self.assertTrue(result)
        mock_sleep.assert_called_once_with(0.1)

    @patch('jit.jit_manager.time.sleep')
    @patch('jit.jit_manager.time.time')
    @patch('jit.jit_manager.subprocess.Popen')
    @patch('jit.jit_manager.os.makedirs')
    @patch.object(JitManager, 'first_segment_exists')
    def test_raises_encoding_error_and_kills_process_on_timeout(
        self, mock_first_segment, mock_makedirs, mock_popen, mock_time, mock_sleep
    ):
        mock_first_segment.return_value = False
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        # start_time=100.0, next call is already past the 5.0s timeout; repeat
        # the final value so any further time.time() calls (e.g. from logging's
        # own timestamping) don't run the side_effect list dry.
        mock_time.side_effect = itertools.chain([100.0, 106.0], itertools.repeat(106.0))

        with self.assertRaises(EncodingError):
            self.manager.trigger_jit_encoding(timeout=5.0)

        mock_process.kill.assert_called_once()
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
