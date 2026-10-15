#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
MultivariantManager is built from a CsmilDescriptor alone: the segment cache
root comes from config, and everything beneath it comes from the descriptor.
(Regression: #54 - renditions were segmented into the segment root, without the
csmil's dirname, because the manager was handed an output_dir of its own.)
"""
import os
from unittest.mock import patch

import pytest

from pathsafety import InvalidPathError
from vodhls.csmil import CsmilDescriptor
from vodhls.master_manifest import MultivariantManager

SEGMENT_ROOT = '/var/cache/casterpak/segments'


@pytest.fixture(autouse=True)
def segment_root_config():
    with patch.object(MultivariantManager, 'config',
                      {'output': {'segmentParentPath': SEGMENT_ROOT}}):
        yield


def make_manager(dirname='casterpak.mp4.transcodes'):
    csmil = CsmilDescriptor(dirname, 'casterpak_', '.mp4', ['360p', '480p', '720p'])
    return MultivariantManager(csmil)


def test_constructor_takes_only_the_csmil():
    with pytest.raises(TypeError):
        MultivariantManager(CsmilDescriptor('d', 'b_', '.mp4', ['360p']), '/some/output_dir')


def test_output_dir_is_segment_root_plus_csmil_dirname():
    assert make_manager().output_dir == f'{SEGMENT_ROOT}/casterpak.mp4.transcodes'


def test_output_dir_for_a_nested_dirname():
    assert make_manager('projects/2024').output_dir == f'{SEGMENT_ROOT}/projects/2024'


def test_flat_file_output_dir_is_the_segment_root():
    assert make_manager('').output_dir == SEGMENT_ROOT


def test_master_playlist_name_does_not_repeat_the_dirname():
    manager = make_manager()
    assert manager.master_playlist_name == 'casterpak_,360p,480p,720p,.mp4.m3u8'
    # the master lands once under the dirname, not <dirname>/<dirname>/...
    assert os.path.join(manager.output_dir, manager.master_playlist_name) == \
        f'{SEGMENT_ROOT}/casterpak.mp4.transcodes/casterpak_,360p,480p,720p,.mp4.m3u8'


def test_rendition_directories_sit_directly_under_output_dir():
    """Bento4 writes each rendition to output_dir/<rendition basename>; that must be
    the same directory MediaManager.output_dir serves it from (<root>/<csmil dirname>/<file>)."""
    manager = make_manager()
    for filename in manager.csmil_data.rendition_filenames:
        served = os.path.join(SEGMENT_ROOT, manager.csmil_data.dirname, filename)
        assert os.path.join(manager.output_dir, filename) == served


@pytest.mark.parametrize('dirname', ['..', '../../etc', '/etc'])
def test_dirname_cannot_escape_the_segment_root(dirname):
    with pytest.raises(InvalidPathError):
        make_manager(dirname).output_dir
