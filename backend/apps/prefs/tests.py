from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import MarketAccess


class MarketAccessTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_user("boss", password="p", is_staff=True)
        self.user = U.objects.create_user("trader", password="p")
        self.api = APIClient()

    def test_defaults_all_allowed(self):
        self.api.force_authenticate(self.user)
        r = self.api.get("/api/prefs/market_access/")
        self.assertEqual(r.json(), {"metals": True, "spot": True, "futures": True})

    def test_admin_can_restrict_and_user_sees_it(self):
        self.api.force_authenticate(self.admin)
        r = self.api.patch(f"/api/prefs/market_access/{self.user.id}/",
                           {"metals": False, "spot": False}, format="json")
        self.assertEqual(r.json(), {"metals": False, "spot": False, "futures": True})
        self.api.force_authenticate(self.user)
        r2 = self.api.get("/api/prefs/market_access/")
        self.assertEqual(r2.json()["metals"], False)
        self.assertEqual(r2.json()["futures"], True)

    def test_non_admin_cannot_change_others(self):
        self.api.force_authenticate(self.user)
        r = self.api.patch(f"/api/prefs/market_access/{self.admin.id}/",
                           {"futures": False}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_all_access_map(self):
        MarketAccess.objects.create(user=self.user, allow_futures=False)
        self.api.force_authenticate(self.admin)
        r = self.api.get("/api/prefs/market_access/all/")
        data = r.json()
        self.assertEqual(data[str(self.user.id)]["futures"], False)
        self.assertEqual(data[str(self.admin.id)]["metals"], True)
