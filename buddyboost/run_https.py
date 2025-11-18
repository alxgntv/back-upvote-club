import os
import sys
import ssl
import logging
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Добавляем путь к корневой директории проекта
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buddyboost.settings')

import django
django.setup()

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    pass

if __name__ == "__main__":
    logger.info("Запуск Django с HTTPS на localhost:8000")
    
    certfile = os.path.join(project_root, 'localhost.crt')
    keyfile = os.path.join(project_root, 'localhost.key')
    
    logger.info(f"Используется сертификат: {certfile}")
    logger.info(f"Используется ключ: {keyfile}")
    
    # Устанавливаем переменные окружения для SSL
    os.environ['DJANGO_HTTPS'] = 'on'
    os.environ['DJANGO_CERT_PATH'] = certfile
    os.environ['DJANGO_KEY_PATH'] = keyfile
    
    # Логируем NGROK_URL
    ngrok_url = os.environ.get('NGROK_URL')
    if ngrok_url:
        logger.info(f"NGROK_URL: {ngrok_url}")
    else:
        logger.warning("NGROK_URL не установлен")
    
    # Создаем SSL контекст
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    
    # Получаем WSGI приложение
    application = get_wsgi_application()
    handler = StaticFilesHandler(application)
    
    # Запускаем сервер
    httpd = make_server('localhost', 8000, handler, ThreadingWSGIServer)
    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    
    logger.info("Сервер запущен на https://localhost:8000")
    httpd.serve_forever()