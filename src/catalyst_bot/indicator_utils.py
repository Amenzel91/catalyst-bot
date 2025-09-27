"""
indicator_utils.py
===================

This module contains a collection of technical indicator functions used to
support enhanced analytics in Catalyst Bot.  The functions here compute
popular technical indicators such as Average True Range (ATR), Bollinger
Bands, On‑Balance Volume (OBV), the Average Directional Index (ADX), and
a composite indicator score.  These indicators operate on pandas
DataFrames with columns ``Open``, ``High``, ``Low``, ``Close`` and
``Volume``.  The composite score aggregates multiple indicators into
a single number between 0 and 100, where higher values indicate stronger
momentum and volatility alignment.

The implementations below are intentionally self‑contained and avoid
external dependencies beyond pandas and numpy.  They return ``None`` or
``NaN`` when insufficient data is provided to compute the requested
indicator.  Callers are expected to handle missing values gracefully.
"""

from __future__ import annotations

import math
from typing import Tuple, Optional

import numpy as np
import pandas as pd

def compute_atr(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """Return the Average True Range (ATR) for a price DataFrame.

    ATR measures volatility by averaging the range of each bar over the
    specified period.  The DataFrame must contain 'High', 'Low' and
    'Close' columns.  If the DataFrame is empty or too short, returns
    ``None``.

    Parameters
    ----------
    df : pandas.DataFrame
        The OHLCV price data with at least 'High', 'Low', 'Close' columns.
    period : int, optional
        The rolling window length, by default 14.

    Returns
    -------
    pandas.Series or None
        A Series of ATR values aligned with ``df`` or ``None`` if not
        enough data is available.
    """
    if df is None or df.empty or not {'High', 'Low', 'Close'}.issubset(df.columns):
        return None
    high = df['High']
    low = df['Low']
    close = df['Close']
    # True range is the maximum of (high-low), abs(high-prev_close), abs(low-prev_close)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's smoothing: use exponential moving average of true range
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


def compute_bollinger_bands(
    df: pd.DataFrame, period: int = 20, num_std: float = 2.0
) -> Optional[Tuple[pd.Series, pd.Series, pd.Series]]:
    """Compute Bollinger Bands for the given price DataFrame.

    The Bollinger Bands consist of a middle band (simple moving average),
    an upper band and a lower band at ``num_std`` standard deviations from
    the middle.  Requires a 'Close' column.  Returns ``None`` if
    insufficient data is available.

    Parameters
    ----------
    df : pandas.DataFrame
        The OHLCV data with a 'Close' column.
    period : int
        The length of the moving average window.
    num_std : float
        The number of standard deviations above and below the moving
        average for the bands.

    Returns
    -------
    tuple (mid, upper, lower) or None
        A tuple of Series representing the middle, upper and lower bands.
    """
    if df is None or df.empty or 'Close' not in df.columns:
        return None
    close = df['Close']
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def compute_obv(df: pd.DataFrame) -> Optional[pd.Series]:
    """Compute the On‑Balance Volume (OBV) indicator.

    OBV uses volume to measure buying and selling pressure.  It cumulates
    volume when price closes higher than the previous close and subtracts
    volume when it closes lower.  A DataFrame with 'Close' and 'Volume'
    columns is required.

    Returns ``None`` if data is missing or insufficient.
    """
    if df is None or df.empty or not {'Close', 'Volume'}.issubset(df.columns):
        return None
    close = df['Close']
    volume = df['Volume']
    direction = np.sign(close.diff().fillna(0.0))
    obv = (direction * volume).fillna(0).cumsum()
    return obv


def compute_adx(df: pd.DataFrame, period: int = 14) -> Optional[pd.Series]:
    """Return the Average Directional Index (ADX).

    ADX quantifies trend strength by measuring the spread between positive
    and negative directional movements over a rolling window.  Requires
    'High', 'Low', 'Close' columns.  Returns None if data is missing.
    """
    required = {'High', 'Low', 'Close'}
    if df is None or df.empty or not required.issubset(df.columns):
        return None
    high = df['High']
    low = df['Low']
    close = df['Close']
    # Compute directional movement
    up_move = high.diff()
    down_move = low.diff().abs() * -1  # negative downward move
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), -down_move, 0.0)
    # True range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Smooth values using Wilder's smoothing
    atr = tr.rolling(window=period, min_periods=period).mean()
    plus_di = (100 * pd.Series(plus_dm).rolling(window=period, min_periods=period).sum() / atr)
    minus_di = (100 * pd.Series(minus_dm).rolling(window=period, min_periods=period).sum() / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(window=period, min_periods=period).mean()
    return adx


def compute_composite_score(
    df: pd.DataFrame,
    *,
    atr_weight: float = 0.2,
    obv_weight: float = 0.2,
    adx_weight: float = 0.3,
    bb_weight: float = 0.3,
) -> Optional[float]:
    """Compute a composite indicator score from multiple indicators.

    The composite score aggregates normalized values of ATR, OBV, ADX and
    Bollinger Band width.  The weights determine the relative importance
    of each component.  The result is scaled to 0–100.  Returns ``None`` if
    any required indicator cannot be computed.

    Parameters
    ----------
    df : pandas.DataFrame
        OHLCV data with 'High', 'Low', 'Close', 'Volume' columns.
    atr_weight, obv_weight, adx_weight, bb_weight : float
        Weights for ATR, OBV, ADX and Bollinger Band width, respectively.
        The weights should sum to 1.0; if not, they will be renormalized.

    Returns
    -------
    float or None
        Composite score in the range 0–100 or ``None`` if computation fails.
    """
    required = {'High', 'Low', 'Close', 'Volume'}
    if df is None or df.empty or not required.issubset(df.columns):
        return None
    # Compute individual indicators (take the last available value)
    atr_series = compute_atr(df)
    obv_series = compute_obv(df)
    adx_series = compute_adx(df)
    bb = compute_bollinger_bands(df)
    if atr_series is None or obv_series is None or adx_series is None or bb is None:
        return None
    mid, upper, lower = bb
    # Last values
    try:
        atr_val = float(atr_series.dropna().iloc[-1])
        obv_val = float(obv_series.dropna().iloc[-1])
        adx_val = float(adx_series.dropna().iloc[-1])
        bb_width_val = float(((upper - lower).dropna()).iloc[-1])
    except Exception:
        return None
    # Normalize each component to 0–1 range (simple z‑score approach)
    # For demonstration, we apply log scaling to ATR and OBV to mitigate large ranges.
    try:
        atr_norm = math.tanh(math.log1p(abs(atr_val)))  # 0–1 after tanh
        obv_norm = math.tanh(math.log1p(abs(obv_val)))
        adx_norm = adx_val / 100.0  # ADX already between 0 and ~100
        bb_norm = math.tanh(math.log1p(abs(bb_width_val)))
    except Exception:
        return None
    weights = np.array([atr_weight, obv_weight, adx_weight, bb_weight], dtype=float)
    # Renormalize weights if sum differs from 1
    wsum = weights.sum()
    if not np.isclose(wsum, 1.0):
        weights = weights / wsum
    comps = np.array([atr_norm, obv_norm, adx_norm, bb_norm], dtype=float)
    score = float((weights * comps).sum() * 100.0)
    return score


__all__ = [
    'compute_atr',
    'compute_bollinger_bands',
    'compute_obv',
    'compute_adx',
    'compute_composite_score',
]