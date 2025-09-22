Patch A – Options Scanner Stub
==============================

This patch introduces the first component of Wave 4: a stub implementation
of the options sentiment scanner.  The new module is located at
`src/catalyst_bot/options_scanner.py` and defines a single
function:

* `scan_options(ticker: str) -> Optional[Dict[str, Any]]`: returns
  sentiment data for the given ticker or `None` if no data is available.

The default implementation simply validates the input and returns
`None`.  This makes it safe to enable the feature flag without
changing any behaviour.  A real provider can be added later by
replacing the stubbed logic.

### Installation

1. Copy the contents of this patch into your repository, preserving
   the relative directory structure.
2. Add the following feature flags to your `.env` or
   configuration file (with sensible defaults):

   ```ini
   FEATURE_OPTIONS_SCANNER=0
   SENTIMENT_WEIGHT_OPTIONS=0.05
   OPTIONS_VOLUME_THRESHOLD=3.0
   OPTIONS_MIN_PREMIUM=10000
   ```

3. In your code, import `scan_options` from
   `catalyst_bot.options_scanner` and call it when
   `FEATURE_OPTIONS_SCANNER` is enabled.  Use the returned
   `score` and `label` to adjust your bullishness calculation according
   to `SENTIMENT_WEIGHT_OPTIONS`.  If the function returns `None`,
   skip the options contribution entirely.

This stub is intended to be expanded upon in later patches.  Please
refer to the Wave 4 roadmap for additional context.