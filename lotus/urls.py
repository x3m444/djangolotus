from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Zona publica
    path('', include('apps.public.urls')),

    # Zona staff
    path('staff/', include('apps.core.urls')),
    path('staff/receptie/', include('apps.receptie.urls')),
    path('staff/bucatarie/', include('apps.bucatarie.urls')),
    path('staff/ghiseu/', include('apps.ghiseu.urls')),
    path('staff/livrare/', include('apps.livrare.urls')),
    path('staff/manager/', include('apps.admin_manager.urls')),

    path('admin/', admin.site.urls),
]
