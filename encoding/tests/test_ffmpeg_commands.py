import os
import unittest
import configparser

from unittest.mock import patch


class TestFFmpegCommands(unittest.TestCase):
    def setUp(self):

        self.input_dir = '/tmp/test_input'
        self.output_dir = '/tmp/test_output'
        self.video_name = 'file.mp4'

        #start the patcher for the 'get_config' function.
        self.patcher = patch('encoding.encodingmanager.get_config')
        self.mock_get_config = self.patcher.start()

        #Mock the config for testing.  This is what get_config() will return.
        self.mock_config = configparser.ConfigParser()

        # 2. Add ONLY the values EncodingManager needs (this helps find unused or new config dependencies)
        self.mock_config.add_section('input')
        self.mock_config.set('input', 'videoCachePath', self.output_dir)
        self.mock_config.add_section('filesystem')
        self.mock_config.set('filesystem', 'videoParentPath', self.input_dir)
               
        # 3. THIS IS THE KEY: Tell the mock function to return the config object
        self.mock_get_config.return_value = self.mock_config
        
        from encoding.encodingmanager import EncodingManager
        self.manager = EncodingManager(
            filename=os.path.join(self.input_dir, self.video_name)
        )

    def tearDown(self):
        self.patcher.stop()
        
    def test_get_ffmpeg_command_default(self):
        self.maxDiff=None
        generated_cmd = self.manager.get_ffmpeg_command()
        expected_output_dir = os.path.join(self.output_dir, f"{self.video_name}.transcodes")

        expected_cmd = ["nice", "-n", "10",
            'ffmpeg', '-y', 
            '-threads', '7',  ## TODO - variable threads in test
            '-i', self.input_dir + '/' + self.video_name,
            '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-s:v', '1920x1080',
            '-b:v', '5000k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-r', '30',
            "-f", "mp4",
            os.path.join(expected_output_dir, 'file_1080p.mp4'),
            '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-s:v', '1280x720',
            '-b:v', '2500k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-r', '30',
            "-f", "mp4",
            os.path.join(expected_output_dir, 'file_720p.mp4'),
            '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-s:v', '854x480',
            '-b:v', '1000k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-r', '30',
            "-f", "mp4",
            os.path.join(expected_output_dir, 'file_480p.mp4'),
            '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-s:v', '640x360',
            '-b:v', '750k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-r', '30',
            "-f", "mp4",
            os.path.join(expected_output_dir, 'file_360p.mp4'),
            '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-s:v', '426x240',
            '-b:v', '400k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-r', '30',
            "-f", "mp4",
            os.path.join(expected_output_dir, 'file_240p.mp4')
        ]
        # I'll assert list equality. This is strict and good.
        self.assertListEqual(generated_cmd, expected_cmd)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestFFmpegCommands))
    return suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner()
    runner.run(suite())
