"""Command-line commands, registered onto the app.

    flask --app app send-test-email you@example.com

A CLI command rather than a dev-only route, on purpose. A route needs a guard
that a later edit can quietly remove, and a route that sends email to an
arbitrary address is an open relay if that guard ever breaks. A command is not
reachable over the network at all, so the protection is structural rather than
conditional. The FLASK_ENV check below is a second lock on a door that has no
handle on the outside.
"""

import click

import config
from services import email_service, email_templates


def register(app):
    @app.cli.command("send-test-email")
    @click.argument("address")
    @click.option("--name", default="Test User",
                  help="Name to greet, for checking how the template renders.")
    def send_test_email(address, name):
        """Send the welcome email to ADDRESS without creating an account."""
        if config.IS_PRODUCTION:
            raise click.ClickException(
                "Refusing to run with FLASK_ENV=production. This command exists "
                "to check rendering during development."
            )

        subject, html, text = email_templates.welcome(name)

        click.echo(f"backend:  {config.EMAIL_BACKEND}")
        click.echo(f"from:     {config.MAIL_FROM_NAME} <{config.MAIL_FROM_ADDRESS}>")
        click.echo(f"to:       {email_service.mask_email(address)}")
        click.echo(f"subject:  {subject}")
        click.echo(f"rendered: {len(html)} chars html, {len(text)} chars text")

        # Synchronous here, unlike signup: a CLI caller is waiting for the
        # answer, and exiting before the thread finishes would report nothing.
        result = email_service.send(address, subject, html, text, template="welcome")

        if result.success:
            click.secho(f"sent. message id: {result.provider_message_id}", fg="green")
        else:
            raise click.ClickException(result.error)
