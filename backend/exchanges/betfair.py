import logging
from datetime import datetime

import httpx

from .base import Exchange, Market, Outcome
from backend.config import config

logger = logging.getLogger(__name__)

EVENT_TYPE_MAP = {
    "Soccer": "sports",
    "Tennis": "sports",
    "Basketball": "sports",
    "American Football": "sports",
    "Ice Hockey": "sports",
    "Rugby Union": "sports",
    "Cricket": "sports",
    "Golf": "sports",
    "Politics": "politics",
}


class BetfairExchange(Exchange):
    name = "Betfair"
    LOGIN_URL = "https://identitysso.betfair.com/api/login"
    API_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"

    def __init__(self):
        self._session_token: str | None = None
        self._cfg = config.exchanges.betfair

    async def fetch_markets(self) -> list[Market]:
        if not self._cfg.enabled or not self._cfg.api_key:
            return []

        if not self._session_token:
            await self._login()

        if not self._session_token:
            logger.error("Betfair: login failed, skipping")
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            catalogue = await self._list_catalogue(client)
            if not catalogue:
                return []

            market_ids = [m["marketId"] for m in catalogue]
            books = await self._list_books(client, market_ids)

            markets: list[Market] = []
            for cat in catalogue:
                book = books.get(cat["marketId"])
                if book:
                    market = self._parse(cat, book)
                    if market:
                        markets.append(market)

            return markets

    async def _login(self):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self.LOGIN_URL,
                    data={"username": self._cfg.username, "password": self._cfg.password},
                    headers={
                        "X-Application": self._cfg.api_key,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    self._session_token = data.get("token")
                else:
                    logger.error(f"Betfair login error: {data.get('error')}")
        except httpx.HTTPError as e:
            logger.error(f"Betfair login HTTP error: {e}")

    async def _list_catalogue(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.post(
                f"{self.API_URL}/listMarketCatalogue/",
                headers=self._headers(),
                json={
                    "filter": {
                        "inPlayOnly": True,
                        "marketTypeCodes": ["MATCH_ODDS", "MONEYLINE", "1X2"],
                    },
                    "maxResults": 100,
                    "marketProjection": [
                        "MARKET_NAME", "EVENT", "EVENT_TYPE", "RUNNER_DESCRIPTION",
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Betfair catalogue error: {e}")
            return []

    async def _list_books(self, client: httpx.AsyncClient, market_ids: list[str]) -> dict[str, dict]:
        try:
            resp = await client.post(
                f"{self.API_URL}/listMarketBook/",
                headers=self._headers(),
                json={
                    "marketIds": market_ids[:50],
                    "priceProjection": {
                        "priceData": ["EX_BEST_OFFERS"],
                        "exBestOffersOverrides": {"bestPricesDepth": 1},
                    },
                },
            )
            resp.raise_for_status()
            return {b["marketId"]: b for b in resp.json()}
        except httpx.HTTPError as e:
            logger.error(f"Betfair market book error: {e}")
            return {}

    def _parse(self, cat: dict, book: dict) -> Market | None:
        runner_names = {r["selectionId"]: r["runnerName"] for r in cat.get("runners", [])}
        outcomes: list[Outcome] = []

        for runner in book.get("runners", []):
            if runner.get("status") != "ACTIVE":
                continue
            best_back = runner.get("ex", {}).get("availableToBack", [])
            if not best_back:
                continue
            odds = best_back[0].get("price")
            size = best_back[0].get("size")
            name = runner_names.get(runner["selectionId"], "Unknown")
            if odds and odds > 1.0:
                outcomes.append(Outcome(name=name, odds=odds, available_stake=size))

        if len(outcomes) < 2:
            return None

        event = cat.get("event", {})
        event_type = cat.get("eventType", {}).get("name", "")
        title = f"{event.get('name', '')} – {cat.get('marketName', '')}"

        return Market(
            id=f"betfair_{cat['marketId']}",
            exchange=self.name,
            title=title,
            category=EVENT_TYPE_MAP.get(event_type, "sports"),
            outcomes=outcomes,
            url=f"https://www.betfair.com/exchange/plus/{cat['marketId']}",
            fetched_at=datetime.utcnow(),
        )

    def _headers(self) -> dict:
        return {
            "X-Application": self._cfg.api_key,
            "X-Authentication": self._session_token or "",
            "Content-Type": "application/json",
        }
