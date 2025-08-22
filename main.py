# catalyst/main.py
from __future__ import annotations
import asyncio, logging, random
from contextlib import suppress

from .logsetup import setup_logging
from .config import settings
from .store import Store
from .pipeline import Pipeline
from .alerting.discorder import DiscordAlerter
from .services.universe import UniverseService
from .ingest.finviz import FinvizNewsIngestor
from .ingest.alphavantage import AlphaVantageNewsIngestor

async def _pump(ing, pipe: Pipeline):
    name = ing.__class__.__name__
    log = logging.getLogger(__name__)
    try:
        async for item in ing.run():
            await pipe.handle(item)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning("Ingestor %s failed: %s", name, e, exc_info=True)

async def run():
    setup_logging(settings.log_level)
    log = logging.getLogger("catalyst")
    log.info("Catalyst core (Finviz+AV) starting…")

    st = Store(settings.db_path)
    uni = UniverseService()
    await uni.ensure_fresh()

    alerter = None
    if settings.discord_webhook_url or (settings.discord_token and settings.discord_channel_id):
        alerter = DiscordAlerter()
        log.info("Discord alerter enabled.")
    else:
        log.info("Discord alerter disabled.")

    pipe = Pipeline(st, universe=uni, alerter=alerter)

    ingestors = []
    if settings.enable_finviz_news:
        ingestors.append(FinvizNewsIngestor())
    if settings.enable_av_news:
        # AV will pull news for the current universe tickers
        ingestors.append(AlphaVantageNewsIngestor(uni.all_symbols()))

    try:
        while True:
            await uni.ensure_fresh()  # refresh universe periodically
            if not ingestors:
                log.warning("No ingestors enabled; sleeping.")
                await asyncio.sleep(60); continue

            await asyncio.gather(*(_pump(i, pipe) for i in ingestors))
            await asyncio.sleep(150 + random.randint(-15, 15))
    except asyncio.CancelledError:
        pass
    finally:
        with suppress(Exception): st.close()
        log.info("Catalyst stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down.")
