"""
backtest.metrics
================

This module contains utility functions and data structures for summarizing
backtesting results.  Patch B enhances the original metrics to include
additional risk measures such as the Sharpe ratio, Sortino ratio,
profit factor, average win/loss, and trade count.  The goal is to
provide a richer set of statistics for evaluating trading strategies.

The key function ``summarize_returns`` accepts a list or array of trade
returns (percentages) and computes a summary dataclass with both basic
and advanced metrics.  All calculations operate in decimal space (e.g.
5% return = 0.05).  The results can be easily converted to percentages
by multiplying by 100.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional

import numpy as np


@dataclass
class BacktestSummary:
    """Summary statistics for a set of backtest returns.

    Attributes
    ----------
    n : int
        Number of trades.
    hits : int
        Number of profitable trades (>0 return).
    hit_rate : float
        Fraction of profitable trades (hits / n).  NaN if n == 0.
    avg_return : float
        Mean of all trade returns.
    max_drawdown : float
        Maximum drawdown experienced over the equity curve (computed
        cumulatively from returns).  Negative values indicate losses.
    sharpe : float
        Sharpe ratio (mean / std) of returns (annualization omitted).
    sortino : float
        Sortino ratio (mean / downside std).
    profit_factor : float
        Ratio of total profits to total losses.  Infinity if no losses.
    avg_win_loss : float
        Average positive return minus average negative return.
    trade_count : int
        Alias for ``n``.
    """

    n: int
    hits: int
    hit_rate: float
    avg_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    profit_factor: float
    avg_win_loss: float
    trade_count: int


def max_drawdown(returns: Iterable[float]) -> float:
    """Compute maximum drawdown from a sequence of returns.

    Parameters
    ----------
    returns : iterable of float
        Series of trade returns expressed as decimals (e.g., 0.05 for 5%).

    Returns
    -------
    float
        The maximum drawdown (negative number).  Zero if no drawdown.
    """
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= 1.0 + r
        if equity > peak:
            peak = equity
        dd = (equity / peak) - 1.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def summarize_returns(returns: Iterable[float]) -> BacktestSummary:
    """Produce a BacktestSummary from a list of trade returns.

    Parameters
    ----------
    returns : iterable of float
        Returns for each trade, expressed as decimals (not percentages).

    Returns
    -------
    BacktestSummary
        A dataclass with summary metrics.
    """
    rets = np.array(list(returns), dtype=float)
    n = len(rets)
    hits = int((rets > 0).sum()) if n > 0 else 0
    hit_rate = (hits / n) if n > 0 else float("nan")
    avg_ret = float(np.mean(rets)) if n > 0 else float("nan")
    md = max_drawdown(rets) if n > 0 else 0.0
    # Sharpe ratio: mean / std (avoid division by zero)
    if n > 1 and float(np.std(rets, ddof=1)) > 0:
        sharpe_val = float(np.mean(rets) / np.std(rets, ddof=1))
    else:
        sharpe_val = float("nan")
    # Sortino ratio: mean / downside deviation
    downside = rets[rets < 0]
    if len(downside) > 0 and float(np.std(downside, ddof=1)) > 0:
        sortino_val = float(np.mean(rets) / np.std(downside, ddof=1))
    else:
        sortino_val = float("nan")
    # Profit factor: total gains / total losses
    gains = rets[rets > 0].sum()
    losses = -rets[rets < 0].sum()
    if losses > 0:
        profit_factor_val = float(gains / losses)
    else:
        # No losses -> infinite profit factor
        profit_factor_val = float("inf") if gains > 0 else float("nan")
    # Average win minus average loss
    avg_win = float(np.mean(rets[rets > 0])) if hits > 0 else 0.0
    avg_loss = float(np.mean(rets[rets < 0])) if (n - hits) > 0 else 0.0
    avg_win_loss_val = avg_win - abs(avg_loss)
    return BacktestSummary(
        n=n,
        hits=hits,
        hit_rate=hit_rate,
        avg_return=avg_ret,
        max_drawdown=md,
        sharpe=sharpe_val,
        sortino=sortino_val,
        profit_factor=profit_factor_val,
        avg_win_loss=avg_win_loss_val,
        trade_count=n,
    )


# ---------------------------------------------------------------------------
# Legacy backtest summary API
#
# The classes and function below preserve the original Catalyst Bot backtest
# metrics interface so that existing tests and external code can continue
# importing ``HitDefinition``, ``MetricSummary`` and ``summarize_backtest``
# from this module.  They compute simpler statistics used by the
# backtest CLI and older reports.  See the original project for full
# documentation.

# (moved to top with other imports)


@dataclass(frozen=True)
class HitDefinition:
    """Parameterized hit rules for a trade row.

    A hit occurs when either the intraday high return or next day close return
    exceeds the specified minimum thresholds.  ``None`` disables a criterion.
    """

    intraday_high_min: Optional[float] = None
    next_close_min: Optional[float] = None


@dataclass(frozen=True)
class MetricSummary:
    """Simplified summary statistics for legacy backtests.

    Attributes
    ----------
    n : int
        Number of rows/trades.
    hits : int
        Number of rows classified as a hit.
    hit_rate : float
        Fraction of rows classified as hits (hits / n).  Returns 0 if n == 0.
    avg_return : float
        Average of the realized returns in the rows.
    max_drawdown : float
        Maximum drawdown computed from the equity curve generated by
        cumulatively compounding the realized returns.
    """

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


__all__ = [
    "BacktestSummary",
    "max_drawdown",
    "summarize_returns",
    # Legacy API exports
    "HitDefinition",
    "MetricSummary",
    "summarize_backtest",
]
