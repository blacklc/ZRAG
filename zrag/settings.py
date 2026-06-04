import os
from pathlib import Path

from zrag.config.loader import load_config

BASE_DIR = Path(__file__).resolve().parent.parent

_config = load_config("config")

ZRAG_API_KEY = _config.get("api", {}).get("key", "")
ZRAG_LLM = _config.get("llm", {})
ZRAG_EMBEDDING = _config.get("embedding", {})
ZRAG_STORAGE = _config.get("storage", {})
ZRAG_INGEST = _config.get("ingest", {})
ZRAG_RETRIEVAL = _config.get("retrieval", {})

DEFAULT_THROTTLE_RATES = _config.get("api", {}).get("throttle_rates", {
    'chat': '10/min',
    'ingest': '3/min',
})

SECRET_KEY = 'django-insecure-dev-only-key'
DEBUG = True
ALLOWED_HOSTS = ['localhost']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'rest_framework',
    'corsheaders',
    'zrag',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True   # Phase 1 开发阶段

CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'UNAUTHENTICATED_USER': None,
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': DEFAULT_THROTTLE_RATES,
    'EXCEPTION_HANDLER': 'zrag.api.exception_handler.api_exception_handler',
}

ROOT_URLCONF = 'zrag.urls'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'django.db',
    }
}

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True
