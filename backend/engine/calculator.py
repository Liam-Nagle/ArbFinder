import hashlib
from datetime import datetime, timezone
from pydantic import BaseModel

from backend.exchanges.base import Market


class ArbLeg(BaseModel):
    exchange: str
    outcome: str
    odds: float
    stake: float
    market_url: str


class ArbOpportunity(BaseModel):
    id: str
    title: str
    category: str
    arb_percent: float
    legs: list[ArbLeg]
    total_stake: float
    guaranteed_return: float
    guaranteed_profit: float
    found_at: str


def find_arb_for_pair(
    market_a: Market, market_b: Market, bankroll: float
) -> ArbOpportunity | None:
    outcomes_a = {o.name.lower(): (o.odds, market_a) for o in market_a.outcomes}
    outcomes_b = {o.name.lower(): (o.odds, market_b) for o in market_b.outcomes}

    shared = set(outcomes_a) & set(outcomes_b)
    if len(shared) < 2:
        return None

    # For each shared outcome pick the best (highest) odds across both exchanges
    best: dict[str, tuple[float, Market]] = {}
    for name in shared:
        odds_a, mkt_a = outcomes_a[name]
        odds_b, mkt_b = outcomes_b[name]
        best[name] = (odds_a, mkt_a) if odds_a >= odds_b else (odds_b, mkt_b)

    implied_sum = sum(1 / odds for odds, _ in best.values())
    if implied_sum >= 1.0:
        return None

    arb_percent = round((1 - implied_sum) * 100, 3)
    guaranteed_return = round(bankroll / implied_sum, 2)
    guaranteed_profit = round(guaranteed_return - bankroll, 2)

    legs: list[ArbLeg] = []
    for name, (odds, market) in best.items():
        stake = round(bankroll * (1 / odds) / implied_sum, 2)
        legs.append(ArbLeg(
            exchange=market.exchange,
            outcome=name.title(),
            odds=odds,
            stake=stake,
            market_url=market.url,
        ))

    arb_id = hashlib.md5(f"{market_a.id}|{market_b.id}".encode()).hexdigest()[:12]

    return ArbOpportunity(
        id=arb_id,
        title=market_a.title,
        category=market_a.category,
        arb_percent=arb_percent,
        legs=legs,
        total_stake=bankroll,
        guaranteed_return=guaranteed_return,
        guaranteed_profit=guaranteed_profit,
        found_at=datetime.now(timezone.utc).isoformat(),
    )


def find_all_arbs(
    pairs: list[tuple[Market, Market]],
    bankroll: float,
    min_arb_percent: float = 0.5,
) -> list[ArbOpportunity]:
    opportunities: list[ArbOpportunity] = []
    seen: set[str] = set()

    for market_a, market_b in pairs:
        opp = find_arb_for_pair(market_a, market_b, bankroll)
        if opp and opp.arb_percent >= min_arb_percent and opp.id not in seen:
            opportunities.append(opp)
            seen.add(opp.id)

    return sorted(opportunities, key=lambda o: o.arb_percent, reverse=True)
