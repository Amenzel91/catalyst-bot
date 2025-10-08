"""
Performance Analytics for Backtesting
======================================

Calculate performance metrics including Sharpe ratio, max drawdown,
win rate, and catalyst-specific performance.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np

from ..logging_utils import get_logger

log = get_logger("backtesting.analytics")


def calculate_sharpe_ratio(
    returns: List[float], risk_free_rate: float = 0.02, periods_per_year: int = 252
) -> float:
    """
    Calculate Sharpe Ratio.

    Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev of Returns

    Parameters
    ----------
    returns : list of float
        List of period returns (e.g., daily returns)
    risk_free_rate : float
        Annual risk-free rate (default: 0.02 = 2%)
    periods_per_year : int
        Number of periods per year (252 for daily, 12 for monthly)

    Returns
    -------
    float
        Annualized Sharpe ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)

    # Calculate mean and std dev
    mean_return = np.mean(returns_array)
    std_return = np.std(returns_array, ddof=1)

    if std_return == 0:
        return 0.0

    # Annualize
    annual_mean_return = mean_return * periods_per_year
    annual_std_return = std_return * math.sqrt(periods_per_year)

    # Calculate Sharpe ratio
    sharpe = (annual_mean_return - risk_free_rate) / annual_std_return

    log.debug(
        "sharpe_calculated sharpe=%.2f mean_return=%.4f std_return=%.4f",
        sharpe,
        annual_mean_return,
        annual_std_return,
    )

    return sharpe


