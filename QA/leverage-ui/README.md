# Local fixture smoke test

This test never connects to an exchange. Every API response is intercepted; all
non-localhost network requests are aborted. Dummy token and synthetic journal data
are UI fixtures, not a trading recommendation or a profitability result.

Start Vite on 127.0.0.1:5173, then from repository root with Playwright installed:

```sh
CHROMIUM_PATH=/path/to/chromium node qa/leverage-ui/browser-smoke.mjs
```

Playwright is a separate QA prerequisite, not a production dependency. Screenshots
are written to qa/leverage-ui/artifacts. A real/demo label in this test means the
UI mode only: both order submissions are mocked. TradingView external embeds are
blocked by design. This is not a live exchange, browser authentication, production
Docker or PostgreSQL migration acceptance test.

Executed release checks:
- Django 209 tests, OK, skipped=1 (isolated config.test_settings database).
- Frontend 15 tests, pass=15; production Vite build succeeded.
- Local Chromium 24 checks; 2 simulated orders; no page exceptions.
- 1440 and 390 widths; reduced motion; pagination with 5,000 synthetic trades.
- High leverage keeps submit enabled, stop-based sizing does not clamp leverage,
  warning survives modal close; no horizontal document overflow.
- Shell deployment script syntax checked with bash -n; NOT run on production here.

Visual review: every captured view was opened individually. Primary button fill
was corrected after the first review, then re-rendered and inspected. Risk editor
was compacted without hiding saved balance/risk. Close glyph was replaced by an
explicit SVG. Final chart component height: 80%, unchanged. Dashboard external
chart blanks during this offline fixture are not presented as live chart tests.
