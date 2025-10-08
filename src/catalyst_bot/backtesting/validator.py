"""
Parameter Validation System
============================

Validates parameter changes by comparing backtest results before/after.
Helps admins make data-driven decisions about configuration changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from ..logging_utils import get_logger
from .engine import BacktestEngine

log = get_logger("backtesting.validator")


def validate_parameter_change(
    param: str,
    old_value: Any,
    new_value: Any,
    backtest_days: int = 30,
    initial_capital: float = 10000.0,
) -> Dict:
    """
    Run backtest comparing old vs new parameter value.

    Parameters
    ----------
    param : str
        Parameter name (e.g., 'min_score', 'take_profit_pct')
    old_value : Any
        Current parameter value
    new_value : Any
        Proposed new value
    backtest_days : int
        Number of days to backtest (default: 30)
    initial_capital : float
        Starting capital for backtests

    Returns
    -------
    dict
        {
            'param': str,
            'old_value': Any,
            'new_value': Any,
            'old_sharpe': float,
            'new_sharpe': float,
            'old_return_pct': float,
            'new_return_pct': float,
            'old_win_rate': float,
            'new_win_rate': float,
            'old_max_drawdown': float,
            'new_max_drawdown': float,
            'old_total_trades': int,
            'new_total_trades': int,
            'recommendation': str,  # 'APPROVE', 'REJECT', 'NEUTRAL'
            'confidence': float,  # 0.0-1.0
            'reason': str
        }
    """
    log.info(
        "validating_parameter_change param=%s old=%s new=%s days=%d",
        param,
        old_value,
        new_value,
        backtest_days,
    )

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=backtest_days)

    # Run backtest with old value
    log.info("running_backtest_old_value param=%s value=%s", param, old_value)
    old_strategy = {param: old_value}
    old_engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=initial_capital,
        strategy_params=old_strategy,
    )

    try:
        old_results = old_engine.run_backtest()
        old_metrics = old_results["metrics"]
    except Exception as e:
        log.error("backtest_old_value_failed param=%s error=%s", param, str(e))
        return {
            "param": param,
            "old_value": old_value,
            "new_value": new_value,
            "recommendation": "REJECT",
            "confidence": 0.0,
            "reason": f"Old value backtest failed: {str(e)}",
        }

    # Run backtest with new value
    log.info("running_backtest_new_value param=%s value=%s", param, new_value)
    new_strategy = {param: new_value}
    new_engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=initial_capital,
        strategy_params=new_strategy,
    )

    try:
        new_results = new_engine.run_backtest()
        new_metrics = new_results["metrics"]
    except Exception as e:
        log.error("backtest_new_value_failed param=%s error=%s", param, str(e))
        return {
            "param": param,
            "old_value": old_value,
            "new_value": new_value,
            "recommendation": "REJECT",
            "confidence": 0.0,
            "reason": f"New value backtest failed: {str(e)}",
        }

    # Extract key metrics
    old_sharpe = old_metrics.get("sharpe_ratio", 0)
    new_sharpe = new_metrics.get("sharpe_ratio", 0)
    old_return = old_metrics.get("total_return_pct", 0)
    new_return = new_metrics.get("total_return_pct", 0)
    old_win_rate = old_metrics.get("win_rate", 0)
    new_win_rate = new_metrics.get("win_rate", 0)
    old_drawdown = old_metrics.get("max_drawdown_pct", 0)
    new_drawdown = new_metrics.get("max_drawdown_pct", 0)
    old_trades = old_metrics.get("total_trades", 0)
    new_trades = new_metrics.get("total_trades", 0)

    # Determine recommendation
    recommendation, confidence, reason = _evaluate_change(
        old_sharpe=old_sharpe,
        new_sharpe=new_sharpe,
        old_return=old_return,
        new_return=new_return,
        old_win_rate=old_win_rate,
        new_win_rate=new_win_rate,
        old_drawdown=old_drawdown,
        new_drawdown=new_drawdown,
        old_trades=old_trades,
        new_trades=new_trades,
    )

    result = {
        "param": param,
        "old_value": old_value,
        "new_value": new_value,
        "old_sharpe": old_sharpe,
        "new_sharpe": new_sharpe,
        "old_return_pct": old_return,
        "new_return_pct": new_return,
        "old_win_rate": old_win_rate,
        "new_win_rate": new_win_rate,
        "old_max_drawdown": old_drawdown,
        "new_max_drawdown": new_drawdown,
        "old_total_trades": old_trades,
        "new_total_trades": new_trades,
        "recommendation": recommendation,
        "confidence": confidence,
        "reason": reason,
    }

    log.info(
        "validation_complete param=%s recommendation=%s confidence=%.2f reason=%s",
        param,
        recommendation,
        confidence,
        reason,
    )

    return result


def _evaluate_change(
    old_sharpe: float,
    new_sharpe: float,
    old_return: float,
    new_return: float,
    old_win_rate: float,
    new_win_rate: float,
    old_drawdown: float,
    new_drawdown: float,
    old_trades: int,
    new_trades: int,
) -> tuple[str, float, str]:
    """
    Evaluate whether a parameter change should be approved.

    Uses a scoring system based on multiple metrics.

    Returns
    -------
    tuple
        (recommendation: str, confidence: float, reason: str)
    """
    # Calculate improvements
    sharpe_improvement = ((new_sharpe - old_sharpe) / max(abs(old_sharpe), 0.1)) * 100
    return_improvement = new_return - old_return
    win_rate_improvement = new_win_rate - old_win_rate
    drawdown_improvement = old_drawdown - new_drawdown  # Lower is better

    # Score components (weighted)
    sharpe_score = sharpe_improvement * 0.40  # Sharpe is most important
    return_score = return_improvement * 0.30
    win_rate_score = win_rate_improvement * 100 * 0.20  # Convert to same scale
    drawdown_score = drawdown_improvement * 0.10

    total_score = sharpe_score + return_score + win_rate_score + drawdown_score

    # Trade count check
    if new_trades < 10:
        return (
            "REJECT",
            0.3,
            f"Insufficient trades ({new_trades}) for reliable validation. Need at least 10.",
        )

    # Strong approval threshold
    if total_score > 15 and sharpe_improvement > 20:
        confidence = min(0.95, 0.7 + (total_score / 100))
        return (
            "APPROVE",
            confidence,
            f"Strong improvement: Sharpe {sharpe_improvement:+.1f}%, Return {return_improvement:+.1f}%, "  # noqa: E501
            f"Win Rate {win_rate_improvement:+.1f}%",
        )

    # Good approval threshold
    if total_score > 8 and sharpe_improvement > 10:
        confidence = min(0.85, 0.6 + (total_score / 150))
        return (
            "APPROVE",
            confidence,
            f"Good improvement: Sharpe {sharpe_improvement:+.1f}%, Return {return_improvement:+.1f}%, "  # noqa: E501
            f"Win Rate {win_rate_improvement:+.1f}%",
        )

    # Moderate approval threshold
    if total_score > 3 and sharpe_improvement > 0:
        confidence = min(0.70, 0.5 + (total_score / 200))
        return (
            "APPROVE",
            confidence,
            f"Moderate improvement: Sharpe {sharpe_improvement:+.1f}%, Return {return_improvement:+.1f}%",  # noqa: E501
        )

    # Neutral zone
    if -3 <= total_score <= 3:
        confidence = 0.5
        return (
            "NEUTRAL",
            confidence,
            "Minimal impact: No significant improvement or degradation detected",
        )

    # Rejection
    confidence = min(0.80, 0.6 + abs(total_score) / 150)
    return (
        "REJECT",
        confidence,
        f"Performance degradation: Sharpe {sharpe_improvement:+.1f}%, Return {return_improvement:+.1f}%, "  # noqa: E501
        f"Win Rate {win_rate_improvement:+.1f}%",
    )


def validate_multiple_parameters(
    changes: Dict[str, tuple[Any, Any]],
    backtest_days: int = 30,
    initial_capital: float = 10000.0,
) -> Dict:
    """
    Validate multiple parameter changes simultaneously.

    Parameters
    ----------
    changes : dict
        Dict mapping param_name -> (old_value, new_value)
    backtest_days : int
        Number of days to backtest
    initial_capital : float
        Starting capital

    Returns
    -------
    dict
        Combined validation results with overall recommendation
    """
    log.info("validating_multiple_parameters params=%s", list(changes.keys()))

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=backtest_days)

    # Build old and new strategy dicts
    old_strategy = {param: old_val for param, (old_val, new_val) in changes.items()}
    new_strategy = {param: new_val for param, (old_val, new_val) in changes.items()}

    # Run backtests
    old_engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=initial_capital,
        strategy_params=old_strategy,
    )

    new_engine = BacktestEngine(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=initial_capital,
        strategy_params=new_strategy,
    )

    try:
        old_results = old_engine.run_backtest()
        new_results = new_engine.run_backtest()
    except Exception as e:
        log.error("combined_backtest_failed error=%s", str(e))
        return {
            "recommendation": "REJECT",
            "confidence": 0.0,
            "reason": f"Backtest failed: {str(e)}",
        }

    old_metrics = old_results["metrics"]
    new_metrics = new_results["metrics"]

    # Evaluate combined change
    recommendation, confidence, reason = _evaluate_change(
        old_sharpe=old_metrics.get("sharpe_ratio", 0),
        new_sharpe=new_metrics.get("sharpe_ratio", 0),
        old_return=old_metrics.get("total_return_pct", 0),
        new_return=new_metrics.get("total_return_pct", 0),
        old_win_rate=old_metrics.get("win_rate", 0),
        new_win_rate=new_metrics.get("win_rate", 0),
        old_drawdown=old_metrics.get("max_drawdown_pct", 0),
        new_drawdown=new_metrics.get("max_drawdown_pct", 0),
        old_trades=old_metrics.get("total_trades", 0),
        new_trades=new_metrics.get("total_trades", 0),
    )

    result = {
        "parameters": changes,
        "old_metrics": old_metrics,
        "new_metrics": new_metrics,
        "recommendation": recommendation,
        "confidence": confidence,
        "reason": reason,
    }

    log.info(
        "multi_param_validation_complete recommendation=%s confidence=%.2f",
        recommendation,
        confidence,
    )

    return result
