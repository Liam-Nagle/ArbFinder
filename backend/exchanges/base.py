from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Outcome(BaseModel):
    name: str
    odds: float
    available_stake: Optional[float] = None


class Market(BaseModel):
    id: str
    exchange: str
    title: str
    category: str
    outcomes: list[Outcome]
    url: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class Exchange(ABC):
    name: str

    @abstractmethod
    async def fetch_markets(self) -> list[Market]:
        pass
