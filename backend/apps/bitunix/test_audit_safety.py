from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.bitunix.client import BitunixError

class RealOrderSafetyTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="real-safe")
        self.api=APIClient();self.api.force_authenticate(self.user)
        self.data={"mode":"real","confirm":True,"symbol":"BTCUSDT","side":"BUY","qty":.01,"leverage":2}
    def send(self, account=None, risk_error=False, leverage_error=False):
        from unittest.mock import Mock
        client=Mock(configured=True);client.last_price.return_value=100
        client.account.return_value=account if account is not None else {"available":100}
        client.place_order.return_value={"orderId":"mock-only"}
        if leverage_error:client.change_leverage.side_effect=BitunixError("failed")
        with patch("apps.bitunix.views._client",return_value=client),patch("apps.prefs.models.RiskLimits.check_order",side_effect=RuntimeError("test") if risk_error else None,return_value=None):
            response=self.api.post("/api/bitunix/order/",self.data,format="json")
        return response,client
    def test_risk_check_failure_blocks(self):
        r,c=self.send(risk_error=True);self.assertEqual(r.status_code,503);c.place_order.assert_not_called()
    def test_unknown_balance_blocks(self):
        r,c=self.send(account={"unrelated":100});self.assertEqual(r.status_code,503);c.place_order.assert_not_called()
    def test_zero_balance_not_fallback(self):
        r,c=self.send(account={"available":0,"availableBalance":100});self.assertEqual(r.status_code,400);c.place_order.assert_not_called()
    def test_leverage_failure_blocks(self):
        r,c=self.send(leverage_error=True);self.assertEqual(r.status_code,502);c.place_order.assert_not_called()
    def test_known_valid_context_passes_mock(self):
        r,c=self.send();self.assertEqual(r.status_code,200);c.place_order.assert_called_once()
