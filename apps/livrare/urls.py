from django.urls import path
from . import views

app_name = 'livrare'

urlpatterns = [
    path('', views.index, name='index'),

    # Marcare status
    path('comanda/<int:pk>/pedrum/', views.pedrum, name='pedrum'),
    path('comanda/<int:pk>/livrat/', views.livrat, name='livrat'),
    path('comanda/<int:pk>/problema/', views.problema, name='problema'),
    path('comanda/<int:pk>/aviz/', views.aviz, name='aviz'),
]
