# jobs/finviz_filings.py
from __future__ import annotations
import logging, os
from typing import Iterable
from catalyst_bot.finviz_elite import export_latest_filings
from catalyst_bot.storage import connect, migrate, insert_filings

# Optional alert hook
try:
    from catalyst_bot.alerts import post_discord_json  # type: ignore
except Exception:
    def post_discord_json(payload: dict):
        print("[ALERT]", payload)
        return {"status": "printed"}

log = logging.getLogger("finviz_filings")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

def iter_watchlist() -> Iterable[str]:
    # Replace with your watchlist source if you have one; this is a sensible default.
    return ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL"]

IMPORTANT_FORMS = {"8-K", "13D", "13G", "SC 13D", "SC 13G", "S-1", "424B", "144"}

def run_once():
    conn = connect()
    migrate(conn)
    total_new = 0
    for t in iter_watchlist():
        rows = export_latest_filings(ticker=t)
        new = insert_filings(conn, t, rows)
        log.info("ingested_filings", extra={"ticker": t, "added": new, "seen": len(rows)})
        total_new += new
        # lightweight alert rule
        for r in rows[:3]:  # only preview a few to avoid noise
            form = (r.get("Form") or r.get("Type") or "").upper()
            if form in IMPORTANT_FORMS:
                post_discord_json({
                    "channel": "filings",
                    "ticker": t,
                    "title": f"{t} filed {form}",
                    "url": r.get("Link") or r.get("link"),
                    "form": form,
                    "when": r.get("Filing Date") or r.get("Date"),
                })
    log.info("filings_complete", extra={"new_records": total_new})

if __name__ == "__main__":
    if not os.getenv("FINVIZ_ELITE_AUTH"):
        raise SystemExit("Set FINVIZ_ELITE_AUTH first.")
    run_once()
