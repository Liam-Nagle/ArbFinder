import logging
from datetime import datetime

import httpx

from .base import Exchange, Market, Outcome

logger = logging.getLogger(__name__)

CATEGORY_KEYWORDS = {
    "politics": ["election", "president", "vote", "senate", "congress", "parliament", "prime minister", "referendum"],
    "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "sol", "price will"],
    "sports": ["nfl", "nba", "mlb", "nhl", "premier league", "champions league", "world cup", "tennis", "ufc"],
}


class PolymarketExchange(Exchange):
    name = "Polymarket"
    BASE_URL = "https://clob.polymarket.com"
    MAX_MARKETS = 300

    async def fetch_markets(self) -> list[Market]:
        markets: list[Market] = []
        next_cursor: str | None = None

        async with httpx.AsyncClient(timeout=30) as client:
            while len(markets) < self.MAX_MARKETS:
                params: dict = {"active": "true", "closed": "false"}
                if next_cursor:
                    params["next_cursor"] = next_cursor

                try:
                    resp = await client.get(f"{self.BASE_URL}/markets", params=params)
                    resp.raise_for_status()
                except httpx.HTTPError as e:
                    logger.error(f"Polymarket HTTP error: {e}")
                    break

                data = resp.json()

                for item in data.get("data", []):
                    market = self._parse_market(item)
                    if market:
                        markets.append(market)

                next_cursor = data.get("next_cursor")
                if not next_cursor or next_cursor == "LTE=":
                    break

        return markets

    def _parse_market(self, item: dict) -> Market | None:
        tokens = item.get("tokens", [])
        if len(tokens) < 2:
            return None

        outcomes: list[Outcome] = []
        for token in tokens:
            price = token.get("price", 0)
            if price <= 0.01 or price >= 0.99:
                continue
            outcomes.append(Outcome(
                name=token.get("outcome", "Unknown"),
                odds=round(1 / price, 4),
            ))

        if len(outcomes) < 2:
            return None

        condition_id = item.get("condition_id", "")
        question = item.get("question", "")
        slug = item.get("market_slug", condition_id)

        return Market(
            id=f"polymarket_{condition_id}",
            exchange=self.name,
            title=question,
            category=self._categorize(question),
            outcomes=outcomes,
            url=f"https://polymarket.com/event/{slug}",
            fetched_at=datetime.utcnow(),
        )

    def _categorize(self, title: str) -> str:
        lower = title.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return category
        return "other"
