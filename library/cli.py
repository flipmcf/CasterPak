#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""Administrator commands. With [library] registration = closed (the default)
this is how accounts are made:

    flask --app library create-user alice --email alice@example.com
"""
import click

from library.auth import Conflict, create_user
from library.models import User
from library.storage import StorageError
from library.validation import ValidationError


def register_cli(app):
    @app.cli.command('create-user')
    @click.argument('username')
    @click.option('--email', default=None)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user_command(username, email, password):
        """Create a user and their library directory."""
        try:
            user = create_user(username, password, email)
        except (ValidationError, Conflict) as e:
            raise click.ClickException(e.message)
        except StorageError as e:
            raise click.ClickException(f"storage error: {e}")
        click.echo(f"created user '{user.username}' (id {user.id})")

    @app.cli.command('list-users')
    def list_users_command():
        """List users."""
        for user in User.query.order_by(User.id):
            click.echo(f"{user.id}\t{user.username}\t{user.email or '-'}\t{'active' if user.is_active else 'DISABLED'}")
