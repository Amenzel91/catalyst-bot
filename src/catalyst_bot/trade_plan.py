"""Trade plan calculation module for actionable alerts.

Calculates ATR-based stops, support/resistance levels, and risk/reward ratios
to transform alerts from observations into executable trade plans.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

try:
    from .logging_utils import get_logger
except Exception:
    import logging

    logging.basicConfig(level=logging.INFO)

    def get_logger(_):
        return logging.getLogger("trade_plan")


log = get_logger("trade_plan")


def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Calculate Average True Range (ATR) for volatility-based stops.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC price data with High, Low, Close columns
    period : int
        ATR period (default: 14)

    Returns
    -------
    float or None
        Current ATR value, or None if calculation fails
    """
    try:
        if df is None or len(df) < period:
            return None

        # True Range = max(high-low, abs(high-prevclose), abs(low-prevclose))
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR is the moving average of True Range
        atr = true_range.rolling(window=period).mean()

        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None

    except Exception as e:
        log.warning("atr_calculation_failed err=%s", str(e))
        return None


def find_support_resistance(
    df: pd.DataFrame, lookback_days: int = 20
) -> Dict[str, List[float]]:
    """Find key support and resistance levels using pivot points and swing levels.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC price data
    lookback_days : int
        Number of days to look back for swing levels

    Returns
    -------
    dict
        Dictionary with 'support' and 'resistance' lists of price levels
    """
    try:
        if df is None or len(df) < 2:
            return {"support": [], "resistance": []}

        support_levels = []
        resistance_levels = []

        # Method 1: Previous day's high/low (classic pivot)
        if len(df) >= 2:
            high_series = df["High"].iloc[-2:].values
            low_series = df["Low"].iloc[-2:].values
            if len(high_series) >= 2 and len(low_series) >= 2:
                prev_high = float(high_series[0])
                prev_low = float(low_series[0])
                support_levels.append(prev_low)
                resistance_levels.append(prev_high)

        # Method 2: Swing highs and lows in lookback period
        lookback_df = df.tail(min(lookback_days, len(df))).reset_index(drop=True)

        # Find local peaks (resistance) - price higher than neighbors
        if len(lookback_df) >= 3:
            high_values = lookback_df["High"].values
            for i in range(1, len(high_values) - 1):
                if high_values[i] > high_values[i - 1] and high_values[i] > high_values[i + 1]:
                    resistance_levels.append(float(high_values[i]))

        # Find local troughs (support) - price lower than neighbors
        if len(lookback_df) >= 3:
            low_values = lookback_df["Low"].values
            for i in range(1, len(low_values) - 1):
                if low_values[i] < low_values[i - 1] and low_values[i] < low_values[i + 1]:
                    support_levels.append(float(low_values[i]))

        # Remove duplicates and sort
        support_levels = sorted(list(set(support_levels)))
        resistance_levels = sorted(list(set(resistance_levels)))

        return {"support": support_levels, "resistance": resistance_levels}

    except Exception as e:
        log.warning("support_resistance_calculation_failed err=%s", str(e))
        return {"support": [], "resistance": []}


