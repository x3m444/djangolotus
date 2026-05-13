from django.conf import settings as django_settings
from .views import TEME, TEMA_DEFAULT


def tema(request):
    tema_curenta = request.session.get('tema', TEMA_DEFAULT)
    tema_info = next((t for t in TEME if t[0] == tema_curenta), TEME[0])
    return {
        'tema_curenta':   tema_curenta,
        'tema_tip':       tema_info[2],
        'teme_disponibile': TEME,
        'settings':       django_settings,
    }
