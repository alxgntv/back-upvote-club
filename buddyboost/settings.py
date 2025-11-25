import os
from pathlib import Path
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from datetime import timedelta
import logging
import dj_database_url
import stripe
import json

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')
ALLOWED_REDIRECT_HOSTS = ['localhost','127.0.0.1', 'api.upvote.club', 'upvote.club',]
NGROK_URL = os.environ.get('NGROK_URL', '')
if NGROK_URL:
    ALLOWED_HOSTS.append(NGROK_URL)
    ALLOWED_HOSTS.append(f"{NGROK_URL}.ngrok-free.app")
    ALLOWED_HOSTS.append(f"https://{NGROK_URL}.ngrok-free.app")
    ALLOWED_HOSTS.append(f"http://{NGROK_URL}.ngrok-free.app")
    ALLOWED_HOSTS.append(f"localhost:3000")
    ALLOWED_HOSTS.append(f"localhost:3000")
    ALLOWED_HOSTS.append(f"localhost")
    ALLOWED_HOSTS.append(f"127.0.0.1")
    ALLOWED_HOSTS.append(f"api.upvote.club")
    ALLOWED_HOSTS.append(f"upvote.club")
    ALLOWED_HOSTS.append(f"https://upvote.club")
    ALLOWED_HOSTS.append(f"http://upvote.club")
    ALLOWED_HOSTS.append(f"https://api.upvote.club")
    ALLOWED_HOSTS.append(f"http://api.upvote.club")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'api',
    'django_crontab',
    'markdownx',
    'whitenoise.runserver_nostatic',
    'django_filters',
    'twitter_auth',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'buddyboost.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'buddyboost.wsgi.application'

if 'SUPERUSER_USERNAME' in os.environ:
    DJANGO_SUPERUSER_USERNAME = os.environ['SUPERUSER_USERNAME']
    DJANGO_SUPERUSER_PASSWORD = os.environ['SUPERUSER_PASSWORD']
    DJANGO_SUPERUSER_EMAIL = os.environ['SUPERUSER_EMAIL']

# Database
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=True)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Firebase settings
# Primary: take JSON from env (Heroku Config Var)
FIREBASE_CREDENTIALS_JSON = os.getenv('FIREBASE_CREDENTIALS_JSON')
FIREBASE_CREDENTIALS = None

if FIREBASE_CREDENTIALS_JSON:
    # Use credentials from environment variable (Heroku)
    try:
        FIREBASE_CREDENTIALS = json.loads(FIREBASE_CREDENTIALS_JSON)
    except Exception:
        FIREBASE_CREDENTIALS = None
else:
    # Fallback for local dev (file on disk)
    firebase_credentials_path = os.path.join(BASE_DIR, 'credentials', 'firebase-credentials.json')
    if os.path.exists(firebase_credentials_path):
        FIREBASE_CREDENTIALS = firebase_credentials_path

# Twitter API settings
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
TWITTER_CALLBACK_URL = os.getenv('TWITTER_CALLBACK_URL')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')

# Apify settings
APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')


# Stripe settings
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_SUCCESS_URL = os.getenv('STRIPE_SUCCESS_URL')
STRIPE_CANCEL_URL = os.getenv('STRIPE_CANCEL_URL')
STRIPE_API_VERSION = os.getenv('STRIPE_API_VERSION', '2024-04-10')

# Stripe Price IDs
STRIPE_MEMBER_MONTHLY_PRICE_ID = os.getenv('STRIPE_MEMBER_MONTHLY_PRICE_ID')
STRIPE_MEMBER_ANNUAL_PRICE_ID = os.getenv('STRIPE_MEMBER_ANNUAL_PRICE_ID')
STRIPE_BUDDY_MONTHLY_PRICE_ID = os.getenv('STRIPE_BUDDY_MONTHLY_PRICE_ID')
STRIPE_BUDDY_ANNUAL_PRICE_ID = os.getenv('STRIPE_BUDDY_ANNUAL_PRICE_ID')
STRIPE_MATE_MONTHLY_PRICE_ID = os.getenv('STRIPE_MATE_MONTHLY_PRICE_ID')
STRIPE_MATE_ANNUAL_PRICE_ID = os.getenv('STRIPE_MATE_ANNUAL_PRICE_ID')

