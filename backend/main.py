import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import config
from backend.engine.calculator import find_all_arbs
from backend.engine.matcher import match_markets
from backend.exchanges.base import Market
from backend.exchanges.betfair import BetfairExchange
from backend.exchanges.odds_api import OddsApiExchange
from backend.exchanges.polymarket import PolymarketExchange
from backend.exchanges.smarkets import SmarketsExchange
from backend.store import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_exchanges():
    cfg = config.exchanges
    exchanges = []
    if cfg.polymarket.enabled:
        exchanges.append(PolymarketExchange())
    if cfg.smarkets.enabled:
        exchanges.append(SmarketsExchange())
    if cfg.betfair.enabled and cfg.betfair.api_key:
        exchanges.append(BetfairExchange())
    if cfg.odds_api.enabled and cfg.odds_api.api_key:
        exchanges.append(OddsApiExchange())
    return exchanges


async def poll_once(exchanges):
    all_markets: list[Market] = []
    exchange_status: dict = {}

    for exchange in exchanges:
        try:
            markets = await exchange.fetch_markets()
            all_markets.extend(markets)
            exchange_status[exchange.name] = {
                "status": "ok",
                "market_count": len(markets),
                "last_fetched": datetime.utcnow().isoformat(),
            }
            logger.info(f"{exchange.name}: {len(markets)} markets")
        except Exception as e:
            logger.error(f"{exchange.name} failed: {e}")
            exchange_status[exchange.name] = {
                "status": "error",
                "error": str(e),
                "market_count": 0,
                "last_fetched": None,
            }

    pairs = match_markets(all_markets, threshold=config.settings.match_threshold)
    logger.info(f"Matched {len(pairs)} market pairs across exchanges")

    opportunities = find_all_arbs(
        pairs,
        bankroll=config.settings.bankroll,
        min_arb_percent=config.settings.min_arb_percent,
    )
    logger.info(f"Found {len(opportunities)} arb opportunities")

    await store.update(opportunities, exchange_status)


async def polling_loop():
    exchanges = build_exchanges()
    logger.info(f"Polling loop started — exchanges: {[e.name for e in exchanges]}")

    while True:
        try:
            await poll_once(exchanges)
        except Exception as e:
            logger.error(f"Poll cycle error: {e}")
        await asyncio.sleep(config.settings.poll_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(polling_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="ArbFinder API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/opportunities")
async def get_opportunities():
    return {
        "opportunities": [o.model_dump() for o in store.get_opportunities()],
        "status": store.get_status(),
    }


@app.get("/api/status")
async def get_status():
    return store.get_status()


# Serve the frontend — must come last so API routes take priority
docs_dir = Path(__file__).parent.parent / "docs"
if docs_dir.exists():
    app.mount("/", StaticFiles(directory=str(docs_dir), html=True), name="frontend")
