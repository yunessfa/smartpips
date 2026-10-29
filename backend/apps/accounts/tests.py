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


class RefreshTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # login throttle (8/min) is cache-backed; isolate tests
        self.user = User.objects.create_user("renew", password="pass1234")

    def sign_in(self):
        from rest_framework.test import APIClient
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(reverse("login"), {"username": "renew", "password": "pass1234"})
        self.assertEqual(response.status_code, 200)
        return client, response

    def renew(self, client):
        return client.post(reverse("refresh"), {}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

    def test_cookie_is_httponly_and_digest_only(self):
        from apps.accounts.models import RefreshSession
        client, response = self.sign_in()
        cookie = response.cookies["smartpips_refresh"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertNotEqual(RefreshSession.objects.get().digest, cookie.value)
        self.assertNotIn("refresh_token", response.data)

    def test_refresh_survives_access_expiry_and_rotates(self):
        client, login = self.sign_in()
        ExpiringToken.objects.filter(key=login.data["token"]).update(created=timezone.now() - timedelta(days=2))
        # Real expiry rejection deletes the old access token but not its session.
        client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        self.assertEqual(client.get(reverse("me")).status_code, 401)
        old_cookie = client.cookies["smartpips_refresh"].value
        response = self.renew(client)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["token"], login.data["token"])
        self.assertNotEqual(client.cookies["smartpips_refresh"].value, old_cookie)
        client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(client.get(reverse("me")).status_code, 200)

    def test_missing_csrf_is_denied(self):
        client, _ = self.sign_in()
        self.assertEqual(client.post(reverse("refresh"), {}).status_code, 403)

    def test_rotated_cookie_cannot_be_replayed(self):
        client, _ = self.sign_in()
        old = client.cookies["smartpips_refresh"].value
        self.assertEqual(self.renew(client).status_code, 200)
        client.cookies["smartpips_refresh"] = old
        self.assertEqual(self.renew(client).status_code, 401)

    def test_expired_refresh_is_denied(self):
        from apps.accounts.models import RefreshSession
        client, _ = self.sign_in()
        RefreshSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.renew(client).status_code, 401)

    def test_logout_revokes_session(self):
        from apps.accounts.models import RefreshSession
        client, login = self.sign_in()
        client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        self.assertEqual(client.post(reverse("logout")).status_code, 204)
        self.assertEqual(RefreshSession.objects.count(), 0)

    def test_other_device_survives_logout(self):
        from apps.accounts.models import RefreshSession
        first, login = self.sign_in()
        second, _ = self.sign_in()
        first.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        first.post(reverse("logout"))
        self.assertEqual(RefreshSession.objects.count(), 1)
        self.assertEqual(self.renew(second).status_code, 200)

    def test_disabled_user_cannot_refresh(self):
        client, _ = self.sign_in()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.renew(client).status_code, 401)

    def test_cross_origin_refresh_is_denied_even_with_csrf(self):
        client, _ = self.sign_in()
        response = client.post(reverse("refresh"), {},
                               HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
                               HTTP_ORIGIN="https://untrusted.example")
        self.assertEqual(response.status_code, 403)
