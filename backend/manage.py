#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Django's runserver defaults to 8000, which collides with anything else
# already on that port. Charla takes 8001 so it can run alongside another
# local Django project, and so `runserver` on its own is enough - a flag you
# have to remember is a flag you eventually forget.
DEFAULT_RUNSERVER_PORT = os.environ.get('CHARLA_PORT', '8001')


def apply_default_port(argv):
    """Give bare `runserver` a port, leaving an explicit one alone.

    Only fires when the command is exactly `runserver` with no address
    argument; `runserver 9000` or `runserver 0.0.0.0:8000` still win, as do
    every other management command.
    """
    if len(argv) < 2 or argv[1] != 'runserver':
        return argv

    rest = argv[2:]
    if any(not arg.startswith('-') for arg in rest):
        return argv  # an address was given
    return [argv[0], argv[1], DEFAULT_RUNSERVER_PORT, *rest]


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(apply_default_port(sys.argv))


if __name__ == '__main__':
    main()
