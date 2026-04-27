import asyncio
import logging
from datetime import datetime

import httpx

from .base import Exchange, Market, Outcome

logger = logging.getLogger(__name__)

SPORT_CATEGORY_MAP = {
    "american-football": "sports",
    "basketball": "sports",
    "tennis": "sports",
    "football": "sports",
    "rugby-union": "sports",
    "rugby-league": "sports",
    "cricket": "sports",
    "ice-hockey": "sports",
    "golf": "sports",
    "politics": "politics",
    "current-affairs": "other",
}


class SmarketsExchange(Exchange):
    name = "Smarkets"
    BASE_URL = "https://api.smarkets.com/v3"
    MAX_EVENTS = 40

    async def fetch_markets(self) -> list[Market]:
        markets: list[Market] = []

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/events/",
                    params={"state": "live", "per_page": self.MAX_EVENTS},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(f"Smarkets events error: {e}")
                return []

            events = resp.json().get("events", [])

            tasks = [self._fetch_event_markets(client, event) for event in events]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    markets.extend(result)

        return markets

    async def _fetch_event_markets(self, client: httpx.AsyncClient, event: dict) -> list[Market]:
        event_id = event.get("id")
        category = self._get_category(event)
        markets: list[Market] = []

        try:
            resp = await client.get(
                f"{self.BASE_URL}/markets/",
                params={"event_id": event_id, "state": "live"},
            )
            if resp.status_code != 200:
                return []
        except httpx.HTTPError:
            return []

        for m_data in resp.json().get("markets", []):
            market = await self._build_market(client, m_data, event, category)
            if market:
                markets.append(market)

        return markets

    async def _build_market(
        self, client: httpx.AsyncClient, m_data: dict, event: dict, category: str
    ) -> Market | None:
        market_id = m_data.get("id")

        try:
            c_resp = await client.get(f"{self.BASE_URL}/markets/{market_id}/contracts/")
            q_resp = await client.get(f"{self.BASE_URL}/markets/{market_id}/quotes/")
        except httpx.HTTPError:
            return None

        if c_resp.status_code != 200 or q_resp.status_code != 200:
            return None

        contracts = {
            str(c["id"]): c["name"]
            for c in c_resp.json().get("contracts", [])
        }
        quotes = q_resp.json().get("quotes", {})

        outcomes: list[Outcome] = []
        for contract_id, quote in quotes.items():
            # Best back price = cheapest offer (in centiprice, 0–10000)
            offers = quote.get("offer", [])
            if not offers:
                continue
            centiprice = offers[0][0]
            if not centiprice or centiprice <= 0 or centiprice >= 10000:
                continue

            decimal_odds = round(10000 / centiprice, 4)
            available = offers[0][1] if len(offers[0]) > 1 else None
            name = contracts.get(contract_id, f"Outcome {contract_id}")

            outcomes.append(Outcome(name=name, odds=decimal_odds, available_stake=available))

        if len(outcomes) < 2:
            return None

        event_name = event.get("name", "")
        market_name = m_data.get("name", "")
        title = f"{event_name} – {market_name}" if market_name != event_name else event_name

        return Market(
            id=f"smarkets_{market_id}",
            exchange=self.name,
            title=title,
            category=category,
            outcomes=outcomes,
            url=f"https://smarkets.com/event/{event.get('id')}/sport/{m_data.get('slug', '')}",
            fetched_at=datetime.utcnow(),
        )

    def _get_category(self, event: dict) -> str:
        sport = (event.get("sport") or "").lower()
        cat_obj = event.get("category") or {}
        slug = (cat_obj.get("slug") if isinstance(cat_obj, dict) else "").lower()
        return SPORT_CATEGORY_MAP.get(sport, SPORT_CATEGORY_MAP.get(slug, "other"))
