#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import pytest

from library import create_app
from library.settings import load_settings
from vodhls import ConfigurationError

from library.tests.conftest import make_config


def test_defaults(tmp_path):
    s = load_settings(make_config(tmp_path))
    assert s.registration == 'open'
    assert s.abr_supported is True                  # filesystem library: CasterPak can auto-encode
    assert s.casterpak_url == 'https://video.example.test'


def test_default_registration_is_closed(tmp_path):
    cfg = make_config(tmp_path)
    del cfg['library']['registration']
    assert load_settings(cfg).registration == 'closed'


@pytest.mark.parametrize('secret', ['', 'short', 'x' * 31])
def test_refuses_to_start_without_a_strong_jwt_secret(tmp_path, secret):
    with pytest.raises(ConfigurationError, match='jwt_secret'):
        create_app(make_config(tmp_path, jwt_secret=secret))


def test_invite_mode_needs_a_real_code(tmp_path):
    with pytest.raises(ConfigurationError, match='registration_code'):
        load_settings(make_config(tmp_path, registration='invite', registration_code='abc'))


def test_bad_registration_mode(tmp_path):
    with pytest.raises(ConfigurationError):
        load_settings(make_config(tmp_path, registration='sometimes'))


def test_library_writes_where_casterpak_reads_or_not_at_all(tmp_path):
    cfg = make_config(tmp_path)
    cfg['input']['input_type'] = 'http'
    with pytest.raises(ConfigurationError, match='not writable'):
        load_settings(cfg)


def test_s3_library_needs_a_bucket(tmp_path):
    cfg = make_config(tmp_path)
    cfg['input']['input_type'] = 's3'
    cfg['s3'] = {'bucket': ''}
    with pytest.raises(ConfigurationError, match='bucket'):
        load_settings(cfg)


def test_abr_is_not_offered_for_an_s3_library_by_default(tmp_path):
    cfg = make_config(tmp_path)
    cfg['input']['input_type'] = 's3'
    cfg['s3'] = {'bucket': 'b'}
    s = load_settings(cfg)
    assert s.abr_supported is False
    cfg['library']['abr'] = 'true'
    assert load_settings(cfg).abr_supported is True
