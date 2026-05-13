from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST

TEME = [
    ('slate',    'Slate',    'dark'),
    ('darkly',   'Darkly',   'dark'),
    ('cyborg',   'Cyborg',   'dark'),
    ('flatly',   'Flatly',   'light'),
    ('sandstone','Sandstone','light'),
    ('minty',    'Minty',    'light'),
    ('pulse',    'Pulse',    'light'),
]
TEMA_DEFAULT = 'darkly'


def login_view(request):
    if not settings.AUTH_ENABLED:
        return redirect('dashboard')

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard'))
        else:
            messages.error(request, 'Username sau parolă incorectă.')

    return render(request, 'base/login.html')


def logout_view(request):
    logout(request)
    if settings.AUTH_ENABLED:
        return redirect('login')
    return redirect('dashboard')


@login_required
def dashboard(request):
    rol = request.user.groups.first()
    rol_name = rol.name if rol else 'admin'

    redirect_map = {
        'receptie':  'receptie:index',
        'bucatarie': 'bucatarie:index',
        'ghiseu':    'ghiseu:index',
        'livrator':  'livrare:index',
        'admin':     'manager:index',
    }

    target = redirect_map.get(rol_name)
    if target:
        try:
            return redirect(target)
        except Exception:
            pass

    return render(request, 'base/dashboard.html', {'rol': rol_name})


@login_required
def manual(request):
    return render(request, 'core/manual.html')


@require_POST
def set_theme(request):
    tema = request.POST.get('tema', TEMA_DEFAULT)
    if tema in [t[0] for t in TEME]:
        request.session['tema'] = tema
    return redirect(request.POST.get('next', '/staff/'))
