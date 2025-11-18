import os
import sys
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
from wsgiref.simple_server import make_server

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')

import django
django.setup()

if __name__ == "__main__":
    print("Запуск Django на http://localhost:8000")
    
    application = get_wsgi_application()
    handler = StaticFilesHandler(application)
    
    httpd = make_server('localhost', 8000, handler)
    print("Сервер запущен на http://localhost:8000")
    httpd.serve_forever()