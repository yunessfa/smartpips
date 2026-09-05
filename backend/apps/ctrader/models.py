from django.db import models


class CTraderToken(models.Model):
    """Stores the OAuth token + chosen trading account for the cTrader bridge.

    There's normally just one row (singleton). The OAuth callback fills the tokens
    and the account list; the bridge reads them to connect.
    """
    access_token = models.CharField(max_length=255, blank=True)
    refresh_token = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # the ctidTraderAccountId the bridge should trade/stream
    account_id = models.BigIntegerField(null=True, blank=True)
    accounts_json = models.JSONField(default=list)  # full account list from OAuth
    updated = models.DateTimeField(auto_now=True)

    def is_valid(self):
        return bool(self.access_token and self.account_id)
