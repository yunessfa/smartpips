from django.db import models


class Source(models.Model):
    """A reference site/feed the assistant uses for fundamental & news context."""

    TYPE_CHOICES = [
        ("exchange", "Exchange"),
        ("news", "News"),
        ("data", "Market Data"),
        ("social", "Social / Sentiment"),
        ("research", "Research"),
    ]

    name = models.CharField(max_length=120)              # e.g. Binance
    url = models.URLField()                              # e.g. https://www.binance.com
    # Optional RSS/Atom feed the assistant reads for recent headlines.
    feed_url = models.URLField(blank=True)
    source_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default="exchange")
    description = models.TextField(blank=True)
    # Weight 1-10: how much the assistant should trust/prioritise this source.
    weight = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-weight", "name"]

    def __str__(self):
        return self.name
