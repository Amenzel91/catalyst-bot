from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class HitDefinition:
    """Parameterized hit rules for a trade row."""

    intraday_high_min: Optional[float] = None
    next_close_min: Optional[float] = None


@dataclass(frozen=True)
class MetricSummary:
    n: int
    hits: int
    hit_rate: float
    avg_return: float
    max_drawdown: float


def _max_drawdown_from_equity(equity_curve: Iterable[float]) -> float:
    """Compute max drawdown from an equity curve."""
    peak = None
    max_dd = 0.0
    for v in equity_curve:
        if peak is None or v > peak:
            peak = v
        if peak is not None:
            dd = (v / peak) - 1.0
            if dd < max_dd:
                max_dd = dd
    return max_dd


def _row_hit(row: Mapping, rule: HitDefinition) -> bool:
    """Return True if the row meets the hit criteria."""
    ih = row.get("intraday_high_return")
    nc = row.get("next_day_close_return")
    if rule.intraday_high_min is not None and isinstance(ih, (int, float)):
        if ih >= rule.intraday_high_min:
            return True
    if rule.next_close_min is not None and isinstance(nc, (int, float)):
        if nc >= rule.next_close_min:
            return True
    return False


def summarize_backtest(rows: List[Mapping], rule: HitDefinition) -> MetricSummary:
    """Summarize a list of trade rows with hit-rate, average return and max drawdown."""
    n = len(rows)
    if n == 0:
        return MetricSummary(
            n=0, hits=0, hit_rate=0.0, avg_return=0.0, max_drawdown=0.0
        )

    hits = 0
    acc = 0.0
    equity = [1.0]
    for r in rows:
        if _row_hit(r, rule):
            hits += 1
        rret = r.get("realized_return", 0.0) or 0.0
        acc += float(rret)
        equity.append(equity[-1] * (1.0 + float(rret)))
    hit_rate = hits / n
    avg_return = acc / n
    max_dd = _max_drawdown_from_equity(equity)
    return MetricSummary(
        n=n, hits=hits, hit_rate=hit_rate, avg_return=avg_return, max_drawdown=max_dd
    )
