from django.db import models


class AIProvider(models.Model):
    """A configurable, OpenAI-compatible chat model provider.

    DeepSeek, OpenAI, OpenRouter, Groq and many free providers all expose an
    OpenAI-compatible `/chat/completions` endpoint, so a single client works
    for all of them — only the base URL, model name and API key change.
    """

    PROVIDER_CHOICES = [
        ("deepseek", "DeepSeek"),
        ("openai", "OpenAI"),
        ("openrouter", "OpenRouter"),
        ("groq", "Groq"),
        ("ollama", "Ollama (local)"),
        ("custom", "Custom (OpenAI-compatible)"),
    ]

    DEFAULT_BASE_URLS = {
        "deepseek": "https://api.deepseek.com",
        "openai": "https://api.openai.com",
        "openrouter": "https://openrouter.ai/api",
        "groq": "https://api.groq.com/openai",
        "ollama": "http://localhost:11434",
    }

    DEFAULT_MODELS = {
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o-mini",
        "openrouter": "deepseek/deepseek-chat",
        "groq": "llama-3.3-70b-versatile",
        "ollama": "llama3.1",
    }

    label = models.CharField(max_length=120, help_text="Friendly name shown in the UI")
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="deepseek")
    base_url = models.CharField(max_length=255, blank=True)
    model = models.CharField(max_length=120, blank=True)
    api_key = models.CharField(max_length=255, blank=True)
    temperature = models.FloatField(default=0.4)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "label"]

    def save(self, *args, **kwargs):
        # Fill in sensible defaults based on the provider type.
        if not self.base_url:
            self.base_url = self.DEFAULT_BASE_URLS.get(self.provider_type, "")
        if not self.model:
            self.model = self.DEFAULT_MODELS.get(self.provider_type, "")
        # Only one provider can be active at a time.
        if self.is_active:
            AIProvider.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.label} [{self.model}]"
