Patch B – Sector & Session Enhancements
======================================

This patch introduces Wave 4’s sector and market‑session context
capability along with optional low‑beta relaxation.  A new module
(`src/catalyst_bot/sector_info.py`) provides helper functions to look up
sector information, derive a human‑readable market session for a
timestamp, and compute a neutral band adjustment based on sector
risk.  An auxiliary configuration module
(`src/catalyst_bot/config_extras.py`) defines feature flags and default
values for these features.

Key features
------------

* **Sector lookup:** `get_sector_info(ticker)` returns a dict
  containing `sector`, `industry` and `beta` (float or `None`).  Unknown
  tickers return `None` values so callers can fall back to a default
  label.  Populate `SECTOR_MAP` with additional tickers as needed.

* **Session detection:** `get_session(ts, tz)` maps a datetime to a
  session name (`Pre‑Mkt`, `Regular`, `After‑Hours`, or `Closed`).  The
  lookup assumes U.S. market hours (04:00–20:00 Eastern Time).
  Session names can be customised via the `SESSION_NAMES` environment
  variable (e.g. `SESSION_NAMES=pre:Pre‑Market,regular:Day,after:Post`).

* **Low‑beta relaxation:** When `FEATURE_SECTOR_RELAX=1`, callers can
  widen the neutral band for specified sectors by a given number of
  basis points.  Configure per‑sector adjustments via
  `LOW_BETA_SECTORS`, e.g. `LOW_BETA_SECTORS=utilities:5,consumer
  staples:7`, and a default adjustment for other sectors via
  `DEFAULT_NEUTRAL_BAND_BPS`.  Use
  `get_neutral_band_bps(sector)` to retrieve the appropriate
  adjustment.

* **Configuration:** Feature flags are defined in
  `src/catalyst_bot/config_extras.py`.  Add the following lines to
  your `.env` to enable features and customise behaviour:

  ```ini
  FEATURE_SECTOR_INFO=0
  FEATURE_MARKET_TIME=0
  FEATURE_SECTOR_RELAX=0
  LOW_BETA_SECTORS=utilities:5,consumer staples:7
  DEFAULT_NEUTRAL_BAND_BPS=0
  SECTOR_FALLBACK_LABEL=Unknown
  SESSION_NAMES=pre:Pre‑Mkt,regular:Regular,after:After‑Hours,closed:Closed
  ```

Integration guidance
--------------------

1. **Import helpers:** Update your alert generation code (e.g.
   `alerts.py`) to import `get_sector_info`, `get_session` and
   `get_neutral_band_bps` from `catalyst_bot.sector_info` and feature flags
   from `catalyst_bot.config_extras`.

2. **Display fields separately:** When `FEATURE_SECTOR_INFO` is enabled,
   call `get_sector_info(ticker)`.  If all returned values are `None`, use
   `SECTOR_FALLBACK_LABEL` as the field value.  Otherwise, display
   the `sector` value (omit the industry unless desired).  When
   `FEATURE_MARKET_TIME` is enabled, call `get_session(now, tz)`
   (using the appropriate timezone for your alerts) and place the
   resulting session label near the bottom of the embed, close to your
   existing timestamp.

3. **Low‑beta adjustment:** When `FEATURE_SECTOR_RELAX` is enabled,
   compute a neutral band adjustment via
   `get_neutral_band_bps(sector)` and widen your bullishness neutral
   band accordingly for the relevant sector.  If you already use a
   neutral band in basis points, simply add the returned value.

4. **Graceful fallback:** If no sector information is available for a
   ticker, display `SECTOR_FALLBACK_LABEL` rather than omitting the
   field.  Similarly, ensure that `get_session` always returns a
   sensible value (`Closed`) so the session field never disappears.

This patch does not modify existing files directly; instead it
provides the building blocks and configuration required to implement
sector and session display.  See the Wave 4 roadmap for further
details and examples.