@@
 ### Changed

 - **Price lookup**: Updated `get_last_price_snapshot()` in
   `src/catalyst_bot/market.py` to use the new cached Alpha Vantage
   fetcher and to respect the configured TTL.
+
+### Analyzer Enhancements
+
+- **Daily report & pending changes**: The analyzer now produces a
+  Markdown report summarizing each day's events, per‑category hit/miss
+  statistics and newly discovered keywords. Reports are written to
+  `out/analyzer/summary_<date>.md`.
+- **Weight proposals & unknown keywords**: Based on price change
+  thresholds (configurable via `ANALYZER_HIT_UP_THRESHOLD_PCT` and
+  `ANALYZER_HIT_DOWN_THRESHOLD_PCT`), the analyzer computes hit/miss
+  ratios for each keyword category and generates proposed weight
+  adjustments. It also records keywords observed in titles that are
+  absent from `keyword_weights.json`. These proposals are serialized
+  to `data/analyzer/pending_<planId>.json` for admin review.
+- **Classification integration**: Integrated the `classifier.classify`
+  helper to evaluate news relevance and sentiment. This enables
+  categorization by configured keyword categories and identification
+  of unknown keywords.
+- **Environment thresholds**: Added support for the environment
+  variables `ANALYZER_HIT_UP_THRESHOLD_PCT` and
+  `ANALYZER_HIT_DOWN_THRESHOLD_PCT` to tune the price move criteria
+  used when computing hit/miss statistics (default ±5 %).
+
+### Notes
+
+These analyzer enhancements lay the groundwork for a fully automated
+daily workflow. Reports and pending changes are generated but not
+automatically applied; an admin must review and approve the proposed
+updates by promoting the pending JSON file into `keyword_stats.json`.
+Future phases will integrate the approval loop and backtesting
+framework.
