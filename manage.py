#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

def run_server():
    from django.core.wsgi import get_wsgi_application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from wsgiref.simple_server import make_server
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')
    application = get_wsgi_application()
    handler = StaticFilesHandler(application)
    
    httpd = make_server('localhost', 8000, handler)
    httpd.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        run_server()
    else:
        main()
