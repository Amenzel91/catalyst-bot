"""
Portfolio Manager for Backtesting
==================================

Tracks portfolio state during backtest including cash, positions,
trades, and performance metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from ..logging_utils import get_logger

log = get_logger("backtesting.portfolio")


@dataclass
class Position:
    """Represents an open position."""

    ticker: str
    shares: int
    entry_price: float
    entry_time: int
    cost_basis: float
    alert_data: Dict
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    def update_price(self, current_price: float) -> None:
        """Update position with current market price."""
        self.current_price = current_price
        self.unrealized_pnl = (current_price - self.entry_price) * self.shares
        self.unrealized_pnl_pct = (
            (current_price - self.entry_price) / self.entry_price
        ) * 100


@dataclass
class ClosedTrade:
    """Represents a closed trade with full P&L details."""

    ticker: str
    shares: int
    entry_price: float
    exit_price: float
    entry_time: int
    exit_time: int
    profit: float
    profit_pct: float
    hold_time_hours: float
    exit_reason: str
    alert_data: Dict
    commission: float = 0.0


class Portfolio:
    """
    Tracks portfolio state during backtest:
    - Cash balance
    - Open positions
    - Historical trades
    - Performance metrics
    """

    def __init__(self, initial_capital: float = 10000.0):
        """
        Initialize portfolio.

        Parameters
        ----------
        initial_capital : float
            Starting capital
        """
        self.cash = initial_capital
        self.initial_capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.equity_curve: List[tuple[int, float]] = []
        self.peak_value = initial_capital
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0

        log.info("portfolio_initialized capital=%.2f", initial_capital)

    def open_position(
        self,
        ticker: str,
        shares: int,
        entry_price: float,
        entry_time: int,
        alert_data: Dict,
        commission: float = 0.0,
    ) -> bool:
        """
        Open a new position.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        shares : int
            Number of shares
        entry_price : float
            Entry price per share (after slippage)
        entry_time : int
            Unix timestamp of entry
        alert_data : Dict
            Alert metadata (score, sentiment, catalysts, etc.)
        commission : float
            Commission paid

        Returns
        -------
        bool
            True if position opened successfully
        """
        if ticker in self.positions:
            log.warning("position_already_open ticker=%s - skipping", ticker)
            return False

        cost_basis = (shares * entry_price) + commission

        if cost_basis > self.cash:
            log.warning(
                "insufficient_capital ticker=%s cost=%.2f cash=%.2f",
                ticker,
                cost_basis,
                self.cash,
            )
            return False

        # Deduct from cash
        self.cash -= cost_basis

        # Create position
        position = Position(
            ticker=ticker,
            shares=shares,
            entry_price=entry_price,
            entry_time=entry_time,
            cost_basis=cost_basis,
            alert_data=alert_data,
            current_price=entry_price,
        )

        self.positions[ticker] = position

        log.info(
            "position_opened ticker=%s shares=%d entry=%.4f cost=%.2f cash=%.2f",
            ticker,
            shares,
            entry_price,
            cost_basis,
            self.cash,
        )

        return True

    def close_position(
        self,
        ticker: str,
        exit_price: float,
        exit_time: int,
        exit_reason: str,
        commission: float = 0.0,
    ) -> Optional[ClosedTrade]:
        """
        Close position and record trade results.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        exit_price : float
            Exit price per share (after slippage)
        exit_time : int
            Unix timestamp of exit
        exit_reason : str
            Reason for exit ('take_profit', 'stop_loss', 'time_exit', etc.)
        commission : float
            Commission paid on exit

        Returns
        -------
        ClosedTrade or None
            Trade details if successful, None otherwise
        """
        if ticker not in self.positions:
            log.warning("position_not_found ticker=%s - cannot close", ticker)
            return None

        position = self.positions[ticker]

        # Calculate proceeds (after commission)
        proceeds = (position.shares * exit_price) - commission

        # Add proceeds to cash
        self.cash += proceeds

        # Calculate profit
        profit = proceeds - position.cost_basis
        profit_pct = (profit / position.cost_basis) * 100

        # Calculate hold time
        hold_time_hours = (exit_time - position.entry_time) / 3600.0

        # Create closed trade record
        trade = ClosedTrade(
            ticker=ticker,
            shares=position.shares,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            profit=profit,
            profit_pct=profit_pct,
            hold_time_hours=hold_time_hours,
            exit_reason=exit_reason,
            alert_data=position.alert_data,
            commission=commission,
        )

        self.closed_trades.append(trade)

        # Remove from open positions
        del self.positions[ticker]

        log.info(
            "position_closed ticker=%s exit=%.4f profit=%.2f profit_pct=%.2f%% "
            "hold_hours=%.1f reason=%s cash=%.2f",
            ticker,
            exit_price,
            profit,
            profit_pct,
            hold_time_hours,
            exit_reason,
            self.cash,
        )

        return trade

    def update_position_prices(self, current_prices: Dict[str, float]) -> None:
        """
        Update all positions with current market prices.

        Parameters
        ----------
        current_prices : dict
            Dict mapping ticker -> current_price
        """
        for ticker, position in self.positions.items():
            if ticker in current_prices:
                position.update_price(current_prices[ticker])

    def calculate_total_value(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total portfolio value (cash + positions).

        Parameters
        ----------
        current_prices : dict
            Dict mapping ticker -> current_price

        Returns
        -------
        float
            Total portfolio value
        """
        # Update positions first
        self.update_position_prices(current_prices)

        # Sum position values
        positions_value = sum(
            pos.shares * pos.current_price for pos in self.positions.values()
        )

        total_value = self.cash + positions_value

        # Update drawdown metrics
        if total_value > self.peak_value:
            self.peak_value = total_value
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = (
                (self.peak_value - total_value) / self.peak_value
            ) * 100
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown

        return total_value

    def record_equity_point(
        self, timestamp: int, current_prices: Dict[str, float]
    ) -> None:
        """
        Record a point on the equity curve.

        Parameters
        ----------
        timestamp : int
            Unix timestamp
        current_prices : dict
            Current market prices
        """
        total_value = self.calculate_total_value(current_prices)
        self.equity_curve.append((timestamp, total_value))

    def get_performance_metrics(self) -> Dict:
        """
        Calculate portfolio performance metrics.

        Returns
        -------
        dict
            Performance metrics including:
            - total_return_pct: Total return percentage
            - total_profit: Total profit in dollars
            - win_rate: Percentage of winning trades
            - avg_win: Average winning trade %
            - avg_loss: Average losing trade %
            - profit_factor: Gross profit / gross loss
            - max_drawdown_pct: Maximum drawdown
            - total_trades: Number of closed trades
            - winning_trades: Number of winners
            - losing_trades: Number of losers
            - avg_hold_time_hours: Average hold time
        """
        if not self.closed_trades:
            return {
                "total_return_pct": 0.0,
                "total_profit": 0.0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "avg_hold_time_hours": 0.0,
            }

        # Calculate total return
        current_value = self.cash + sum(
            pos.cost_basis for pos in self.positions.values()
        )
        total_return_pct = (
            (current_value - self.initial_capital) / self.initial_capital
        ) * 100
        total_profit = current_value - self.initial_capital

        # Separate wins and losses
        wins = [t for t in self.closed_trades if t.profit > 0]
        losses = [t for t in self.closed_trades if t.profit < 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        total_trades = len(self.closed_trades)

        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0

        # Average win/loss
        avg_win = sum(t.profit_pct for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t.profit_pct for t in losses) / len(losses) if losses else 0.0

        # Profit factor
        gross_profit = sum(t.profit for t in wins)
        gross_loss = abs(sum(t.profit for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Average hold time
        avg_hold_time_hours = (
            sum(t.hold_time_hours for t in self.closed_trades) / total_trades
            if total_trades > 0
            else 0.0
        )

        return {
            "total_return_pct": total_return_pct,
            "total_profit": total_profit,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown_pct": self.max_drawdown,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_hold_time_hours": avg_hold_time_hours,
        }

    def get_trades_by_catalyst(self) -> Dict[str, List[ClosedTrade]]:
        """
        Group closed trades by catalyst type.

        Returns
        -------
        dict
            Dict mapping catalyst_type -> list of trades
        """
        by_catalyst: Dict[str, List[ClosedTrade]] = {}

        for trade in self.closed_trades:
            catalyst = trade.alert_data.get("catalyst_type", "unknown")
            if catalyst not in by_catalyst:
                by_catalyst[catalyst] = []
            by_catalyst[catalyst].append(trade)

        return by_catalyst

    def get_summary(self) -> Dict:
        """
        Get portfolio summary including current positions and metrics.

        Returns
        -------
        dict
            Portfolio summary
        """
        metrics = self.get_performance_metrics()

        return {
            "cash": self.cash,
            "initial_capital": self.initial_capital,
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed_trades),
            "metrics": metrics,
        }
