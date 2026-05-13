from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User, Group


class AutoLoginMiddleware:
    """
    Când AUTH_ENABLED=False, autologhează automat ca admin
    fără să ceară parolă. Util în development.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.AUTH_ENABLED and not request.user.is_authenticated:
            user, created = User.objects.get_or_create(
                username='dev_admin',
                defaults={'is_staff': True, 'is_superuser': True}
            )
            if created:
                user.set_unusable_password()
                user.save()
                group, _ = Group.objects.get_or_create(name='admin')
                user.groups.set([group])

            user.backend = 'apps.core.auth_backend.UtilizatoriBackend'
            login(request, user)

        return self.get_response(request)
