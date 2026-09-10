#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Security-focused integration tests for every route in casterpak/routes.py
that accepts a URL-supplied filename or directory path.

Written from an attacker's point of view: each route is hit with path
traversal, argument-injection (leading '-'), CSMIL-delimiter injection
(','), shell metacharacters, null bytes, and other malformed input, and
must reject all of it (422) rather than reach anything downstream.
Alongside that, a smaller set of positive tests confirms legitimate names
(including '+', which shows up in real uploaded content) still work.

This is the one place these rules are pinned end-to-end. The rules
themselves live in pathsafety.py; Readme.md's "Valid Filenames" section is
the human-readable version - keep all three in sync.

Attack payloads never reach a mock: casterpak's own validation
(pathsafety.validate_filename/validate_dirname, and vodhls/csmil.py's use
of the same) rejects them with abort(422) before EncodingManager, the
vodhls factories, JitManager, or Flask's send_file/send_from_directory are
ever touched - so those tests need no mocking at all. Only the positive
tests, which exercise the real success path, mock those out (same pattern
as casterpak/tests/test_routes.py).
"""

import configparser
import unittest
from flask import Flask, Response
from unittest.mock import patch, MagicMock

from casterpak.routes import bp
from pathsafety import validate_filename, validate_dirname, InvalidPathError


def make_test_config():
    """Create a configparser-based config matching the real app's config format."""
    config = configparser.ConfigParser()
    config.read_dict({
        'filesystem': {'videoParentPath': '/tmp/mock_videos'},
        'output': {'serverName': 'localhost', 'use_https': 'false', 'segmentParentPath': '/tmp/mock_segments'},
    })
    return config


# --- Attack payloads, shared across every route under test -----------------

TRAVERSAL_PAYLOADS = [
    '../../../etc/passwd',
    'foo/../../bar',
    '..',
    '....//....//etc/passwd',   # doubled-dot-slash: still splits to '..' segments
]

LEADING_DASH_PAYLOADS = [
    '-rf',
    '--output=/etc/cron.d/evil',
    '-oProxyCommand=whoami',
]

DELIMITER_INJECTION_PAYLOADS = [
    'evil,720,480',
]

SHELL_METACHAR_PAYLOADS = [
    'evil;rm -rf all',
    'evil`whoami`',
    'evil$(whoami)',
    'evil|whoami',
    'evil&&whoami',
    "evil'whoami",
    'evil"whoami',
    'evil<whoami',
    'evil>whoami',
    'evil{whoami}',
    'evil*whoami',
    'evil whoami',        # a literal space
]

NULL_BYTE_PAYLOADS = [
    'evil\x00.mp4',
]


class SecurityTestCase(unittest.TestCase):
    """Shared Flask app/client setup for every route under test."""

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

    def assert_rejected(self, path, msg_prefix=""):
        """A malicious path must come back 422 - never 200, and never a 500
        (a 500 would mean it got PAST validation and crashed something
        downstream instead, which is worse: it means attacker input reached
        real logic)."""
        response = self.client.get(path)
        self.assertEqual(
            response.status_code, 422,
            f"{msg_prefix}expected 422 for {path!r}, got {response.status_code}"
        )


# --- pathsafety.py itself, directly -----------------------------------------

