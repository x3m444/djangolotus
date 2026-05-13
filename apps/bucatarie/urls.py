from django.urls import path
from . import views

app_name = 'bucatarie'

urlpatterns = [
    path('', views.index, name='index'),

    # Gătire lot (per produs, agregat)
    path('gatit/batch/', views.gatit_batch, name='gatit_batch'),
    path('gatit/batch/reset/', views.gatit_batch_reset, name='gatit_batch_reset'),

    # Gătire comenzi individuale
    path('comanda/<int:pk>/gatit/', views.comanda_gatit, name='comanda_gatit'),
    path('linie/<int:pk>/gatit/', views.linie_gatit, name='linie_gatit'),

    # Împachetare
    path('comanda/<int:pk>/impachetare/', views.impachetare_comanda, name='impachetare_comanda'),
    path('pachet-firma/<int:pk>/ambalat/', views.pachet_firma_ambalat, name='pachet_firma_ambalat'),

    # Buffer ambalare (mutat de la ghișeu la bucătărie)
    path('buffer/add/', views.buffer_add, name='buffer_add'),

    # Necesar ingrediente
    path('necesar/export/',          views.necesar_export,  name='necesar_export'),
    path('necesar/<int:pk>/primit/', views.necesar_primit,  name='necesar_primit'),

    # Stoc nevândut
    path('stoc/declara/', views.stoc_declara, name='stoc_declara'),
]
