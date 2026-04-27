import asyncio
from datetime import datetime, timezone
from backend.engine.calculator import ArbOpportunity


class Store:
    def __init__(self):
        self._opportunities: list[ArbOpportunity] = []
        self._last_updated: datetime | None = None
        self._exchange_status: dict = {}
        self._lock = asyncio.Lock()

    async def update(self, opportunities: list[ArbOpportunity], exchange_status: dict):
        async with self._lock:
            self._opportunities = opportunities
            self._last_updated = datetime.now(timezone.utc)
            self._exchange_status = exchange_status

    def get_opportunities(self) -> list[ArbOpportunity]:
        return self._opportunities

    def get_status(self) -> dict:
        return {
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,  # always UTC+offset
            "opportunity_count": len(self._opportunities),
            "exchange_status": self._exchange_status,
        }


store = Store()