# Initialize Stripe with API version
stripe.api_key = STRIPE_SECRET_KEY
stripe.api_version = STRIPE_API_VERSION

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'api.authentication.FirebaseAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# Настройки для Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# Firebase Admin SDK initialization
if FIREBASE_CREDENTIALS:
    if isinstance(FIREBASE_CREDENTIALS, dict):
        # Credentials from environment variable (JSON dict)
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    else:
        # Credentials from file path
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred)

# Google Indexing API credentials
# Primary: take JSON from env (Heroku Config Var)
GOOGLE_INDEXING_JSON = os.getenv('GOOGLE_INDEXING_JSON')
GOOGLE_INDEXING_CREDENTIALS_INFO = None
if GOOGLE_INDEXING_JSON:
    try:
        GOOGLE_INDEXING_CREDENTIALS_INFO = json.loads(GOOGLE_INDEXING_JSON)
    except Exception:
        GOOGLE_INDEXING_CREDENTIALS_INFO = None

# Fallback for local dev (file on disk)
GOOGLE_API_CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials', 'google-indexing-api.json')

# CORS settings
CORS_ALLOW_ALL_ORIGINS = False  # Изменено на False для безопасности
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_WHITELIST = [
    'http://localhost:3000',
    'https://localhost:3000',
    "https://5380-64-176-193-154.ngrok-free.app",
    "https://frontend-upvote-c-git-c3f4d9-serviceintheroomgmailcoms-projects.vercel.app",
    "https://frontend-upvote-club-6loqur3hg.vercel.app/",
    "https://upvote.club",
    "https://api.upvote.club"
]
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'https://localhost:3000',
    "https://5380-64-176-193-154.ngrok-free.app",
    "https://frontend-upvote-c-git-c3f4d9-serviceintheroomgmailcoms-projects.vercel.app",
    "https://frontend-upvote-club-6loqur3hg.vercel.app",
    "https://upvote.club",
    "http://upvote.club",
    "https://api.upvote.club",
    "http://api.upvote.club"
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'ngrok-skip-browser-warning',
    'x-middleware-ssr',
    'x-blog-post-data',
    'access-control-allow-origin',
    'access-control-allow-headers',
    'access-control-allow-methods',
    'access-control-max-age',
    'access-control-allow-credentials'
]

# Добавьте эту строку, чтобы разрешить все заголовки
CORS_ALLOW_ALL_HEADERS = True

# Добавьте localhost:3000 в CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'https://localhost:3000',
    'http://localhost:8000',
    'https://*.ngrok-free.app',
    'https://5380-64-176-193-154.ngrok-free.app',
    "https://frontend-upvote-c-git-c3f4d9-serviceintheroomgmailcoms-projects.vercel.app",
    "http://frontend-upvote-c-git-c3f4d9-serviceintheroomgmailcoms-projects.vercel.app",
    "https://frontend-upvote-club-6loqur3hg.vercel.app",
    "https://upvote.club",
    "https://api.upvote.club"
]

NGROK_URL = os.environ.get('NGROK_URL', '')
HEROKU_ENV = os.environ.get('HEROKU_ENV', 'False') == 'True'

if NGROK_URL:
    ALLOWED_HOSTS.append(NGROK_URL)
    CSRF_TRUSTED_ORIGINS.append(f'https://{NGROK_URL}')
    print(f"Добавлен NGROK_URL: {NGROK_URL} в ALLOWED_HOSTS и CSRF_TRUSTED_ORIGINS")

if HEROKU_ENV:
    ALLOWED_HOSTS.append('api.upvote.club')
    CSRF_TRUSTED_ORIGINS.append('https://api.upvote.club')
    print("Добавлен api.upvote.club в ALLOWED_HOSTS и CSRF_TRUSTED_ORIGINS для продакшн среды")