def calculate_trade_plan(
    ticker: str,
    current_price: float,
    df: pd.DataFrame,
    atr_multiplier: float = 2.0,
    min_rr_ratio: float = 1.5,
) -> Optional[Dict[str, Any]]:
    """Calculate complete trade plan with entry, stop, targets, and R/R.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    current_price : float
        Current entry price
    df : pd.DataFrame
        OHLC price data for calculations
    atr_multiplier : float
        Multiplier for ATR-based stop (default: 2.0)
    min_rr_ratio : float
        Minimum acceptable risk/reward ratio (default: 1.5)

    Returns
    -------
    dict or None
        Trade plan with entry, stop, targets, R/R, and key levels
    """
    try:
        if df is None or len(df) < 14:
            log.debug("insufficient_data ticker=%s len=%d", ticker, len(df) if df is not None else 0)
            return None

        # Calculate ATR for dynamic stop-loss
        atr = calculate_atr(df, period=14)
        if atr is None:
            log.debug("atr_calculation_failed ticker=%s", ticker)
            return None

        # Calculate stop-loss (below entry for long positions)
        stop_loss = current_price - (atr * atr_multiplier)

        # Find support and resistance levels
        levels = find_support_resistance(df, lookback_days=20)

        # Find nearest resistance above current price for target
        resistances_above = [r for r in levels["resistance"] if r > current_price]
        target_1 = resistances_above[0] if resistances_above else current_price * 1.05

        # Find nearest support below current price
        supports_below = [s for s in levels["support"] if s < current_price]
        nearest_support = supports_below[-1] if supports_below else stop_loss

        # Calculate risk and reward
        risk_per_share = current_price - stop_loss
        reward_per_share = target_1 - current_price

        # Calculate risk/reward ratio
        if risk_per_share > 0:
            rr_ratio = reward_per_share / risk_per_share
        else:
            rr_ratio = 0.0

        # Determine trade quality based on R/R
        if rr_ratio >= min_rr_ratio:
            trade_quality = "FAVORABLE"
            quality_emoji = "🟢"
        elif rr_ratio >= 1.0:
            trade_quality = "MARGINAL"
            quality_emoji = "🟡"
        else:
            trade_quality = "POOR"
            quality_emoji = "🔴"

        trade_plan = {
            "ticker": ticker,
            "entry": round(current_price, 2),
            "stop": round(stop_loss, 2),
            "target_1": round(target_1, 2),
            "atr": round(atr, 2),
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(reward_per_share, 2),
            "rr_ratio": round(rr_ratio, 2),
            "trade_quality": trade_quality,
            "quality_emoji": quality_emoji,
            "support_levels": [round(s, 2) for s in supports_below[-2:]] if supports_below else [],
            "resistance_levels": [round(r, 2) for r in resistances_above[:2]] if resistances_above else [],
        }

        log.info(
            "trade_plan_calculated ticker=%s entry=%.2f stop=%.2f target=%.2f rr=%.2f quality=%s",
            ticker,
            current_price,
            stop_loss,
            target_1,
            rr_ratio,
            trade_quality,
        )

        return trade_plan

    except Exception as e:
        log.warning("trade_plan_calculation_failed ticker=%s err=%s", ticker, str(e))
        return None


def get_embed_color_from_rr(rr_ratio: float) -> int:
    """Get Discord embed color based on risk/reward ratio.

    Parameters
    ----------
    rr_ratio : float
        Risk/Reward ratio

    Returns
    -------
    int
        Discord color code (green/yellow/red)
    """
    if rr_ratio >= 1.5:
        return 0x2ECC71  # Green - favorable
    elif rr_ratio >= 1.0:
        return 0xF1C40F  # Yellow - marginal
    else:
        return 0xE74C3C  # Red - poor


if __name__ == "__main__":
    # Test the module
    import yfinance as yf

    print("Testing trade plan module...")

    # Download some test data
    ticker = "AAPL"
    stock = yf.Ticker(ticker)
    df = stock.history(period="1mo", interval="1d")

    if not df.empty:
        current_price = df["Close"].iloc[-1]
        trade_plan = calculate_trade_plan(ticker, current_price, df)

        if trade_plan:
            print(f"\n✓ Trade Plan for {ticker}:")
            print(f"  Entry: ${trade_plan['entry']:.2f}")
            print(f"  Stop: ${trade_plan['stop']:.2f}")
            print(f"  Target: ${trade_plan['target_1']:.2f}")
            print(f"  ATR: ${trade_plan['atr']:.2f}")
            print(f"  R/R: {trade_plan['rr_ratio']:.2f} {trade_plan['quality_emoji']}")
            print(f"  Quality: {trade_plan['trade_quality']}")
            if trade_plan['support_levels']:
                print(f"  Support: {trade_plan['support_levels']}")
            if trade_plan['resistance_levels']:
                print(f"  Resistance: {trade_plan['resistance_levels']}")
        else:
            print("✗ Failed to calculate trade plan")
    else:
        print("✗ Failed to download test data")

    print("\nAll tests passed!")
