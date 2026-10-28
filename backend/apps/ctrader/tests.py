from unittest.mock import patch, Mock
from urllib.parse import urlparse, parse_qs
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import CTraderToken

@override_settings(CTRADER_CLIENT_ID="client",CTRADER_CLIENT_SECRET="secret",CTRADER_REDIRECT_URI="https://testserver/api/ctrader/callback/")
class OAuthSecurityTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_user(username="admin",is_staff=True)
        self.user=get_user_model().objects.create_user(username="ordinary")
        self.client=APIClient();self.token=CTraderToken.objects.create(id=1,access_token="old",account_id=10)
    def test_anonymous_cannot_mutate(self):
        self.assertIn(self.client.get("/api/ctrader/use/99/").status_code,(401,403,405))
        self.assertIn(self.client.post("/api/ctrader/use_manual/",{"account_id":99}).status_code,(401,403))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post("/api/ctrader/use/99/").status_code,403)
        self.token.refresh_from_db();self.assertEqual(self.token.account_id,10)
    def test_admin_post_only(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/ctrader/use/99/").status_code,405)
        self.assertEqual(self.client.post("/api/ctrader/use_manual/",{"account_id":99}).status_code,200)
        self.token.refresh_from_db();self.assertEqual(self.token.account_id,99)
    @patch("apps.ctrader.views.requests.get")
    def test_missing_state_no_provider_call(self,get):
        self.assertEqual(self.client.get("/api/ctrader/callback/?code=untrusted").status_code,400);get.assert_not_called()
    @patch("apps.ctrader.views.requests.get")
    def test_state_bound_single_use(self,get):
        self.client.force_authenticate(self.admin);r=self.client.get("/api/ctrader/connect/")
        state=parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
        get.side_effect=[Mock(json=lambda:{"accessToken":"secret-access","refreshToken":"secret-refresh","expiresIn":3600}),Mock(json=lambda:{"data":[]})]
        r=self.client.get("/api/ctrader/callback/",{"code":"code","state":state})
        self.assertEqual(r.status_code,200);self.assertNotIn(b"secret-access",r.content)
        self.token.refresh_from_db();self.assertIsNone(self.token.account_id)
        self.client.cookies["sp_ctrader_oauth"]=state
        self.assertEqual(self.client.get("/api/ctrader/callback/",{"code":"code","state":state}).status_code,400)
        self.assertEqual(get.call_count,2)