class TestPathsafetyDirectly(unittest.TestCase):
    """Unit-level coverage of the validator itself, including cases (like a
    raw null byte) that are awkward or impossible to route through an actual
    HTTP request."""

    def test_rejects_traversal_segments(self):
        for payload in ('.', '..'):
            with self.subTest(payload=payload):
                with self.assertRaises(InvalidPathError):
                    validate_filename(payload)

    def test_rejects_leading_dash(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                with self.assertRaises(InvalidPathError):
                    validate_filename(payload)

    def test_rejects_comma(self):
        with self.assertRaises(InvalidPathError):
            validate_filename('evil,720')

    def test_rejects_empty_segment(self):
        with self.assertRaises(InvalidPathError):
            validate_filename('')

    def test_dirname_rejects_traversal_via_split_segments(self):
        with self.assertRaises(InvalidPathError):
            validate_dirname('foo/../bar')

    def test_dirname_rejects_leading_slash_via_empty_segment(self):
        # '/etc/passwd'.split('/') == ['', 'etc', 'passwd'] - the leading
        # empty segment is what actually closes this off, not a '/'
        # special-case (see pathsafety.py's docstring).
        with self.assertRaises(InvalidPathError):
            validate_dirname('/etc/passwd')

    def test_dirname_rejects_doubled_slash_via_empty_segment(self):
        with self.assertRaises(InvalidPathError):
            validate_dirname('foo//bar')

    def test_rejects_null_byte(self):
        with self.assertRaises(InvalidPathError):
            validate_filename('evil\x00.mp4')

    def test_accepts_plus_and_multiple_dots(self):
        self.assertEqual(validate_filename('test+plus+file.tar.gz'), 'test+plus+file.tar.gz')

    def test_accepts_nonleading_hyphen_and_underscore(self):
        self.assertEqual(validate_filename('my-video_final.mp4'), 'my-video_final.mp4')

    def test_empty_dirname_is_valid(self):
        # top-level, no subdirectory
        self.assertEqual(validate_dirname(''), '')


# --- single_bitrate_manifest -------------------------------------------------

class TestSingleBitrateManifestSecurity(SecurityTestCase):
    def test_rejects_path_traversal(self):
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/master.m3u8')

    def test_rejects_leading_dash(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/master.m3u8')

    def test_rejects_shell_metacharacters(self):
        for payload in SHELL_METACHAR_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/master.m3u8')

    def test_rejects_comma(self):
        for payload in DELIMITER_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/master.m3u8')

    @patch('casterpak.routes.send_from_directory', return_value=Response('manifest'))
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_accepts_plus_in_filename(self, mock_factory, mock_send):
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        response = self.client.get('/i/test+plus+file.mp4/master.m3u8')
        self.assertEqual(response.status_code, 200)


# --- abr_manifest -------------------------------------------------------------

class TestAbrManifestSecurity(SecurityTestCase):
    def test_rejects_path_traversal(self):
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/abr/{payload}/master.m3u8')

    def test_rejects_leading_dash(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/abr/{payload}/master.m3u8')

    def test_rejects_shell_metacharacters(self):
        for payload in SHELL_METACHAR_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/abr/{payload}/master.m3u8')

    def test_rejects_comma(self):
        for payload in DELIMITER_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/abr/{payload}/master.m3u8')

    @patch('casterpak.routes.EncodingManager')
    def test_accepts_plus_and_redirects(self, mock_encoding_manager_class):
        mock_encoder = MagicMock()
        mock_encoder.renditions_exist.return_value = True
        mock_encoder.in_progress.return_value = False
        mock_encoder.bitrates = ['720p']
        mock_encoding_manager_class.return_value = mock_encoder

        response = self.client.get('/i/abr/test+plus+file.mp4/master.m3u8')
        self.assertEqual(response.status_code, 302)
        self.assertIn('test+plus+file', response.location)


# --- csmil_parent_manifest -----------------------------------------------------

class TestCsmilParentManifestSecurity(SecurityTestCase):
    def test_rejects_path_traversal_in_basename(self):
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload},720,480,.mp4.csmil/master.m3u8')

    def test_rejects_path_traversal_in_directory(self):
        # payload as its own '/'-delimited directory segment, ahead of the
        # basename - the actual shape a traversal attempt would take here.
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/somefile,720,480,.mp4.csmil/master.m3u8')

    def test_rejects_leading_dash_in_basename(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload},720,480,.mp4.csmil/master.m3u8')

    def test_rejects_shell_metacharacters(self):
        for payload in SHELL_METACHAR_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload},720,480,.mp4.csmil/master.m3u8')

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.vodhls_master_playlist_factory')
    def test_accepts_plus_in_basename(self, mock_factory, mock_cachedb):
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_dir = '/tmp/mock_output'
        mock_manager.master_playlist_name = 'master.m3u8'
        mock_factory.return_value = mock_manager

        with patch('casterpak.routes.send_from_directory', return_value=Response('manifest')):
            response = self.client.get('/i/test+plus,720,480,.mp4.csmil/master.m3u8')

        self.assertEqual(response.status_code, 200)
        csmil_data = mock_factory.call_args[0][0]
        self.assertEqual(csmil_data.basename, 'test+plus')


# --- child_manifest -------------------------------------------------------------

class TestChildManifestSecurity(SecurityTestCase):
    def test_rejects_path_traversal(self):
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/index_0_av.m3u8')

    def test_rejects_leading_dash(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/index_0_av.m3u8')

    def test_rejects_shell_metacharacters(self):
        for payload in SHELL_METACHAR_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/index_0_av.m3u8')

    def test_rejects_comma(self):
        for payload in DELIMITER_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/index_0_av.m3u8')

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.send_file', return_value=Response('manifest'))
    @patch('casterpak.routes.vodhls_media_playlist_factory')
    def test_accepts_plus_in_filename(self, mock_factory, mock_send_file, mock_cachedb):
        mock_manager = MagicMock()
        mock_manager.manifest_exists.return_value = True
        mock_manager.output_manifest_filename = '/tmp/mock_output/index_0_av.m3u8'
        mock_factory.return_value = mock_manager

        response = self.client.get('/i/test+plus+file.mp4/index_0_av.m3u8')
        self.assertEqual(response.status_code, 200)


# --- segment ----------------------------------------------------------------------

class TestSegmentSecurity(SecurityTestCase):
    def test_rejects_path_traversal_in_dirname(self):
        for payload in TRAVERSAL_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/segment-0.ts')

    def test_rejects_leading_dash_in_dirname(self):
        for payload in LEADING_DASH_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/segment-0.ts')

    def test_rejects_shell_metacharacters(self):
        for payload in SHELL_METACHAR_PAYLOADS:
            with self.subTest(payload=payload):
                self.assert_rejected(f'/i/{payload}/segment-0.ts')

    @patch('casterpak.routes.cachedb')
    @patch('casterpak.routes.send_from_directory', return_value=Response('segment data'))
    @patch('casterpak.routes.vodhls_media_playlist_factory')
    def test_accepts_plus_in_dirname(self, mock_factory, mock_send, mock_cachedb):
        mock_manager = MagicMock()
        mock_manager.segment_exists.return_value = True
        mock_factory.return_value = mock_manager

        response = self.client.get('/i/test+plus+dir.mp4/segment-0.ts')
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
