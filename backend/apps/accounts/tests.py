from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import ExpiringToken


class AuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass1234")

    def test_login_issues_token(self):
        res = self.client.post(
            reverse("login"), {"username": "alice", "password": "pass1234"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.data)
        self.assertEqual(res.data["username"], "alice")

    def test_bad_password_rejected(self):
        res = self.client.post(
            reverse("login"), {"username": "alice", "password": "wrong"}
        )
        self.assertEqual(res.status_code, 401)

    def test_register_creates_user_and_token(self):
        res = self.client.post(
            reverse("register"), {"username": "bob", "password": "pass1234"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(User.objects.filter(username="bob").exists())

    def test_expired_token_is_rejected(self):
        token = ExpiringToken.objects.create(user=self.user)
        # backdate it beyond the TTL
        token.created = timezone.now() - timedelta(days=2)
        token.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        res = self.client.get(reverse("me"))
        self.assertEqual(res.status_code, 401)
        # the auth layer should have deleted the stale token
        self.assertFalse(ExpiringToken.objects.filter(key=token.key).exists())

    def test_valid_token_grants_access(self):
        login = self.client.post(
            reverse("login"), {"username": "alice", "password": "pass1234"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        res = self.client.get(reverse("me"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["username"], "alice")
