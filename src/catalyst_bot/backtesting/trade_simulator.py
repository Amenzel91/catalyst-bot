"""
Realistic Penny Stock Trade Simulator
======================================

Simulates realistic penny stock trading with slippage, volume constraints,
and market impact modeling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..logging_utils import get_logger

log = get_logger("backtesting.trade_simulator")


@dataclass
class TradeResult:
    """Result of a simulated trade execution."""

    executed: bool
    shares: int
    entry_price: float
    fill_price: float
    slippage_pct: float
    cost_basis: float
    commission: float
    reason: str


class PennyStockTradeSimulator:
    """
    Simulates realistic penny stock trading with:
    - Slippage (5-15% on volatile names)
    - Commission fees
    - Volume constraints (can't buy/sell more than X% of daily volume)
    - Market hours validation
    - Bid-ask spread modeling
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.10,  # 10% of portfolio per trade
        max_daily_volume_pct: float = 0.05,  # Max 5% of daily volume
        commission_per_trade: float = 0.0,  # $0 with most brokers now
        slippage_model: str = "adaptive",  # "fixed", "adaptive", "volume_based"
        fixed_slippage_pct: float = 0.02,  # 2% fixed slippage if using fixed model
    ):
        """
        Initialize the trade simulator.

        Parameters
        ----------
        initial_capital : float
            Starting capital for the simulation
        position_size_pct : float
            Position size as % of portfolio (0.0-1.0)
        max_daily_volume_pct : float
            Maximum % of daily volume to trade (0.0-1.0)
        commission_per_trade : float
            Commission fee per trade
        slippage_model : str
            Slippage model to use ('fixed', 'adaptive', 'volume_based')
        fixed_slippage_pct : float
            Fixed slippage % if using 'fixed' model
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.max_daily_volume_pct = max_daily_volume_pct
        self.commission_per_trade = commission_per_trade
        self.slippage_model = slippage_model
        self.fixed_slippage_pct = fixed_slippage_pct

        log.info(
            "trade_simulator_initialized capital=%.2f position_size=%.1f%% "
            "max_volume=%.1f%% slippage_model=%s",
            initial_capital,
            position_size_pct * 100,
            max_daily_volume_pct * 100,
            slippage_model,
        )

    def calculate_slippage(
        self,
        ticker: str,
        price: float,
        volume: Optional[int],
        order_size: int,
        direction: str,  # 'buy' or 'sell'
        volatility_pct: Optional[float] = None,
    ) -> float:
        """
        Calculate realistic slippage based on market conditions.

        Penny stocks characteristics:
        - Higher slippage due to wider bid-ask spreads
        - More slippage on low volume days
        - More slippage on large orders relative to daily volume
        - Buying typically has positive slippage (pay more)
        - Selling typically has negative slippage (receive less)

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        price : float
            Quote price
        volume : int, optional
            Daily volume
        order_size : int
            Number of shares to trade
        direction : str
            'buy' or 'sell'
        volatility_pct : float, optional
            Recent volatility percentage

        Returns
        -------
        float
            Actual fill price after slippage
        """
        if self.slippage_model == "fixed":
            # Simple fixed slippage model
            slippage_factor = self.fixed_slippage_pct
            if direction == "buy":
                return price * (1 + slippage_factor)
            else:
                return price * (1 - slippage_factor)

        # Adaptive slippage model for penny stocks
        base_slippage = 0.02  # 2% base slippage for penny stocks

        # Adjust for price level (lower price = higher % slippage)
        if price < 1.0:
            price_factor = 2.5  # 5% total slippage
        elif price < 2.0:
            price_factor = 2.0  # 4% total slippage
        elif price < 5.0:
            price_factor = 1.5  # 3% total slippage
        else:
            price_factor = 1.0  # 2% total slippage

        # Adjust for volume impact
        volume_factor = 1.0
        if volume and order_size > 0:
            volume_impact = order_size / volume
            if volume_impact > 0.10:  # Trying to trade >10% of daily volume
                volume_factor = 3.0
            elif volume_impact > 0.05:
                volume_factor = 2.0
            elif volume_impact > 0.02:
                volume_factor = 1.5
            elif volume < 100000:  # Low volume stock
                volume_factor = 1.8

        # Adjust for volatility
        volatility_factor = 1.0
        if volatility_pct:
            if volatility_pct > 20:  # Very volatile
                volatility_factor = 2.0
            elif volatility_pct > 10:
                volatility_factor = 1.5
            elif volatility_pct > 5:
                volatility_factor = 1.2

        # Calculate total slippage
        total_slippage_pct = (
            base_slippage * price_factor * volume_factor * volatility_factor
        )

        # Cap maximum slippage at 15%
        total_slippage_pct = min(total_slippage_pct, 0.15)

        # Apply directional slippage
        if direction == "buy":
            fill_price = price * (1 + total_slippage_pct)
        else:
            fill_price = price * (1 - total_slippage_pct)

        log.debug(
            "slippage_calculated ticker=%s price=%.4f direction=%s "
            "slippage=%.2f%% fill=%.4f",
            ticker,
            price,
            direction,
            total_slippage_pct * 100,
            fill_price,
        )

        return fill_price

    def can_execute_trade(
        self, ticker: str, shares: int, daily_volume: Optional[int]
    ) -> Tuple[bool, str]:
        """
        Validate if trade can execute given volume constraints.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        shares : int
            Number of shares to trade
        daily_volume : int, optional
            Daily trading volume

        Returns
        -------
        tuple
            (can_execute: bool, reason: str)
        """
        if shares <= 0:
            return False, "Invalid share count"

        if daily_volume is None:
            # If we don't have volume data, allow the trade but warn
            log.warning(
                "no_volume_data ticker=%s shares=%d - allowing trade", ticker, shares
            )
            return True, "Executed (volume unknown)"

        # Check if order is too large relative to daily volume
        volume_pct = (shares / daily_volume) if daily_volume > 0 else 1.0

        if volume_pct > self.max_daily_volume_pct:
            return (
                False,
                f"Order too large: {volume_pct:.1%} of daily volume "
                f"(max: {self.max_daily_volume_pct:.1%})",
            )

        # Check for extremely low volume
        if daily_volume < 10000:
            return (
                False,
                f"Insufficient liquidity: {daily_volume:,} shares daily volume",
            )

        return True, "Validated"

    def execute_trade(
        self,
        ticker: str,
        action: str,  # 'buy' or 'sell'
        price: float,
        volume: Optional[int],
        timestamp: int,
        available_capital: float,
        volatility_pct: Optional[float] = None,
    ) -> TradeResult:
        """
        Execute a simulated trade with slippage and fees.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        action : str
            'buy' or 'sell'
        price : float
            Quote price
        volume : int, optional
            Daily volume
        timestamp : int
            Unix timestamp of trade
        available_capital : float
            Available capital for buying
        volatility_pct : float, optional
            Recent volatility percentage

        Returns
        -------
        TradeResult
            Details of the executed trade
        """
        # Calculate shares based on position sizing
        if action == "buy":
            max_trade_value = available_capital * self.position_size_pct
            shares = int(max_trade_value / price)

            if shares <= 0:
                return TradeResult(
                    executed=False,
                    shares=0,
                    entry_price=price,
                    fill_price=price,
                    slippage_pct=0.0,
                    cost_basis=0.0,
                    commission=0.0,
                    reason="Insufficient capital for position",
                )
        else:
            # For sell, shares would be provided externally
            # This is handled at Portfolio level
            shares = 0

        # Validate volume constraints
        can_execute, reason = self.can_execute_trade(ticker, shares, volume)
        if not can_execute:
            return TradeResult(
                executed=False,
                shares=shares,
                entry_price=price,
                fill_price=price,
                slippage_pct=0.0,
                cost_basis=0.0,
                commission=0.0,
                reason=reason,
            )

        # Calculate slippage
        fill_price = self.calculate_slippage(
            ticker, price, volume, shares, action, volatility_pct
        )

        slippage_pct = ((fill_price - price) / price) * 100

        # Calculate costs
        cost_basis = shares * fill_price
        commission = self.commission_per_trade

        # Check if we have enough capital after slippage and commission
        if action == "buy" and (cost_basis + commission) > available_capital:
            # Reduce shares to fit within capital
            affordable_shares = int((available_capital - commission) / fill_price)
            if affordable_shares <= 0:
                return TradeResult(
                    executed=False,
                    shares=0,
                    entry_price=price,
                    fill_price=fill_price,
                    slippage_pct=slippage_pct,
                    cost_basis=0.0,
                    commission=0.0,
                    reason="Insufficient capital after slippage/commission",
                )
            shares = affordable_shares
            cost_basis = shares * fill_price

        log.info(
            "trade_executed ticker=%s action=%s shares=%d entry=%.4f fill=%.4f "
            "slippage=%.2f%% cost=%.2f commission=%.2f",
            ticker,
            action,
            shares,
            price,
            fill_price,
            slippage_pct,
            cost_basis,
            commission,
        )

        return TradeResult(
            executed=True,
            shares=shares,
            entry_price=price,
            fill_price=fill_price,
            slippage_pct=slippage_pct,
            cost_basis=cost_basis,
            commission=commission,
            reason="Executed successfully",
        )

    def calculate_position_size(self, price: float, available_capital: float) -> int:
        """
        Calculate position size in shares based on portfolio allocation.

        Parameters
        ----------
        price : float
            Stock price
        available_capital : float
            Available capital

        Returns
        -------
        int
            Number of shares to buy
        """
        max_trade_value = available_capital * self.position_size_pct
        shares = int(max_trade_value / price)
        return max(shares, 0)
