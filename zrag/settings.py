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
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'zrag',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'zrag.api.middleware.RequestIDMiddleware',
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
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'zrag.api.exception_handler.api_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'ZRAG API',
    'DESCRIPTION': 'ZRAG 知识库 RAG 系统 API 文档。所有 API（除健康检查）需要 Bearer Token 认证。',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SECURITY': [{'bearerAuth': []}],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'API Key',
                'description': '输入 API Key',
            },
        },
    },
}

ROOT_URLCONF = 'zrag.urls'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'django.db',
    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [],
        },
    },
]

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True

# =============================================================================
# 日志配置
#
# 双路径输出:
#   1. console — 流式输出到 stdout/stderr (供 Docker json-file driver 捕获)
#   2. file    — 按天轮转文件输出, 保留 7 天, UTF-8 编码
#
# 格式: 时间戳 [级别] 线程ID 函数名:行号 消息内容
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(thread)d %(funcName)s:%(lineno)d %(message)s',
        },
    },
    'filters': {
        'level_debug': {
            '()': 'zrag.log_filter.ExactLevelFilter',
            'level': 'DEBUG',
        },
        'level_info': {
            '()': 'zrag.log_filter.ExactLevelFilter',
            'level': 'INFO',
        },
        'level_warning': {
            '()': 'zrag.log_filter.ExactLevelFilter',
            'level': 'WARNING',
        },
        'level_error': {
            '()': 'zrag.log_filter.ExactLevelFilter',
            'level': 'ERROR',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'log', 'debug.log'),
            'when': 'D',
            'interval': 1,
            'backupCount': 7,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'filters': ['level_debug'],
        },
        'file_info': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'log', 'info.log'),
            'when': 'D',
            'interval': 1,
            'backupCount': 7,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'filters': ['level_info'],
        },
        'file_warning': {
            'level': 'WARNING',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'log', 'warning.log'),
            'when': 'D',
            'interval': 1,
            'backupCount': 7,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'filters': ['level_warning'],
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'log', 'error.log'),
            'when': 'D',
            'interval': 1,
            'backupCount': 7,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'filters': ['level_error'],
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_debug', 'file_info', 'file_warning', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_debug', 'file_info', 'file_warning', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console', 'file_debug', 'file_info', 'file_warning', 'file_error'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
}
