#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""create_app logs the whole config at startup. Credentials must not be in it."""
import configparser

from casterpak import printable_config


def test_secret_looking_options_are_masked_and_the_rest_is_kept():
    cfg = configparser.ConfigParser()
    cfg['s3'] = {
        'bucket': 'my-videos', 'access_key_id': 'AKIAEXAMPLE1234',
        'secret_access_key': 'wJalrXUtnFEMI/K7MDENG', 'endpoint_url': '',
    }
    cfg['library'] = {'jwt_secret': 'hunter2hunter2', 'registration_code': 'open-sesame'}

    out = printable_config(cfg)

    for leaked in ('AKIAEXAMPLE1234', 'wJalrXUtnFEMI', 'hunter2hunter2', 'open-sesame'):
        assert leaked not in out
    assert 'my-videos' in out          # ordinary options still print
    assert '********' in out


def test_empty_secrets_are_not_masked_so_a_blank_is_visibly_blank():
    cfg = configparser.ConfigParser()
    cfg['s3'] = {'secret_access_key': ''}
    assert '********' not in printable_config(cfg)
