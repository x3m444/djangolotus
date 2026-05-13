from django.urls import path
from . import views

app_name = 'manager'

urlpatterns = [
    path('', views.index, name='index'),

    # Nomenclator
    path('nomenclator/', views.nomenclator, name='nomenclator'),
    path('nomenclator/add/', views.produs_add, name='produs_add'),
    path('nomenclator/<int:pk>/edit/', views.produs_edit, name='produs_edit'),
    path('nomenclator/<int:pk>/delete/', views.produs_delete, name='produs_delete'),
    path('nomenclator/export/', views.produs_export, name='produs_export'),
    path('nomenclator/<int:pk>/reteta/', views.produs_reteta, name='produs_reteta'),
    path('nomenclator/<int:pk>/reteta/add/', views.reteta_linie_add, name='reteta_linie_add'),
    path('reteta/linie/<int:pk>/delete/', views.reteta_linie_delete, name='reteta_linie_delete'),
    path('ingrediente/', views.ingrediente, name='ingrediente'),
    path('ingrediente/add/', views.ingredient_add, name='ingredient_add'),

    # Planificare
    path('planificare/', views.planificare, name='planificare'),
    path('planificare/salveaza/', views.planificare_salveaza, name='planificare_salveaza'),
    path('planificare/export/', views.planificare_export, name='planificare_export'),

    # Lansare Producție
    path('lansare/', views.lansare, name='lansare'),
    path('lansare/salveaza/', views.lansare_salveaza, name='lansare_salveaza'),
    path('lansare/<int:pk>/adauga/', views.lansare_adauga, name='lansare_adauga'),
    path('lansare/<int:pk>/sterge/', views.lansare_sterge, name='lansare_sterge'),

    # Firme
    path('firme/', views.firme, name='firme'),
    path('firme/firma/add/', views.firma_add, name='firma_add'),
    path('firme/firma/<int:pk>/save/', views.firma_save, name='firma_save'),
    path('firme/firma/<int:pk>/toggle/', views.firma_toggle, name='firma_toggle'),
    path('firme/firma/<int:firma_pk>/angajat/add/', views.angajat_add, name='angajat_add'),
    path('firme/angajat/<int:pk>/toggle/', views.angajat_toggle, name='angajat_toggle'),
    path('firme/lansare/salveaza/', views.firme_lansare_salveaza, name='firme_lansare_salveaza'),
    path('firme/lansare/<int:pk>/sterge/', views.firme_lansare_sterge, name='firme_lansare_sterge'),
    path('firme/rezervare/salveaza/', views.firme_rezervare_salveaza, name='firme_rezervare_salveaza'),
    path('firme/raport/export/', views.firme_raport_export, name='firme_raport_export'),

    # Rapoarte
    path('rapoarte/', views.rapoarte, name='rapoarte'),

    # Utilizatori
    path('utilizatori/', views.utilizatori, name='utilizatori'),
    path('utilizatori/add/', views.utilizator_add, name='utilizator_add'),
    path('utilizatori/<int:pk>/toggle/', views.utilizator_toggle, name='utilizator_toggle'),
    path('utilizatori/<int:pk>/reset-parola/', views.utilizator_reset_parola, name='utilizator_reset_parola'),
    path('utilizatori/<int:pk>/link-livrator/', views.utilizator_link_livrator, name='utilizator_link_livrator'),
]
