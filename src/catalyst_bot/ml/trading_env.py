"""
CatalystTradingEnv: Gymnasium environment for RL-based paper trading.

This module implements a custom Gymnasium (Gym) environment for training RL agents
to trade based on catalyst events. The environment:
  - Uses 33-dimensional state space (price features, sentiment, technical indicators)
  - Supports continuous action space [-1, 1] (position sizing)
  - Rewards based on Sharpe ratio, accounting for transaction costs
  - Integrates with existing catalyst bot infrastructure (market.py, classify.py)

Example usage:
    >>> from catalyst_bot.ml.trading_env import CatalystTradingEnv
    >>> env = CatalystTradingEnv(data_df)
    >>> obs, info = env.reset()
    >>> action = env.action_space.sample()
    >>> obs, reward, terminated, truncated, info = env.step(action)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from ..config import get_settings
from ..logging_utils import get_logger

log = get_logger(__name__)


class CatalystTradingEnv(gym.Env):
    """
    Gymnasium environment for paper trading on catalyst events.

    State Space (33 features):
    --------------------------
    Price Features (7):
        0. last_price (normalized)
        1. price_change_pct (last 1 bar)
        2. volatility_20d (ATR-based)
        3. volume_ratio (current vs 20d avg)
        4. rsi_14 (0-100)
        5. macd (normalized)
        6. bb_position (where price sits in Bollinger Bands, 0-1)

    Sentiment Features (10):
        7. vader_sentiment (-1 to 1)
        8. llm_sentiment (-1 to 1)
        9. ml_sentiment (-1 to 1)
        10. sec_sentiment (-1 to 1)
        11. earnings_sentiment (-1 to 1)
        12. analyst_sentiment (-1 to 1)
        13. social_sentiment (-1 to 1)
        14. premarket_sentiment (-1 to 1)
        15. aftermarket_sentiment (-1 to 1)
        16. combined_sentiment (-1 to 1)

    Catalyst Features (6):
        17. keyword_score (normalized, 0-5+)
        18. catalyst_category_one_hot_0 (FDA)
        19. catalyst_category_one_hot_1 (clinical)
        20. catalyst_category_one_hot_2 (partnership)
        21. catalyst_category_one_hot_3 (offering/negative)
        22. catalyst_category_one_hot_4 (other)

    Market Regime Features (5):
        23. vix_level (normalized, 0-100)
        24. spy_trend (1=bull, 0=neutral, -1=bear)
        25. market_session (0=closed, 0.33=premarket, 0.66=regular, 1=afterhours)
        26. time_of_day (0-1, normalized hour)
        27. day_of_week (0-4, Mon-Fri)

    Position Features (5):
        28. current_position (-1 to 1, current holdings)
        29. unrealized_pnl (normalized)
        30. time_in_position (bars since entry)
        31. portfolio_value (normalized)
        32. cash_available (normalized)

    Action Space:
    -------------
    Continuous [-1, 1]: Position sizing
        -1.0: Full short (not implemented in paper trading, treated as 0)
         0.0: Close/hold no position
        +1.0: Full long (max allowed position size)

    Reward Function:
    ----------------
    Sharpe-ratio based reward with transaction cost penalty:
        reward = (pnl - transaction_costs) / volatility_proxy
        transaction_costs = abs(position_change) * slippage_pct * price

    The Sharpe-based reward encourages risk-adjusted returns and penalizes
    excessive trading.

    Parameters
    ----------
    data_df : pd.DataFrame
        Historical catalyst data with columns: ts_utc, ticker, last_price,
        sentiment_*, keyword_score, etc. (see _extract_features for full list)
    initial_capital : float, optional
        Starting capital for paper trading (default: 10000.0)
    max_position_size : float, optional
        Maximum fraction of portfolio to allocate per position (default: 0.2)
    transaction_cost : float, optional
        Transaction cost as fraction of trade value (default: 0.001 = 0.1%)
    lookback_window : int, optional
        Number of bars to use for rolling calculations (default: 20)
    reward_lookback : int, optional
        Window for calculating Sharpe ratio in reward (default: 10)
    """

    metadata = {"render_modes": ["human", "ansi"]}

    def __init__(
        self,
        data_df: pd.DataFrame,
        initial_capital: float = 10000.0,
        max_position_size: float = 0.2,
        transaction_cost: float = 0.001,
        lookback_window: int = 20,
        reward_lookback: int = 10,
    ):
        super().__init__()

        self.data_df = data_df.copy()
        self.initial_capital = initial_capital
        self.max_position_size = max_position_size
        self.transaction_cost = transaction_cost
        self.lookback_window = lookback_window
        self.reward_lookback = reward_lookback

        # TODO: Validate data_df schema
        # Required columns: ts_utc, ticker, last_price, sentiment columns, etc.
        self._validate_data()

        # Define observation space (33 features)
        # All features normalized to reasonable ranges for RL training
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(33,),
            dtype=np.float32,
        )

        # Define action space (continuous position sizing)
        # [-1, 1] where -1=full short, 0=no position, +1=full long
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(1,),
            dtype=np.float32,
        )

        # Episode state
        self.current_step = 0
        self.current_position = 0.0  # Current position size (-1 to 1)
        self.entry_price = 0.0
        self.cash = initial_capital
        self.portfolio_value = initial_capital
        self.position_history: List[float] = []
        self.pnl_history: List[float] = []
        self.reward_history: List[float] = []

        log.info(
            "trading_env_initialized data_rows=%d initial_capital=%.2f "
            "max_position_size=%.2f transaction_cost=%.4f",
            len(self.data_df),
            initial_capital,
            max_position_size,
            transaction_cost,
        )

    def _validate_data(self) -> None:
        """
        Validate that data_df has required columns for feature extraction.

        Raises
        ------
        ValueError
            If required columns are missing
        """
        # TODO: Implement comprehensive data validation
        # Required columns for 33 features
        required_cols = [
            "ts_utc",
            "ticker",
            "last_price",
            # Sentiment columns
            "sentiment_local",  # VADER
            "sentiment_llm",
            "sentiment_ml",
            "sentiment_sec",
            "sentiment_earnings",
            "sentiment_analyst",
            "sentiment_social",
            "sentiment_premarket",
            "sentiment_aftermarket",
            "sentiment_combined",
            # Catalyst features
            "keyword_score",
            "catalyst_category",  # One-hot encoded
            # Technical indicators (computed if missing)
            # "rsi_14", "macd", etc. - can be computed on the fly
        ]

        missing_cols = [col for col in required_cols if col not in self.data_df.columns]
        if missing_cols:
            log.warning(
                "trading_env_missing_columns missing=%s hint=will_be_computed_if_possible",
                ",".join(missing_cols),
            )
            # Don't raise - we can compute some features on the fly

        # Ensure sorted by timestamp
        if "ts_utc" in self.data_df.columns:
            self.data_df = self.data_df.sort_values("ts_utc").reset_index(drop=True)

    def _extract_features(self, step: int) -> np.ndarray:
        """
        Extract 33-dimensional feature vector for current step.

        Parameters
        ----------
        step : int
            Current timestep index in data_df

        Returns
        -------
        np.ndarray
            33-dimensional feature vector (float32)

        Notes
        -----
        This method handles missing data by filling with zeros or computing
        features on-the-fly using existing catalyst bot utilities.
        """
        # TODO: Implement comprehensive feature extraction
        # This is a critical function that bridges catalyst bot data to RL state

        features = np.zeros(33, dtype=np.float32)

        # Get current row
        row = self.data_df.iloc[step]

        # --- PRICE FEATURES (0-6) ---
        # 0. last_price (normalized by rolling mean)
        price_window = self.data_df.iloc[
            max(0, step - self.lookback_window) : step + 1
        ]["last_price"]
        price_mean = price_window.mean()
        price_std = price_window.std() + 1e-8
        features[0] = (row["last_price"] - price_mean) / price_std

        # 1. price_change_pct (1-bar return)
        if step > 0:
            prev_price = self.data_df.iloc[step - 1]["last_price"]
            features[1] = (row["last_price"] - prev_price) / (prev_price + 1e-8)
        else:
            features[1] = 0.0

        # 2. volatility_20d (rolling std of returns)
        if len(price_window) > 1:
            returns = price_window.pct_change().dropna()
            features[2] = returns.std() * np.sqrt(252)  # Annualized
        else:
            features[2] = 0.0

        # 3. volume_ratio (current / 20d avg)
        # TODO: Integrate with market.py volume data if available
        features[3] = 1.0  # Placeholder

        # 4-6. Technical indicators (RSI, MACD, BB position)
        # TODO: Integrate with market.py get_intraday_indicators()
        # For now, use placeholders
        features[4] = 50.0 / 100.0  # RSI normalized to 0-1
        features[5] = 0.0  # MACD
        features[6] = 0.5  # BB position

        # --- SENTIMENT FEATURES (7-16) ---
        sentiment_cols = [
            "sentiment_local",
            "sentiment_llm",
            "sentiment_ml",
            "sentiment_sec",
            "sentiment_earnings",
            "sentiment_analyst",
            "sentiment_social",
            "sentiment_premarket",
            "sentiment_aftermarket",
            "sentiment_combined",
        ]
        for i, col in enumerate(sentiment_cols, start=7):
            features[i] = row.get(col, 0.0)

        # --- CATALYST FEATURES (17-22) ---
        # 17. keyword_score (normalized)
        keyword_score = row.get("keyword_score", 0.0)
        features[17] = np.clip(keyword_score / 5.0, 0.0, 1.0)

        # 18-22. catalyst_category one-hot encoding
        catalyst_category = row.get("catalyst_category", "other")
        category_map = {
            "fda": 18,
            "clinical": 19,
            "partnership": 20,
            "offering": 21,
            "other": 22,
        }
        idx = category_map.get(catalyst_category.lower(), 22)
        features[idx] = 1.0

        # --- MARKET REGIME FEATURES (23-27) ---
        # TODO: Integrate with market regime classifier (VIX, SPY trend)
        features[23] = 0.2  # VIX normalized (20/100)
        features[24] = 0.0  # SPY trend (neutral)
        features[25] = 0.66  # Market session (regular hours)

        # Time features
        from datetime import datetime

        ts = row.get("ts_utc", datetime.now())
        if isinstance(ts, str):
            ts = pd.to_datetime(ts)
        features[26] = ts.hour / 24.0  # Time of day
        features[27] = ts.weekday() / 4.0  # Day of week

        # --- POSITION FEATURES (28-32) ---
        features[28] = self.current_position
        features[29] = self._calculate_unrealized_pnl(row["last_price"]) / self.initial_capital
        features[30] = len(self.position_history) / 100.0  # Normalized time in position
        features[31] = self.portfolio_value / self.initial_capital - 1.0  # Portfolio return
        features[32] = self.cash / self.initial_capital

        return features

    def _calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L for current position.

        Parameters
        ----------
        current_price : float
            Current market price

        Returns
        -------
        float
            Unrealized P&L in dollars
        """
        if self.current_position == 0.0 or self.entry_price == 0.0:
            return 0.0

        position_size_dollars = abs(self.current_position) * self.initial_capital
        shares = position_size_dollars / self.entry_price
        unrealized_pnl = shares * (current_price - self.entry_price)

        return unrealized_pnl * np.sign(self.current_position)

    def _calculate_reward(
        self,
        action: float,
        prev_portfolio_value: float,
        current_price: float,
        prev_price: float,
    ) -> float:
        """
        Calculate Sharpe-ratio based reward with transaction cost penalty.

        Reward Design:
        --------------
        The reward function encourages risk-adjusted returns while penalizing
        excessive trading. It uses a rolling Sharpe ratio as the base reward,
        then subtracts transaction costs.

        Formula:
            pnl = portfolio_value - prev_portfolio_value
            volatility = std(returns over reward_lookback window)
            sharpe = pnl / (volatility + eps)
            transaction_cost = abs(position_change) * transaction_cost_pct * price
            reward = sharpe - transaction_cost_penalty

        Parameters
        ----------
        action : float
            Action taken (position change)
        prev_portfolio_value : float
            Portfolio value before action
        current_price : float
            Current market price
        prev_price : float
            Previous market price

        Returns
        -------
        float
            Reward value (Sharpe-adjusted with transaction costs)
        """
        # TODO: Implement sophisticated reward function
        # Current implementation is a placeholder

        # Calculate P&L from action
        pnl = self.portfolio_value - prev_portfolio_value

        # Calculate transaction costs
        position_change = abs(action - self.current_position)
        trade_value = position_change * self.initial_capital * self.max_position_size
        transaction_cost_dollars = trade_value * self.transaction_cost

        # Calculate Sharpe ratio (rolling)
        if len(self.pnl_history) >= self.reward_lookback:
            recent_pnl = self.pnl_history[-self.reward_lookback :]
            pnl_mean = np.mean(recent_pnl)
            pnl_std = np.std(recent_pnl) + 1e-8
            sharpe = pnl_mean / pnl_std
        else:
            # Not enough history, use simple PnL
            sharpe = pnl / (self.initial_capital * 0.01 + 1e-8)

        # Combine Sharpe ratio with transaction cost penalty
        reward = sharpe - (transaction_cost_dollars / self.initial_capital) * 10.0

        # Clip reward to prevent explosion
        reward = np.clip(reward, -10.0, 10.0)

        return float(reward)

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Execute one timestep in the environment.

        Parameters
        ----------
        action : np.ndarray
            Action from agent (position sizing, -1 to 1)

        Returns
        -------
        observation : np.ndarray
            Next state (33 features)
        reward : float
            Reward for the action
        terminated : bool
            Whether episode ended (end of data or bankruptcy)
        truncated : bool
            Whether episode was truncated (not used here)
        info : dict
            Additional information (pnl, position, etc.)
        """
        # Validate action
        action_value = float(np.clip(action[0], -1.0, 1.0))

        # Store previous state for reward calculation
        prev_portfolio_value = self.portfolio_value
        prev_position = self.current_position

        # Get current and previous price
        current_row = self.data_df.iloc[self.current_step]
        current_price = current_row["last_price"]

        prev_price = (
            self.data_df.iloc[self.current_step - 1]["last_price"]
            if self.current_step > 0
            else current_price
        )

        # Execute trade (position change)
        position_change = action_value - self.current_position
        trade_value = (
            abs(position_change) * self.initial_capital * self.max_position_size
        )
        transaction_cost_dollars = trade_value * self.transaction_cost

        # Update position
        self.current_position = action_value

        # Update entry price if entering/adding to position
        if abs(action_value) > abs(prev_position):
            self.entry_price = current_price

        # Calculate P&L from price movement
        if prev_position != 0.0 and self.entry_price > 0:
            position_size_dollars = abs(prev_position) * self.initial_capital * self.max_position_size
            shares = position_size_dollars / self.entry_price
            pnl = shares * (current_price - prev_price) * np.sign(prev_position)
            self.cash += pnl

        # Deduct transaction costs
        self.cash -= transaction_cost_dollars

        # Update portfolio value
        unrealized_pnl = self._calculate_unrealized_pnl(current_price)
        self.portfolio_value = self.cash + unrealized_pnl

        # Record history
        self.position_history.append(self.current_position)
        self.pnl_history.append(self.portfolio_value - prev_portfolio_value)

        # Calculate reward
        reward = self._calculate_reward(
            action_value, prev_portfolio_value, current_price, prev_price
        )
        self.reward_history.append(reward)

        # Move to next step
        self.current_step += 1

        # Check termination conditions
        terminated = False
        if self.current_step >= len(self.data_df):
            terminated = True
            log.info("trading_env_episode_end reason=data_exhausted")
        elif self.portfolio_value <= 0.0:
            terminated = True
            log.warning("trading_env_episode_end reason=bankruptcy")

        # Get next observation
        observation = (
            self._extract_features(self.current_step)
            if not terminated
            else np.zeros(33, dtype=np.float32)
        )

        # Additional info
        info = {
            "portfolio_value": self.portfolio_value,
            "cash": self.cash,
            "position": self.current_position,
            "pnl": self.portfolio_value - self.initial_capital,
            "return_pct": (self.portfolio_value / self.initial_capital - 1.0) * 100.0,
            "transaction_cost": transaction_cost_dollars,
            "current_price": current_price,
            "step": self.current_step,
        }

        return observation, reward, terminated, False, info

    def reset(
        self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reset the environment to initial state.

        Parameters
        ----------
        seed : int, optional
            Random seed for reproducibility
        options : dict, optional
            Additional reset options

        Returns
        -------
        observation : np.ndarray
            Initial state (33 features)
        info : dict
            Additional information
        """
        super().reset(seed=seed)

        # Reset episode state
        self.current_step = 0
        self.current_position = 0.0
        self.entry_price = 0.0
        self.cash = self.initial_capital
        self.portfolio_value = self.initial_capital
        self.position_history = []
        self.pnl_history = []
        self.reward_history = []

        # Get initial observation
        observation = self._extract_features(0)

        info = {
            "portfolio_value": self.portfolio_value,
            "cash": self.cash,
            "position": self.current_position,
        }

        log.debug("trading_env_reset initial_capital=%.2f", self.initial_capital)

        return observation, info

    def render(self, mode: str = "human") -> Optional[str]:
        """
        Render the environment state.

        Parameters
        ----------
        mode : str, optional
            Render mode ("human" for console, "ansi" for string)

        Returns
        -------
        str or None
            Rendered output (if mode="ansi")
        """
        # TODO: Implement rich rendering (equity curve, position plot, etc.)

        if self.current_step >= len(self.data_df):
            return None

        row = self.data_df.iloc[self.current_step]
        output = (
            f"Step: {self.current_step}/{len(self.data_df)} | "
            f"Ticker: {row.get('ticker', 'N/A')} | "
            f"Price: ${row['last_price']:.2f} | "
            f"Position: {self.current_position:.2f} | "
            f"Portfolio: ${self.portfolio_value:.2f} | "
            f"PnL: ${self.portfolio_value - self.initial_capital:+.2f} "
            f"({(self.portfolio_value/self.initial_capital - 1)*100:+.2f}%)"
        )

        if mode == "human":
            print(output)
        elif mode == "ansi":
            return output

        return None

    def close(self) -> None:
        """Clean up environment resources."""
        log.debug("trading_env_closed")
        pass