# SSL settings
if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_PROXY_SSL_HEADER = None
else:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Настройки SSL для локальной разработки
if os.environ.get('DJANGO_HTTPS') == 'on':
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_CERT = os.environ.get('DJANGO_CERT_PATH')
    SECURE_SSL_KEY = os.environ.get('DJANGO_KEY_PATH')

# Logging settings
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[{asctime}] [{levelname}] {name}: {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'api': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'], 
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# Отключение автоматического добавления слеша
APPEND_SLASH = False

# Отключение перенаправления на HTTPS (только для разработки)
SECURE_SSL_REDIRECT = False

# Twitter API settings
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
TWITTER_CALLBACK_URL = os.getenv('TWITTER_CALLBACK_URL')
FRONTEND_URL = os.getenv('FRONTEND_URL')
CHROME_EXTENSION_URL = os.getenv('CHROME_EXTENSION_URL')

# Heroku settings
HEROKU_ENV = os.environ.get('HEROKU_ENV') == 'True'
if HEROKU_ENV:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    print(f"Настройки Heroku применены. HEROKU_ENV: {HEROKU_ENV}")

# Единая конфигурация для статических файлов
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Единая конфигурация WhiteNoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False
WHITENOISE_ALLOW_ALL_ORIGINS = True

# Определите ID расширений для разрабоки и продакшена
EXTENSION_ID_DEV = 'egiglaghnpkmgpnnhlolghdlgjpdjmgp'
EXTENSION_ID_PROD = 'fkiaohmeeoiipoknngcppjbkinaamnof'
TASKS_PER_REQUEST = int(os.getenv('TASKS_PER_REQUEST', 50))

# Добавьте эти строки к существующим CORS_ALLOWED_ORIGINS
CORS_ALLOWED_ORIGINS += [
    f'chrome-extension://{EXTENSION_ID_DEV}',
    f'chrome-extension://{EXTENSION_ID_PROD}'
]

# Если у вас есть CORS_ORIGIN_WHITELIST, добавьте те же строки и туда
if 'CORS_ORIGIN_WHITELIST' in locals() or 'CORS_ORIGIN_WHITELIST' in globals():
    CORS_ORIGIN_WHITELIST += [
        f'chrome-extension://{EXTENSION_ID_DEV}',
        f'chrome-extension://{EXTENSION_ID_PROD}'
    ]


CRONJOBS = [
    # Сначала обновляем задачи
    ('0 4 * * *', 'api.cron.update_all_user_tasks'),
    # Потом отправляем письма
    ('5 4 * * *', 'api.management.commands.send_daily_tasks_emails.Command.handle'),
    # Новая задача - проверять каждые 5 минут
    ('*/5 * * * *', 'api.management.commands.send_delayed_onboarding_emails.Command.handle'),
    ('*/11 * * * *', 'api.management.commands.process_auto_actions.Command.handle'),
]

# Email settings
TASKS_PER_EMAIL = 5
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'es22.siteground.eu')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 465))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'robot@upvote.club')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '2s243_2qi+y')
EMAIL_USE_SSL = True  # Для порта 465 нужно использовать SSL вместо TLS
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_HOST_USER', 'robot@upvote.club')
SERVER_EMAIL = os.getenv('EMAIL_HOST_USER', 'robot@upvote.club')

SITE_URL = os.getenv('SITE_URL', 'https://upvote.club')

# Firebase Settings
FIREBASE_AUTH = {
    'TOKEN_EXPIRY': 60 * 60 * 24 * 30,  # 30 дней в секундах
    'SESSION_COOKIE_EXPIRY': 60 * 60 * 24 * 30,  # 30 дней в секундах
}

COMPLETE_TASK_REQUIRES_AUTH = os.getenv('COMPLETE_TASK_REQUIRES_AUTH', 'True').lower() == 'true'

BACKEND_ADMIN_URL = SITE_URL