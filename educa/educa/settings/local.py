from .base import *

DEBUG = True

# If .env defines POSTGRES_HOST=db (Docker service DNS),
# override to localhost when running Django directly on host machine.
_postgres_host = config('POSTGRES_HOST', default='127.0.0.1')
if _postgres_host == 'db':
    _postgres_host = '127.0.0.1'

# Keep local runtime separate from Docker internal POSTGRES_PORT values.
_postgres_port = int(config('LOCAL_POSTGRES_PORT', default=5433))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB', default='postgres'),
        'USER': config('POSTGRES_USER', default='postgres'),
        'PASSWORD': config('POSTGRES_PASSWORD', default='postgres'),
        'HOST': _postgres_host,
        'PORT': _postgres_port,
    }
}