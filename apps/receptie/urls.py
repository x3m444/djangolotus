from django.urls import path
from . import views

app_name = 'receptie'

urlpatterns = [
    path('', views.index, name='index'),

    # Comenzi
    path('comanda/nou/', views.comanda_nou, name='comanda_nou'),
    path('comanda/add/', views.comanda_add, name='comanda_add'),
    path('comanda/<int:pk>/', views.comanda_detail, name='comanda_detail'),
    path('comanda/<int:pk>/status/', views.comanda_status, name='comanda_status'),
    path('comanda/<int:pk>/anuleaza/', views.comanda_anuleaza, name='comanda_anuleaza'),

    # Clienți
    path('clienti/cauta/', views.clienti_cauta, name='clienti_cauta'),
    path('clienti/add/', views.client_add, name='client_add'),
]
