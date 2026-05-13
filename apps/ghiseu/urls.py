from django.urls import path
from . import views

app_name = 'ghiseu'

urlpatterns = [
    path('', views.index, name='index'),

    # Servire
    path('servire/add/',             views.servire_add,    name='servire_add'),
    path('bon/add/',                 views.bon_add,        name='bon_add'),

    # Angajați
    path('angajat/add/',             views.angajat_add,    name='angajat_add'),
    path('angajat/<int:pk>/toggle/', views.angajat_toggle, name='angajat_toggle'),

    # Eveniment
    path('eveniment/<int:pk>/distribuit/', views.eveniment_distribuit, name='eveniment_distribuit'),

    # Comenzi speciale ghișeu
    path('special/add/',              views.special_comanda_add, name='special_comanda_add'),
    path('special/<int:pk>/livrat/',  views.special_livrat,      name='special_livrat'),
]