def calculate_max_drawdown(equity_curve: List[Tuple[int, float]]) -> Dict:
    """
    Calculate maximum drawdown (peak-to-trough decline).

    Parameters
    ----------
    equity_curve : list of tuple
        List of (timestamp, equity_value) tuples

    Returns
    -------
    dict
        {
            'max_drawdown_pct': float,
            'peak_value': float,
            'trough_value': float,
            'peak_date': str,
            'trough_date': str,
            'recovery_date': str or None,
            'drawdown_duration_days': float,
            'recovery_duration_days': float or None
        }
    """
    if not equity_curve or len(equity_curve) < 2:
        return {
            "max_drawdown_pct": 0.0,
            "peak_value": 0.0,
            "trough_value": 0.0,
            "peak_date": None,
            "trough_date": None,
            "recovery_date": None,
            "drawdown_duration_days": 0.0,
            "recovery_duration_days": None,
        }

    max_drawdown_pct = 0.0
    peak_value = equity_curve[0][1]
    trough_value = equity_curve[0][1]
    peak_timestamp = equity_curve[0][0]
    trough_timestamp = equity_curve[0][0]
    recovery_timestamp = None

    current_peak = equity_curve[0][1]
    current_peak_timestamp = equity_curve[0][0]

    for timestamp, value in equity_curve:
        # Update peak
        if value > current_peak:
            current_peak = value
            current_peak_timestamp = timestamp

        # Calculate current drawdown
        if current_peak > 0:
            current_drawdown = ((current_peak - value) / current_peak) * 100

            # Update max drawdown
            if current_drawdown > max_drawdown_pct:
                max_drawdown_pct = current_drawdown
                peak_value = current_peak
                trough_value = value
                peak_timestamp = current_peak_timestamp
                trough_timestamp = timestamp
                recovery_timestamp = None  # Reset recovery

        # Check for recovery
        if (
            recovery_timestamp is None
            and trough_timestamp > 0
            and value >= peak_value * 0.99  # Within 1% of peak
        ):
            recovery_timestamp = timestamp

    # Convert timestamps to dates
    peak_date = (
        datetime.fromtimestamp(peak_timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        if peak_timestamp
        else None
    )
    trough_date = (
        datetime.fromtimestamp(trough_timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        if trough_timestamp
        else None
    )
    recovery_date = (
        datetime.fromtimestamp(recovery_timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        if recovery_timestamp
        else None
    )

    # Calculate durations
    drawdown_duration_days = (
        (trough_timestamp - peak_timestamp) / 86400.0
        if trough_timestamp > peak_timestamp
        else 0.0
    )
    recovery_duration_days = (
        (recovery_timestamp - trough_timestamp) / 86400.0
        if recovery_timestamp and recovery_timestamp > trough_timestamp
        else None
    )

    result = {
        "max_drawdown_pct": max_drawdown_pct,
        "peak_value": peak_value,
        "trough_value": trough_value,
        "peak_date": peak_date,
        "trough_date": trough_date,
        "recovery_date": recovery_date,
        "drawdown_duration_days": drawdown_duration_days,
        "recovery_duration_days": recovery_duration_days,
    }

    log.info(
        "max_drawdown_calculated dd_pct=%.2f%% peak=%.2f trough=%.2f duration_days=%.1f",
        max_drawdown_pct,
        peak_value,
        trough_value,
        drawdown_duration_days,
    )

    return result


def calculate_win_rate(trades: List[Dict]) -> Dict:
    """
    Calculate win rate overall and by various dimensions.

    Parameters
    ----------
    trades : list of dict
        List of closed trade dicts

    Returns
    -------
    dict
        {
            'overall': float,
            'by_catalyst': dict,
            'by_score_range': dict,
            'by_hold_time': dict
        }
    """
    if not trades:
        return {
            "overall": 0.0,
            "by_catalyst": {},
            "by_score_range": {},
            "by_hold_time": {},
        }

    # Overall win rate
    wins = sum(1 for t in trades if t.get("profit", 0) > 0)
    total = len(trades)
    overall_win_rate = (wins / total) if total > 0 else 0.0

    # By catalyst type
    by_catalyst: Dict[str, Dict[str, int]] = {}
    for trade in trades:
        catalyst = trade.get("alert_data", {}).get("catalyst_type", "unknown")
        if catalyst not in by_catalyst:
            by_catalyst[catalyst] = {"wins": 0, "total": 0}

        by_catalyst[catalyst]["total"] += 1
        if trade.get("profit", 0) > 0:
            by_catalyst[catalyst]["wins"] += 1

    catalyst_win_rates = {
        cat: (stats["wins"] / stats["total"]) if stats["total"] > 0 else 0.0
        for cat, stats in by_catalyst.items()
    }

    # By score range
    score_ranges = [
        ("0.00-0.25", 0.0, 0.25),
        ("0.25-0.50", 0.25, 0.50),
        ("0.50-0.75", 0.50, 0.75),
        ("0.75-1.00", 0.75, 1.00),
    ]

    by_score: Dict[str, Dict[str, int]] = {}
    for range_name, min_score, max_score in score_ranges:
        by_score[range_name] = {"wins": 0, "total": 0}

        for trade in trades:
            score = trade.get("alert_data", {}).get("score", 0.0)
            if min_score <= score < max_score or (
                max_score == 1.0 and score == 1.0
            ):  # Include 1.0 in last bucket
                by_score[range_name]["total"] += 1
                if trade.get("profit", 0) > 0:
                    by_score[range_name]["wins"] += 1

    score_win_rates = {
        range_name: (stats["wins"] / stats["total"]) if stats["total"] > 0 else 0.0
        for range_name, stats in by_score.items()
    }

    # By hold time
    time_ranges = [
        ("0-1h", 0, 1),
        ("1-4h", 1, 4),
        ("4-12h", 4, 12),
        ("12-24h", 12, 24),
        (">24h", 24, float("inf")),
    ]

    by_time: Dict[str, Dict[str, int]] = {}
    for range_name, min_hours, max_hours in time_ranges:
        by_time[range_name] = {"wins": 0, "total": 0}

        for trade in trades:
            hold_hours = trade.get("hold_time_hours", 0)
            if min_hours <= hold_hours < max_hours:
                by_time[range_name]["total"] += 1
                if trade.get("profit", 0) > 0:
                    by_time[range_name]["wins"] += 1

    time_win_rates = {
        range_name: (stats["wins"] / stats["total"]) if stats["total"] > 0 else 0.0
        for range_name, stats in by_time.items()
    }

    result = {
        "overall": overall_win_rate,
        "by_catalyst": catalyst_win_rates,
        "by_score_range": score_win_rates,
        "by_hold_time": time_win_rates,
    }

    log.info("win_rate_calculated overall=%.2f%%", overall_win_rate * 100)

    return result


def calculate_profit_factor(trades: List[Dict]) -> float:
    """
    Calculate profit factor.

    Profit Factor = Total Gross Profit / Total Gross Loss
    (>1.0 = profitable, >2.0 = very good)

    Parameters
    ----------
    trades : list of dict
        List of closed trade dicts

    Returns
    -------
    float
        Profit factor
    """
    if not trades:
        return 0.0

    gross_profit = sum(t.get("profit", 0) for t in trades if t.get("profit", 0) > 0)
    gross_loss = abs(sum(t.get("profit", 0) for t in trades if t.get("profit", 0) < 0))

    if gross_loss == 0:
        return gross_profit if gross_profit > 0 else 0.0

    profit_factor = gross_profit / gross_loss

    log.info(
        "profit_factor_calculated pf=%.2f gross_profit=%.2f gross_loss=%.2f",
        profit_factor,
        gross_profit,
        gross_loss,
    )

    return profit_factor


def analyze_catalyst_performance(trades: List[Dict]) -> Dict:
    """
    Break down performance by catalyst type.

    Parameters
    ----------
    trades : list of dict
        List of closed trade dicts

    Returns
    -------
    dict
        Performance breakdown by catalyst:
        {
            'fda_approval': {
                'total_trades': int,
                'win_rate': float,
                'avg_return': float,
                'profit_factor': float,
                'avg_hold_hours': float
            },
            ...
        }
    """
    if not trades:
        return {}

    by_catalyst: Dict[str, List[Dict]] = {}

    # Group trades by catalyst
    for trade in trades:
        catalyst = trade.get("alert_data", {}).get("catalyst_type", "unknown")
        if catalyst not in by_catalyst:
            by_catalyst[catalyst] = []
        by_catalyst[catalyst].append(trade)

    # Calculate metrics for each catalyst
    results = {}
    for catalyst, catalyst_trades in by_catalyst.items():
        wins = sum(1 for t in catalyst_trades if t.get("profit", 0) > 0)
        total = len(catalyst_trades)

        win_rate = (wins / total) if total > 0 else 0.0

        avg_return = (
            sum(t.get("profit_pct", 0) for t in catalyst_trades) / total
            if total > 0
            else 0.0
        )

        gross_profit = sum(
            t.get("profit", 0) for t in catalyst_trades if t.get("profit", 0) > 0
        )
        gross_loss = abs(
            sum(t.get("profit", 0) for t in catalyst_trades if t.get("profit", 0) < 0)
        )
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        avg_hold_hours = (
            sum(t.get("hold_time_hours", 0) for t in catalyst_trades) / total
            if total > 0
            else 0.0
        )

        results[catalyst] = {
            "total_trades": total,
            "win_rate": win_rate,
            "avg_return": avg_return,
            "profit_factor": profit_factor,
            "avg_hold_hours": avg_hold_hours,
        }

    log.info("catalyst_performance_analyzed catalysts=%d", len(results))

    return results


def calculate_returns_series(equity_curve: List[Tuple[int, float]]) -> List[float]:
    """
    Calculate period-over-period returns from equity curve.

    Parameters
    ----------
    equity_curve : list of tuple
        List of (timestamp, equity_value) tuples

    Returns
    -------
    list of float
        List of period returns
    """
    if len(equity_curve) < 2:
        return []

    returns = []
    for i in range(1, len(equity_curve)):
        prev_value = equity_curve[i - 1][1]
        curr_value = equity_curve[i][1]

        if prev_value > 0:
            period_return = (curr_value - prev_value) / prev_value
            returns.append(period_return)

    return returns


def calculate_sortino_ratio(
    returns: List[float], risk_free_rate: float = 0.02, periods_per_year: int = 252
) -> float:
    """
    Calculate Sortino Ratio (like Sharpe but only penalizes downside volatility).

    Parameters
    ----------
    returns : list of float
        List of period returns
    risk_free_rate : float
        Annual risk-free rate
    periods_per_year : int
        Number of periods per year

    Returns
    -------
    float
        Annualized Sortino ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)

    # Calculate mean return
    mean_return = np.mean(returns_array)

    # Calculate downside deviation (only negative returns)
    downside_returns = returns_array[returns_array < 0]
    if len(downside_returns) == 0:
        return float("inf") if mean_return > 0 else 0.0

    downside_std = np.std(downside_returns, ddof=1)

    if downside_std == 0:
        return 0.0

    # Annualize
    annual_mean_return = mean_return * periods_per_year
    annual_downside_std = downside_std * math.sqrt(periods_per_year)

    # Calculate Sortino ratio
    sortino = (annual_mean_return - risk_free_rate) / annual_downside_std

    return sortino
