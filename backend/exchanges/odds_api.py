import logging
from datetime import datetime

import httpx

from .base import Exchange, Market, Outcome
from backend.config import config

logger = logging.getLogger(__name__)

# Sport-level URLs per bookmaker key. Used when we can't deep-link to a specific event
# (The Odds API doesn't return bookmaker-internal event IDs).
BOOKMAKER_URLS: dict[str, dict[str, str]] = {
    "bet365": {
        "soccer":          "https://www.bet365.com/#/AS/B1/",
        "basketball":      "https://www.bet365.com/#/AS/B7/",
        "americanfootball":"https://www.bet365.com/#/AS/B60/",
        "tennis":          "https://www.bet365.com/#/AS/B13/",
        "icehockey":       "https://www.bet365.com/#/AS/B62/",
        "rugbyunion":      "https://www.bet365.com/#/AS/B10/",
        "cricket":         "https://www.bet365.com/#/AS/B3/",
        "golf":            "https://www.bet365.com/#/AS/B6/",
        "_default":        "https://www.bet365.com/",
    },
    "matchbook": {
        "soccer":          "https://www.matchbook.com/betting/sport/soccer",
        "basketball":      "https://www.matchbook.com/betting/sport/basketball",
        "americanfootball":"https://www.matchbook.com/betting/sport/american-football",
        "tennis":          "https://www.matchbook.com/betting/sport/tennis",
        "icehockey":       "https://www.matchbook.com/betting/sport/ice-hockey",
        "rugbyunion":      "https://www.matchbook.com/betting/sport/rugby-union",
        "_default":        "https://www.matchbook.com/",
    },
    "paddypower": {
        "soccer":          "https://www.paddypower.com/football",
        "basketball":      "https://www.paddypower.com/basketball",
        "americanfootball":"https://www.paddypower.com/american-football",
        "tennis":          "https://www.paddypower.com/tennis",
        "_default":        "https://www.paddypower.com/",
    },
    "williamhill": {
        "soccer":          "https://sports.williamhill.com/betting/en-gb/football",
        "basketball":      "https://sports.williamhill.com/betting/en-gb/basketball",
        "americanfootball":"https://sports.williamhill.com/betting/en-gb/american-football",
        "tennis":          "https://sports.williamhill.com/betting/en-gb/tennis",
        "_default":        "https://sports.williamhill.com/",
    },
    "ladbrokes": {
        "soccer":          "https://www.ladbrokes.com/sports/football",
        "basketball":      "https://www.ladbrokes.com/sports/basketball",
        "tennis":          "https://www.ladbrokes.com/sports/tennis",
        "_default":        "https://www.ladbrokes.com/",
    },
    "coral": {
        "soccer":          "https://www.coral.co.uk/sports/football",
        "basketball":      "https://www.coral.co.uk/sports/basketball",
        "tennis":          "https://www.coral.co.uk/sports/tennis",
        "_default":        "https://www.coral.co.uk/",
    },
    "betvictor": {
        "soccer":          "https://www.betvictor.com/en-gb/sports/football/matches",
        "basketball":      "https://www.betvictor.com/en-gb/sports/basketball/matches",
        "tennis":          "https://www.betvictor.com/en-gb/sports/tennis/matches",
        "_default":        "https://www.betvictor.com/",
    },
    "unibet_uk": {
        "_default":        "https://www.unibet.co.uk/betting/sports",
    },
    "betway": {
        "_default":        "https://betway.com/en/sports",
    },
    "888sport": {
        "_default":        "https://www.888sport.com/",
    },
    "boylesports": {
        "_default":        "https://www.boylesports.com/sports/football",
    },
    "skybet": {
        "soccer":          "https://m.skybet.com/football",
        "basketball":      "https://m.skybet.com/basketball",
        "_default":        "https://m.skybet.com/",
    },
}


def _bookmaker_url(bk_key: str, sport: str) -> str:
    """Return the best available URL for a bookmaker + sport combination."""
    urls = BOOKMAKER_URLS.get(bk_key, {})
    sport_prefix = next((k for k in BOOKMAKER_URLS.get(bk_key, {}) if sport.lower().startswith(k)), None)
    return urls.get(sport_prefix) or urls.get("_default") or f"https://www.google.com/search?q={bk_key}+{sport}"


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
            url=_bookmaker_url(bk_key, sport),
            fetched_at=datetime.utcnow(),
        )
