# jobs/finviz_ingest.py
from __future__ import annotations
import logging, os
from catalyst_bot.finviz_elite import screener_unusual_volume, screener_breakouts_largecap_nasdaq
from catalyst_bot.storage import connect, migrate, insert_screener_rows

log = logging.getLogger("finviz_ingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

def run_once():
    conn = connect()
    migrate(conn)

    screens = {
        "unusual_volume": screener_unusual_volume(),
        "breakouts_largecap_nasdaq": screener_breakouts_largecap_nasdaq(),
    }
    total = 0
    for key, rows in screens.items():
        n = insert_screener_rows(conn, key, rows)
        log.info("ingested_screen", extra={"screen": key, "rows": n})
        total += n

    log.info("ingest_complete", extra={"total_rows": total})

if __name__ == "__main__":
    # Require auth
    if not os.getenv("FINVIZ_ELITE_AUTH"):
        raise SystemExit("Set FINVIZ_ELITE_AUTH first.")
    run_once()
