from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set-theme/', views.set_theme, name='set_theme'),
    path('manual/', views.manual, name='manual'),
]
