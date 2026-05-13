import bcrypt
from django.contrib.auth.models import User, Group
from apps.core.models import Utilizator


class UtilizatoriBackend:
    """
    Autentificare împotriva tabelului `utilizatori` (bcrypt).
    Sincronizează utilizatorul cu Django auth_user și grupuri per rol.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            util = Utilizator.objects.get(username=username, activ=True)
        except Utilizator.DoesNotExist:
            return None

        pw_bytes = password.encode('utf-8')
        hash_bytes = util.password_hash.encode('utf-8')
        if not bcrypt.checkpw(pw_bytes, hash_bytes):
            return None

        return self._sync_django_user(util)

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _sync_django_user(self, util):
        user, _ = User.objects.get_or_create(username=util.username)
        user.is_staff = util.rol == 'admin'
        user.is_superuser = util.rol == 'admin'
        user.save()

        group, _ = Group.objects.get_or_create(name=util.rol)
        user.groups.set([group])

        return user
