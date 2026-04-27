import logging
from datetime import datetime

import httpx

from .base import Exchange, Market, Outcome
from backend.config import config

logger = logging.getLogger(__name__)

SPORT_CATEGORY_MAP = {
    "soccer": "sports",
    "basketball": "sports",
    "americanfootball": "sports",
    "baseball": "sports",
    "icehockey": "sports",
    "tennis": "sports",
    "rugbyleague": "sports",
    "rugbyunion": "sports",
    "cricket": "sports",
    "golf": "sports",
    "politics": "politics",
}


class OddsApiExchange(Exchange):
    name = "OddsAPI"
    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self):
        self._cfg = config.exchanges.odds_api

    async def fetch_markets(self) -> list[Market]:
        if not self._cfg.enabled or not self._cfg.api_key:
            return []

        markets: list[Market] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for sport in self._cfg.sports:
                try:
                    resp = await client.get(
                        f"{self.BASE_URL}/sports/{sport}/odds/",
                        params={
                            "apiKey": self._cfg.api_key,
                            "regions": "uk",
                            "markets": "h2h",
                            "oddsFormat": "decimal",
                        },
                    )
                    if resp.status_code == 401:
                        logger.error("OddsAPI: invalid API key")
                        return []
                    if resp.status_code != 200:
                        continue

                    for event in resp.json():
                        for bookmaker in event.get("bookmakers", []):
                            market = self._parse(event, bookmaker, sport)
                            if market:
                                markets.append(market)

                except httpx.HTTPError as e:
                    logger.error(f"OddsAPI error for {sport}: {e}")

        return markets

    def _parse(self, event: dict, bookmaker: dict, sport: str) -> Market | None:
        h2h = next(
            (m for m in bookmaker.get("markets", []) if m["key"] == "h2h"), None
        )
        if not h2h:
            return None

        outcomes: list[Outcome] = []
        for o in h2h.get("outcomes", []):
            price = o.get("price", 0)
            if price > 1.0:
                outcomes.append(Outcome(name=o["name"], odds=price))

        if len(outcomes) < 2:
            return None

        home = event.get("home_team", "")
        away = event.get("away_team", "")
        title = f"{home} vs {away}"

        category = next(
            (v for k, v in SPORT_CATEGORY_MAP.items() if sport.lower().startswith(k)),
            "sports",
        )
        bk_key = bookmaker.get("key", "unknown")
        bk_title = bookmaker.get("title", bk_key)

        return Market(
            id=f"oddsapi_{bk_key}_{event.get('id', '')}",
            exchange=f"{self.name} ({bk_title})",
            title=title,
            category=category,
            outcomes=outcomes,
            url="https://the-odds-api.com",
            fetched_at=datetime.utcnow(),
        )
