This patch implements Wave‑3 Patch 2: **Watchlist & screener boost**.

Included files:

- `src/catalyst_bot/config.py` – Adds `screener_csv` and `feature_screener_boost` settings.
- `src/catalyst_bot/watchlist.py` – Introduces `load_screener_set` to parse Finviz screener CSVs.
- `src/catalyst_bot/feeds.py` – Combines watchlist and screener tickers into a unified set used to bypass the price ceiling filter.
- `env.example.ini` – Documents `FEATURE_SCREENER_BOOST` and `SCREENER_CSV` variables.
- `MIGRATIONS.md` – Records the new variables under the “Unreleased” section.
- `CHANGELOG.md` – Adds an entry for the watchlist & screener boost feature.
- `tests/test_watchlist_screener_boost.py` – New unit test covering screener boost logic.
- `APPLY.ps1` – Script to apply this patch idempotently to an existing repository.