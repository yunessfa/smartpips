import os
import subprocess
import sys
from django.test import SimpleTestCase


class RealRefreshMigrationTests(SimpleTestCase):
    def test_actual_migrations_login_expiry_rotation_devices(self):
        env = dict(os.environ)
        env.pop('DJANGO_SETTINGS_MODULE', None)
        result = subprocess.run([sys.executable, '-m', 'apps.accounts.refresh_smoke'],
                                capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('"real_migrations": "pass"', result.stdout)
