"""
ASGI config for educa project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

# 1. تغيير الإعداد الافتراضي ليكون الخاص بالإنتاج (prod) بدلاً من (local)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'educa.settings.prod')

# 2. تهيئة وتجهيز تطبيقات Django بالكامل لمنع خطأ AppRegistryNotReady
django_asgi_app = get_asgi_application()

# 3. استيراد مكتبات Channels والـ Routing الخاص بك بعد تهيئة جينقو تماماً
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.auth import AuthMiddlewareStack
import chat.routing

# 4. بناء الـ Application بالشكل السليم
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                chat.routing.websocket_urlpatterns
            )
        )
    ),
})
