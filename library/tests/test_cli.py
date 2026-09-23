#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
from library import create_app
from library.tests.conftest import PASSWORD, login, make_config


def test_admin_can_create_users_even_when_registration_is_closed(tmp_path):
    app = create_app(make_config(tmp_path, registration='closed'))
    runner = app.test_cli_runner()

    result = runner.invoke(args=['create-user', 'carol', '--email', 'carol@example.com', '--password', PASSWORD])
    assert result.exit_code == 0, result.output
    assert "created user 'carol'" in result.output
    assert (tmp_path / 'library_root' / 'carol').is_dir()
    assert login(app.test_client(), 'carol').status_code == 200

    listing = runner.invoke(args=['list-users'])
    assert 'carol' in listing.output and 'active' in listing.output


def test_cli_applies_the_same_rules_as_the_api(tmp_path):
    runner = create_app(make_config(tmp_path)).test_cli_runner()
    bad_name = runner.invoke(args=['create-user', 'abr', '--password', PASSWORD])
    assert bad_name.exit_code != 0 and 'reserved' in bad_name.output
    weak = runner.invoke(args=['create-user', 'dave', '--password', 'short'])
    assert weak.exit_code != 0 and 'at least' in weak.output
    assert runner.invoke(args=['create-user', 'erin', '--password', PASSWORD]).exit_code == 0
    assert runner.invoke(args=['create-user', 'erin', '--password', PASSWORD]).exit_code != 0
