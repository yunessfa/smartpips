"""Run in a subprocess: real auth migrations, no MIGRATION_MODULES overrides."""
import json
import tempfile
from pathlib import Path
from django.conf import settings


def main():
    with tempfile.TemporaryDirectory() as folder:
        settings.configure(
            SECRET_KEY='isolated-refresh-smoke-only', DEBUG=False, ALLOWED_HOSTS=['testserver'],
            USE_TZ=True, ROOT_URLCONF='apps.accounts.urls',
            INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes',
                            'rest_framework', 'apps.accounts'],
            DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3',
                                   'NAME': str(Path(folder)/'smoke.sqlite3')}},
            MIDDLEWARE=['django.middleware.csrf.CsrfViewMiddleware'],
            AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'],
            PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
            TOKEN_TTL_SECONDS=1800, REFRESH_TTL_SECONDS=2592000,
            REFRESH_COOKIE_NAME='smartpips_refresh', REFRESH_COOKIE_PATH='/api/auth/',
            REFRESH_COOKIE_SECURE=False, CSRF_TRUSTED_ORIGINS=[],
            REST_FRAMEWORK={
                'DEFAULT_AUTHENTICATION_CLASSES': ['apps.accounts.authentication.ExpiringTokenAuthentication'],
                'DEFAULT_THROTTLE_RATES': {'login': '1000/min'}},
        )
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from django.db.migrations.recorder import MigrationRecorder
        from django.utils import timezone
        from datetime import timedelta
        from rest_framework.test import APIClient
        from apps.accounts.models import ExpiringToken, RefreshSession
        call_command('migrate', 'auth', verbosity=0)
        call_command('migrate', 'accounts', '0003_merge_20260812_1149', verbosity=0)
        User.objects.create_user('fixture', password='not-a-real-password')
        client = APIClient(enforce_csrf_checks=True)
        credentials = {'username': 'fixture', 'password': 'not-a-real-password'}
        missing = client.post('/login/', credentials)
        assert missing.status_code == 503 and missing.data['code'] == 'refresh_schema_missing'
        assert ExpiringToken.objects.count() == 0
        before = set(MigrationRecorder.Migration.objects.values_list('app', 'name'))
        call_command('prepare_refresh', verbosity=0)
        after = set(MigrationRecorder.Migration.objects.values_list('app', 'name'))
        assert after-before == {('accounts', '0004_refreshsession')}
        call_command('prepare_refresh', verbosity=0)  # idempotent
        login = client.post('/login/', credentials)
        assert login.status_code == 200
        assert login.cookies['smartpips_refresh']['httponly']
        old = login.data['token']
        ExpiringToken.objects.filter(pk=old).update(created=timezone.now()-timedelta(hours=2))
        client.credentials(HTTP_AUTHORIZATION=f'Token {old}')
        assert client.get('/me/').status_code == 401
        bootstrap = client.get('/refresh/')
        assert bootstrap.data['csrf_token']
        response = client.post('/refresh/', {}, HTTP_X_CSRFTOKEN=bootstrap.data['csrf_token'])
        assert response.status_code == 200 and response.data['token'] != old
        second = APIClient(enforce_csrf_checks=True)
        assert second.post('/login/', credentials).status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        assert client.post('/logout/').status_code == 204
        csrf = second.get('/refresh/').data['csrf_token']
        assert second.post('/refresh/', {}, HTTP_X_CSRFTOKEN=csrf).status_code == 200
        assert RefreshSession.objects.count() == 1
        print(json.dumps({'real_migrations': 'pass', 'missing_schema_diagnostic': 'pass',
                          'migration_scope': 'accounts.0004 only', 'login': 'pass',
                          'expired_access_refresh': 'pass', 'device_isolation': 'pass'}))


if __name__ == '__main__':
    main()
