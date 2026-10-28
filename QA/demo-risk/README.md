# Demo stop-risk advisory hotfix

- Django: 220 isolated tests, OK, 1 skipped (config.test_settings SQLite; not migration validation).
- Frontend: 20 tests pass; Vite production build succeeds (existing chunk warnings).
- Local browser: 390/1440 widths, SUI short .9857/.993888, 75x, margin50, qty3804.403.
- Four mocked POSTs: success and hard errors at each width. Non-local network blocked.
- Both stop-budget warnings readable and retained after modal close; no horizontal overflow.
- All six final screenshots reviewed individually. External charts not tested live.
- No real exchange order, production deployment or PostgreSQL operation run here.
- Stop distance/liquidation, margin, daily loss, position count, invalid/missing stops unchanged.

Browser test: start Vite from frontend on port5174, then repository root:
CHROMIUM_PATH=/usr/local/bin/chromium node qa/demo-risk/browser.mjs
Adjust the Playwright import for your QA installation. Not a production dependency.
