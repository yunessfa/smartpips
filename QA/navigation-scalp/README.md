# Navigation, Unicode, staged exits — local acceptance

29 frontend tests; production Vite build passes (existing chunk-size warning).
220 isolated Django tests OK, 1 skipped; no migration or production database validation here.
Browser at widths390/1440: delayed lazy route (1.2s), previous-page and shell DOM retained,
zero main document requests on internal navigation, TP1/TP2/TP3 labels and engine prices,
original-position slice quantities, and single attached TP preserved in mocked POST.
Two mocked demo requests, no external/exchange network access. Six final screenshots reviewed.
Chart heights remain unchanged; only price precision and target overlays were changed.
Underlying strategy engine, stop/target distances and real execution semantics unchanged.
Staged exit display is guidance, NOT an implementation of exchange partial orders.
Earlier demo-only risk-budget advisory fix is retained.

Run Vite from frontend on port5175; run from repo root:
CHROMIUM_PATH=/usr/local/bin/chromium node qa/navigation-scalp/browser.mjs
Playwright is a separate QA prerequisite; adjust the import path for your QA installation.
