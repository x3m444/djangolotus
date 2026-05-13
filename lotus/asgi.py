import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import lotus.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lotus.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(lotus.routing.websocket_urlpatterns)
    ),
})
