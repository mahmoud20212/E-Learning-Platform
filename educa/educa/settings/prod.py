from .base import *

DEBUG = True

ADMINS = [
    ('Mahmoud Ouda', 'email@mydomain.com'),
]

ALLOWED_HOSTS = ['*']

if 'courses.middleware.subdomain_course_middleware' in MIDDLEWARE:
    MIDDLEWARE.remove('courses.middleware.subdomain_course_middleware')

if 'debug_toolbar.middleware.DebugToolbarMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')

# إعداد Whitenoise للملفات الثابتة
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB'),
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': config('POSTGRES_HOST'),
        'PORT': config('POSTGRES_PORT'),
    }
}

REDIS_PASSWORD = config('REDIS_PASSWORD')
REDIS_HOST = config('REDIS_HOST')
REDIS_PORT = config('REDIS_PORT', cast=int)

REDIS_URL = f'rediss://default:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}'
CELERY_REDIS_URL = f'{REDIS_URL}?ssl_cert_reqs=none'

REDIS_DB = 0

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CONNECTION_POOL_KWARGS': {
                    'ssl_cert_reqs': None
                }
            }
        }
    }

    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }

    CELERY_BROKER_URL = CELERY_REDIS_URL
    CELERY_RESULT_BACKEND = CELERY_REDIS_URL
    
    # إخبار Celery بعدم التشدد في فحص شهادة الأمان للـ Redis
    CELERY_BROKER_USE_SSL = {
        'ssl_cert_reqs': None
    }
    CELERY_REDIS_BACKEND_USE_SSL = {
        'ssl_cert_reqs': None
    }

CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE

# 5. إعدادات الأمان والـ SSL (متوافقة 100% مع الـ Proxy الخاص بـ Render لمنع الـ Redirect Loop)
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True