from .base import *

DEBUG = False

ADMINS = [
    ('Mahmoud', 'email@mydomain.com'),
]

ALLOWED_HOSTS = ['*']
# ALLOWED_HOSTS = ['educaproject.com', 'www.educaproject.com']
# ALLOWED_HOSTS = ['.educaproject.com']

# Whitenoise settings
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
REDIS_DB = 0

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f'{REDIS_URL}/{REDIS_DB}',
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

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE


# Security
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True