import re
from rapidfuzz import fuzz, process

from backend.exchanges.base import Market


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _outcome_names(market: Market) -> frozenset[str]:
    return frozenset(o.name.lower() for o in market.outcomes)


def match_markets(
    all_markets: list[Market], threshold: float = 80.0
) -> list[tuple[Market, Market]]:
    """
    Find pairs of markets from different exchanges that represent the same event.
    Groups by category first, then uses fuzzy title matching.
    Also requires at least 2 matching outcome names.
    """
    by_category: dict[str, list[Market]] = {}
    for m in all_markets:
        by_category.setdefault(m.category, []).append(m)

    pairs: list[tuple[Market, Market]] = []
    seen: set[frozenset[str]] = set()

    for markets in by_category.values():
        by_exchange: dict[str, list[Market]] = {}
        for m in markets:
            by_exchange.setdefault(m.exchange, []).append(m)

        exchanges = list(by_exchange.keys())

        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                group_a = by_exchange[exchanges[i]]
                group_b = by_exchange[exchanges[j]]

                norm_b = [_normalize(m.title) for m in group_b]

                for m_a in group_a:
                    norm_a = _normalize(m_a.title)
                    result = process.extractOne(
                        norm_a, norm_b, scorer=fuzz.token_sort_ratio
                    )
                    if not result or result[1] < threshold:
                        continue

                    m_b = group_b[result[2]]

                    # Require at least 2 shared outcome names
                    shared = _outcome_names(m_a) & _outcome_names(m_b)
                    if len(shared) < 2:
                        continue

                    pair_key = frozenset([m_a.id, m_b.id])
                    if pair_key in seen:
                        continue
                    seen.add(pair_key)
                    pairs.append((m_a, m_b))

    return pairs
