import os
from .base import *

DEBUG = False

ADMINS = [
    ('Mahmoud', 'email@mydomain.com'),
]

ALLOWED_HOSTS = ['*']
# # ALLOWED_HOSTS = ['educaproject.com', 'www.educaproject.com']
# ALLOWED_HOSTS = ['.educaproject.com']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': 'db',
        'PORT': 5432,
    }
}

REDIS_URL = 'redis://cache:6379'
REDIS_HOST = 'cache'
REDIS_PORT = 6379
REDIS_DB = 0
CACHES['default']['LOCATION'] = REDIS_URL
CHANNEL_LAYERS['default']['CONFIG']['hosts'] = [REDIS_URL]

# Security
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True