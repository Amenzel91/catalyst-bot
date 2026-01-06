"""
Position Manager Module

This module manages open trading positions and tracks profit/loss.

Key responsibilities:
- Track open positions
- Calculate real-time P&L
- Update positions with current prices
- Monitor stop-loss triggers
- Close positions
- Maintain position history
- Calculate portfolio-level metrics

Database Schema:
    CREATE TABLE IF NOT EXISTS positions (
        position_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL,  -- 'long' or 'short'
        quantity INTEGER NOT NULL,
        entry_price REAL NOT NULL,
        current_price REAL NOT NULL,
        cost_basis REAL NOT NULL,
        market_value REAL NOT NULL,
        unrealized_pnl REAL NOT NULL,
        unrealized_pnl_pct REAL NOT NULL,
        stop_loss_price REAL,
        take_profit_price REAL,
        opened_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        entry_order_id TEXT,
        signal_id TEXT,
        strategy TEXT,
        metadata JSON
    );

    CREATE TABLE IF NOT EXISTS closed_positions (
        position_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL NOT NULL,
        cost_basis REAL NOT NULL,
        realized_pnl REAL NOT NULL,
        realized_pnl_pct REAL NOT NULL,
        opened_at TIMESTAMP NOT NULL,
        closed_at TIMESTAMP NOT NULL,
        hold_duration_seconds INTEGER NOT NULL,
        exit_reason TEXT,  -- 'stop_loss', 'take_profit', 'manual', 'timeout'
        exit_order_id TEXT,
        entry_order_id TEXT,
        signal_id TEXT,
        strategy TEXT,
        metadata JSON
    );

    CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
    CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at);
    CREATE INDEX IF NOT EXISTS idx_closed_positions_ticker ON closed_positions(ticker);
    CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at ON closed_positions(closed_at);
    CREATE INDEX IF NOT EXISTS idx_closed_positions_strategy ON closed_positions(strategy);
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from ..broker.broker_interface import BrokerInterface, Order, PositionSide
from ..config import get_settings
from ..logging_utils import get_logger
from ..time_utils import now as sim_now

logger = get_logger(__name__)


# ============================================================================
# Type Definitions
# ============================================================================


@dataclass
class ManagedPosition:
    """
    Represents a managed trading position with additional metadata.

    This extends the broker's Position with our tracking information.
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide

    # Quantities
    quantity: int
    entry_price: Decimal
    current_price: Decimal

    # Valuation
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal

    # Risk management
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None

    # Timestamps
    opened_at: datetime = field(default_factory=sim_now)
    updated_at: datetime = field(default_factory=sim_now)

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss"""
        if not self.stop_loss_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss_price
        else:  # SHORT
            return self.current_price >= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit"""
        if not self.take_profit_price:
            return False

        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit_price
        else:  # SHORT
            return self.current_price <= self.take_profit_price

    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held"""
        return sim_now() - self.opened_at

    def calculate_risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio"""
        if not self.stop_loss_price or not self.take_profit_price:
            return None

        if self.side == PositionSide.LONG:
            risk = abs(self.entry_price - self.stop_loss_price)
            reward = abs(self.take_profit_price - self.entry_price)
        else:  # SHORT
            risk = abs(self.stop_loss_price - self.entry_price)
            reward = abs(self.entry_price - self.take_profit_price)

        if risk == 0:
            return None

        return float(reward / risk)


@dataclass
class ClosedPosition:
    """
    Represents a closed trading position.
    """

    # Identity
    position_id: str
    ticker: str
    side: PositionSide

    # Quantities
    quantity: int
    entry_price: Decimal
    exit_price: Decimal

    # P&L
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal

    # Timestamps
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int

    # Exit details
    exit_reason: str  # 'stop_loss', 'take_profit', 'manual', 'timeout'
    exit_order_id: Optional[str] = None

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: Optional[str] = None

    # Additional metadata
    metadata: Dict = field(default_factory=dict)

    def was_profitable(self) -> bool:
        """Check if position was profitable"""
        return self.realized_pnl > 0

    def get_hold_duration_hours(self) -> float:
        """Get hold duration in hours"""
        return self.hold_duration_seconds / 3600.0


@dataclass
class PortfolioMetrics:
    """
    Portfolio-level metrics.
    """

    # Position counts
    total_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0

    # Exposure
    total_exposure: Decimal = Decimal("0")
    long_exposure: Decimal = Decimal("0")
    short_exposure: Decimal = Decimal("0")
    net_exposure: Decimal = Decimal("0")

    # P&L
    total_unrealized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl_pct: Decimal = Decimal("0")

    # Risk
    largest_position_pct: Decimal = Decimal("0")
    positions_at_stop_loss: int = 0
    positions_at_take_profit: int = 0

    # Additional metrics
    avg_position_size: Decimal = Decimal("0")
    metadata: Dict = field(default_factory=dict)


# ============================================================================
# Position Manager
# ============================================================================


class PositionManager:
    """
    Manages trading positions and portfolio state.

    This class is responsible for:
    1. Tracking open positions
    2. Updating positions with current prices
    3. Calculating P&L
    4. Monitoring stop-loss and take-profit levels
    5. Closing positions
    6. Maintaining position history
    7. Computing portfolio metrics
    """

    def __init__(
        self,
        broker: BrokerInterface,
        db_path: Optional[Path] = None,
    ):
        """
        Initialize PositionManager.

        Args:
            broker: Broker client implementing BrokerInterface
            db_path: Path to SQLite database
        """
        self.broker = broker
        self.logger = get_logger(__name__)

        # Database setup
        settings = get_settings()
        self.db_path = db_path or settings.data_dir / "trading.db"
        self._init_database()

        # In-memory position cache
        self._positions: Dict[str, ManagedPosition] = {}

        # Price update tracking
        self._last_price_update: Dict[str, datetime] = {}

        self.logger.info(f"Initialized PositionManager (db={self.db_path})")

    # ========================================================================
    # Database Management
    # ========================================================================

    def _init_database(self) -> None:
        """
        Initialize database schema for position tracking.
        """
        try:
            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                # Create positions table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS positions (
                        position_id TEXT PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        entry_price REAL NOT NULL,
                        current_price REAL NOT NULL,
                        cost_basis REAL NOT NULL,
                        market_value REAL NOT NULL,
                        unrealized_pnl REAL NOT NULL,
                        unrealized_pnl_pct REAL NOT NULL,
                        stop_loss_price REAL,
                        take_profit_price REAL,
                        opened_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        entry_order_id TEXT,
                        signal_id TEXT,
                        strategy TEXT,
                        metadata JSON
                    )
                """
                )

                # Create closed_positions table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS closed_positions (
                        position_id TEXT PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL NOT NULL,
                        cost_basis REAL NOT NULL,
                        realized_pnl REAL NOT NULL,
                        realized_pnl_pct REAL NOT NULL,
                        opened_at TIMESTAMP NOT NULL,
                        closed_at TIMESTAMP NOT NULL,
                        hold_duration_seconds INTEGER NOT NULL,
                        exit_reason TEXT,
                        exit_order_id TEXT,
                        entry_order_id TEXT,
                        signal_id TEXT,
                        strategy TEXT,
                        metadata JSON
                    )
                """
                )

                # Create indexes
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_positions_ticker
                    ON positions(ticker)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_positions_opened_at
                    ON positions(opened_at)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_closed_positions_ticker
                    ON closed_positions(ticker)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at
                    ON closed_positions(closed_at)
                """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_closed_positions_strategy
                    ON closed_positions(strategy)
                """
                )

                conn.commit()
                self.logger.info("Database initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    def _save_position_to_db(self, position: ManagedPosition) -> None:
        """
        Save position to database.

        Args:
            position: Position to save
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO positions (
                        position_id, ticker, side, quantity,
                        entry_price, current_price,
                        cost_basis, market_value,
                        unrealized_pnl, unrealized_pnl_pct,
                        stop_loss_price, take_profit_price,
                        opened_at, updated_at,
                        entry_order_id, signal_id, strategy, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.position_id,
                        position.ticker,
                        position.side.value,
                        position.quantity,
                        float(position.entry_price),
                        float(position.current_price),
                        float(position.cost_basis),
                        float(position.market_value),
                        float(position.unrealized_pnl),
                        float(position.unrealized_pnl_pct),
                        (
                            float(position.stop_loss_price)
                            if position.stop_loss_price
                            else None
                        ),
                        (
                            float(position.take_profit_price)
                            if position.take_profit_price
                            else None
                        ),
                        position.opened_at.isoformat(),
                        position.updated_at.isoformat(),
                        position.entry_order_id,
                        position.signal_id,
                        position.strategy,
                        json.dumps(position.metadata),
                    ),
                )
                conn.commit()
                self.logger.debug(f"Saved position {position.position_id} to database")

        except Exception as e:
            self.logger.error(f"Failed to save position to database: {e}")

    def _save_closed_position_to_db(self, closed: ClosedPosition) -> None:
        """
        Save closed position to database.

        Args:
            closed: Closed position to save
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO closed_positions (
                        position_id, ticker, side, quantity,
                        entry_price, exit_price,
                        cost_basis, realized_pnl, realized_pnl_pct,
                        opened_at, closed_at, hold_duration_seconds,
                        exit_reason, exit_order_id,
                        entry_order_id, signal_id, strategy, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        closed.position_id,
                        closed.ticker,
                        closed.side.value,
                        closed.quantity,
                        float(closed.entry_price),
                        float(closed.exit_price),
                        float(closed.cost_basis),
                        float(closed.realized_pnl),
                        float(closed.realized_pnl_pct),
                        closed.opened_at.isoformat(),
                        closed.closed_at.isoformat(),
                        closed.hold_duration_seconds,
                        closed.exit_reason,
                        closed.exit_order_id,
                        closed.entry_order_id,
                        closed.signal_id,
                        closed.strategy,
                        json.dumps(closed.metadata),
                    ),
                )

                # Remove from open positions table
                conn.execute(
                    "DELETE FROM positions WHERE position_id = ?",
                    (closed.position_id,),
                )

                conn.commit()
                self.logger.info(
                    f"Closed position {closed.position_id}: {closed.ticker} "
                    f"P&L=${closed.realized_pnl} ({closed.realized_pnl_pct*100:.2f}%)"
                )

        except Exception as e:
            self.logger.error(f"Failed to save closed position to database: {e}")

    def _delete_position_from_db(self, position_id: str) -> None:
        """
        Delete position from database.

        Args:
            position_id: Position ID to delete
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM positions WHERE position_id = ?", (position_id,)
                )
                conn.commit()
                self.logger.debug(f"Deleted position {position_id} from database")

        except Exception as e:
            self.logger.error(f"Failed to delete position from database: {e}")

    # ========================================================================
    # Position Management
    # ========================================================================

    async def open_position(
        self,
        order: Order,
        signal_id: Optional[str] = None,
        strategy: Optional[str] = None,
        stop_loss_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ) -> ManagedPosition:
        """
        Create a new position from a filled order.

        Args:
            order: Filled order
            signal_id: Associated trading signal ID
            strategy: Strategy that generated this position
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price

        Returns:
            ManagedPosition object
        """
        if not order.is_filled():
            raise ValueError(f"Order {order.order_id} is not filled")

        # TODO: Calculate position metrics
        quantity = order.filled_quantity
        entry_price = order.filled_avg_price or Decimal("0")
        cost_basis = entry_price * quantity

        # Determine side
        side = PositionSide.LONG if order.side.value == "buy" else PositionSide.SHORT

        # Create position
        position = ManagedPosition(
            position_id=str(uuid.uuid4()),
            ticker=order.ticker,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            cost_basis=cost_basis,
            market_value=cost_basis,
            unrealized_pnl=Decimal("0"),
            unrealized_pnl_pct=Decimal("0"),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            opened_at=order.filled_at or sim_now(),
            updated_at=sim_now(),
            entry_order_id=order.order_id,
            signal_id=signal_id,
            strategy=strategy,
        )

        # Save to database
        self._save_position_to_db(position)

        # Cache in memory
        self._positions[position.position_id] = position

        self.logger.info(
            f"Opened position: {position.ticker} {position.side.value} "
            f"{position.quantity} @ ${position.entry_price}"
        )

        return position

    async def close_position(
        self,
        position_id: str,
        exit_reason: str = "manual",
        exit_order_id: Optional[str] = None,
    ) -> Optional[ClosedPosition]:
        """
        Close an existing position.

        Args:
            position_id: Position ID to close
            exit_reason: Reason for closing (stop_loss, take_profit, manual, timeout)
            exit_order_id: Exit order ID

        Returns:
            ClosedPosition object, or None if position not found
        """
        # Get position
        position = self._positions.get(position_id)
        if not position:
            self.logger.warning(f"Position {position_id} not found")
            return None

        # TODO: Close position via broker
        try:
            close_order = await self.broker.close_position(
                ticker=position.ticker,
                quantity=position.quantity,
            )

            # Wait for fill
            # TODO: Implement wait_for_fill or poll until filled
            # For now, assume it fills at current price

            exit_price = position.current_price
            exit_order_id = close_order.order_id

        except Exception as e:
            self.logger.error(f"Failed to close position via broker: {e}")
            exit_price = position.current_price

        # Calculate realized P&L
        if position.side == PositionSide.LONG:
            realized_pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            realized_pnl = (position.entry_price - exit_price) * position.quantity

        realized_pnl_pct = (
            realized_pnl / position.cost_basis if position.cost_basis else Decimal("0")
        )

        # Create closed position
        closed = ClosedPosition(
            position_id=position.position_id,
            ticker=position.ticker,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            cost_basis=position.cost_basis,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            opened_at=position.opened_at,
            closed_at=sim_now(),
            hold_duration_seconds=int((sim_now() - position.opened_at).total_seconds()),
            exit_reason=exit_reason,
            exit_order_id=exit_order_id,
            entry_order_id=position.entry_order_id,
            signal_id=position.signal_id,
            strategy=position.strategy,
            metadata=position.metadata,
        )

        # Save to database
        self._save_closed_position_to_db(closed)

        # Remove from memory cache
        del self._positions[position_id]

        self.logger.info(
            f"Closed position {position_id}: {closed.ticker} "
            f"P&L=${closed.realized_pnl:.2f} ({closed.realized_pnl_pct*100:.2f}%) "
            f"reason={exit_reason}"
        )

        return closed

    async def update_position_prices(
        self,
        price_updates: Optional[Dict[str, Decimal]] = None,
    ) -> int:
        """
        Update all positions with current prices.

        Args:
            price_updates: Optional dict of ticker -> current_price
                          If None, fetches prices from broker

        Returns:
            Number of positions updated
        """
        if not self._positions:
            return 0

        # Get current prices if not provided
        if price_updates is None:
            # TODO: Fetch current prices for all tickers
            # This could come from:
            # 1. Broker API (if supported)
            # 2. Market data provider
            # 3. WebSocket feed
            price_updates = await self._fetch_current_prices()

        # Update each position
        updated_count = 0
        for position_id, position in self._positions.items():
            ticker = position.ticker
            if ticker not in price_updates:
                continue

            current_price = price_updates[ticker]

            # Update price and recalculate P&L
            position.current_price = current_price
            position.market_value = current_price * position.quantity

            if position.side == PositionSide.LONG:
                position.unrealized_pnl = (
                    current_price - position.entry_price
                ) * position.quantity
            else:  # SHORT
                position.unrealized_pnl = (
                    position.entry_price - current_price
                ) * position.quantity

            position.unrealized_pnl_pct = (
                position.unrealized_pnl / position.cost_basis
                if position.cost_basis
                else Decimal("0")
            )

            position.updated_at = sim_now()

            # Save to database
            self._save_position_to_db(position)

            updated_count += 1

        self.logger.debug(f"Updated {updated_count} positions with current prices")
        return updated_count

    async def _fetch_current_prices(self) -> Dict[str, Decimal]:
        """
        Fetch current prices for all open positions.

        Returns:
            Dictionary of ticker -> current_price
        """
        # TODO: Implement price fetching
        # Options:
        # 1. Use broker.get_current_price() for each ticker
        # 2. Use a market data provider (Alpaca, IEX, etc.)
        # 3. Use a WebSocket feed for real-time prices

        prices = {}

        for position in self._positions.values():
            try:
                # Placeholder - implement actual price fetching
                price = await self.broker.get_current_price(position.ticker)
                if price:
                    prices[position.ticker] = price
            except Exception as e:
                self.logger.warning(f"Failed to fetch price for {position.ticker}: {e}")

        return prices

    async def check_stop_losses(self) -> List[ManagedPosition]:
        """
        Check all positions for stop loss triggers.

        Returns:
            List of positions that hit stop loss
        """
        triggered_positions = []

        for position in self._positions.values():
            if position.should_stop_loss():
                self.logger.warning(
                    f"Stop loss triggered for {position.ticker}: "
                    f"current=${position.current_price}, stop=${position.stop_loss_price}"
                )
                triggered_positions.append(position)

        return triggered_positions

    async def check_take_profits(self) -> List[ManagedPosition]:
        """
        Check all positions for take profit triggers.

        Returns:
            List of positions that hit take profit
        """
        triggered_positions = []

        for position in self._positions.values():
            if position.should_take_profit():
                self.logger.info(
                    f"Take profit triggered for {position.ticker}: "
                    f"current=${position.current_price}, target=${position.take_profit_price}"
                )
                triggered_positions.append(position)

        return triggered_positions

    async def auto_close_triggered_positions(self) -> List[ClosedPosition]:
        """
        Automatically close positions that hit stop loss or take profit.

        Returns:
            List of closed positions
        """
        closed_positions = []

        # Check stop losses
        stop_loss_positions = await self.check_stop_losses()
        for position in stop_loss_positions:
            closed = await self.close_position(
                position_id=position.position_id,
                exit_reason="stop_loss",
            )
            if closed:
                closed_positions.append(closed)

        # Check take profits
        take_profit_positions = await self.check_take_profits()
        for position in take_profit_positions:
            closed = await self.close_position(
                position_id=position.position_id,
                exit_reason="take_profit",
            )
            if closed:
                closed_positions.append(closed)

        return closed_positions

    # ========================================================================
    # Position Queries
    # ========================================================================

    def get_position(self, position_id: str) -> Optional[ManagedPosition]:
        """Get position by ID"""
        return self._positions.get(position_id)

    def get_position_by_ticker(self, ticker: str) -> Optional[ManagedPosition]:
        """Get position by ticker"""
        for position in self._positions.values():
            if position.ticker == ticker:
                return position
        return None

    def get_all_positions(self) -> List[ManagedPosition]:
        """Get all open positions"""
        return list(self._positions.values())

    def get_positions_by_strategy(self, strategy: str) -> List[ManagedPosition]:
        """Get all positions for a specific strategy"""
        return [p for p in self._positions.values() if p.strategy == strategy]

    # ========================================================================
    # Portfolio Metrics
    # ========================================================================

    def calculate_portfolio_metrics(
        self,
        account_value: Optional[Decimal] = None,
    ) -> PortfolioMetrics:
        """
        Calculate portfolio-level metrics.

        Args:
            account_value: Current account value (for percentage calculations)

        Returns:
            PortfolioMetrics object
        """
        positions = list(self._positions.values())

        if not positions:
            return PortfolioMetrics()

        # Count positions
        total_positions = len(positions)
        long_positions = sum(1 for p in positions if p.side == PositionSide.LONG)
        short_positions = sum(1 for p in positions if p.side == PositionSide.SHORT)

        # Calculate exposure
        long_exposure = sum(
            p.market_value for p in positions if p.side == PositionSide.LONG
        )
        short_exposure = sum(
            p.market_value for p in positions if p.side == PositionSide.SHORT
        )
        total_exposure = long_exposure + short_exposure
        net_exposure = long_exposure - short_exposure

        # Calculate P&L
        total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        total_cost_basis = sum(p.cost_basis for p in positions)
        total_unrealized_pnl_pct = (
            total_unrealized_pnl / total_cost_basis
            if total_cost_basis
            else Decimal("0")
        )

        # Risk metrics
        largest_position = max(positions, key=lambda p: p.market_value)
        largest_position_pct = (
            largest_position.market_value / account_value
            if account_value
            else Decimal("0")
        )

        positions_at_stop_loss = sum(1 for p in positions if p.should_stop_loss())
        positions_at_take_profit = sum(1 for p in positions if p.should_take_profit())

        # Average position size
        avg_position_size = (
            total_exposure / total_positions if total_positions else Decimal("0")
        )

        return PortfolioMetrics(
            total_positions=total_positions,
            long_positions=long_positions,
            short_positions=short_positions,
            total_exposure=total_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            net_exposure=net_exposure,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_pct=total_unrealized_pnl_pct,
            largest_position_pct=largest_position_pct,
            positions_at_stop_loss=positions_at_stop_loss,
            positions_at_take_profit=positions_at_take_profit,
            avg_position_size=avg_position_size,
        )

    def get_portfolio_exposure(self) -> Decimal:
        """Get total portfolio exposure"""
        return sum(p.market_value for p in self._positions.values())

    def get_total_unrealized_pnl(self) -> Decimal:
        """Get total unrealized P&L"""
        return sum(p.unrealized_pnl for p in self._positions.values())

    # ========================================================================
    # Historical Queries
    # ========================================================================

    def get_closed_positions(
        self,
        ticker: Optional[str] = None,
        strategy: Optional[str] = None,
        limit: int = 100,
    ) -> List[ClosedPosition]:
        """
        Get closed positions from database.

        Args:
            ticker: Filter by ticker
            strategy: Filter by strategy
            limit: Maximum number of results

        Returns:
            List of ClosedPosition objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = "SELECT * FROM closed_positions WHERE 1=1"
                params = []

                if ticker:
                    query += " AND ticker = ?"
                    params.append(ticker)

                if strategy:
                    query += " AND strategy = ?"
                    params.append(strategy)

                query += " ORDER BY closed_at DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(query, params)
                cursor.fetchall()

                # TODO: Parse rows into ClosedPosition objects
                # This requires mapping column indices to fields

                return []

        except Exception as e:
            self.logger.error(f"Failed to get closed positions: {e}")
            return []

    def get_performance_stats(self, days: int = 30) -> Dict:
        """
        Get performance statistics for closed positions.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with performance statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                        SUM(realized_pnl) as total_pnl,
                        AVG(realized_pnl) as avg_pnl,
                        AVG(realized_pnl_pct) as avg_pnl_pct,
                        MAX(realized_pnl) as best_trade,
                        MIN(realized_pnl) as worst_trade,
                        AVG(hold_duration_seconds) as avg_hold_time_seconds
                    FROM closed_positions
                    WHERE closed_at >= datetime('now', '-' || ? || ' days')
                    """,
                    (days,),
                )

                row = cursor.fetchone()

                total_trades = row[0] or 0
                winning_trades = row[1] or 0
                losing_trades = row[2] or 0
                win_rate = (winning_trades / total_trades) if total_trades else 0.0

                return {
                    "total_trades": total_trades,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "win_rate": win_rate,
                    "total_pnl": row[3] or 0.0,
                    "avg_pnl": row[4] or 0.0,
                    "avg_pnl_pct": row[5] or 0.0,
                    "best_trade": row[6] or 0.0,
                    "worst_trade": row[7] or 0.0,
                    "avg_hold_time_hours": (row[8] or 0.0) / 3600.0,
                }

        except Exception as e:
            self.logger.error(f"Failed to get performance stats: {e}")
            return {}


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of PositionManager.

    This demonstrates how to manage trading positions.
    """

    import asyncio
    from decimal import Decimal

    from ..broker.alpaca_client import AlpacaBrokerClient
    from ..broker.broker_interface import Order, OrderSide, OrderStatus, OrderType

    async def demo():
        """Demo function showing position management"""

        # Initialize broker (paper trading)
        broker = AlpacaBrokerClient(paper_trading=True)
        await broker.connect()

        # Initialize position manager
        manager = PositionManager(broker=broker)

        # Simulate a filled order
        filled_order = Order(
            order_id="test_order_123",
            ticker="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            filled_quantity=10,
            filled_avg_price=Decimal("150.00"),
            status=OrderStatus.FILLED,
            filled_at=sim_now(),
        )

        # Open position
        position = await manager.open_position(
            order=filled_order,
            signal_id="test_signal_001",
            strategy="momentum_v1",
            stop_loss_price=Decimal("145.00"),
            take_profit_price=Decimal("160.00"),
        )

        print("\nOpened Position:")
        print(f"  Ticker: {position.ticker}")
        print(f"  Quantity: {position.quantity}")
        print(f"  Entry Price: ${position.entry_price}")
        print(f"  Cost Basis: ${position.cost_basis}")
        print(f"  Stop Loss: ${position.stop_loss_price}")
        print(f"  Take Profit: ${position.take_profit_price}")

        # Update prices
        await manager.update_position_prices(
            {
                "AAPL": Decimal("155.00"),
            }
        )

        # Get updated position
        updated_position = manager.get_position(position.position_id)
        if updated_position:
            print("\nUpdated Position:")
            print(f"  Current Price: ${updated_position.current_price}")
            print(f"  Market Value: ${updated_position.market_value}")
            print(f"  Unrealized P&L: ${updated_position.unrealized_pnl:.2f}")
            print(f"  Unrealized P&L %: {updated_position.unrealized_pnl_pct*100:.2f}%")

        # Check stop losses
        stop_losses = await manager.check_stop_losses()
        take_profits = await manager.check_take_profits()
        print("\nRisk Checks:")
        print(f"  Stop Losses Hit: {len(stop_losses)}")
        print(f"  Take Profits Hit: {len(take_profits)}")

        # Get portfolio metrics
        account = await broker.get_account()
        metrics = manager.calculate_portfolio_metrics(account_value=account.equity)
        print("\nPortfolio Metrics:")
        print(f"  Total Positions: {metrics.total_positions}")
        print(f"  Total Exposure: ${metrics.total_exposure}")
        print(f"  Total Unrealized P&L: ${metrics.total_unrealized_pnl:.2f}")

        # Close position
        closed = await manager.close_position(
            position_id=position.position_id,
            exit_reason="manual",
        )

        if closed:
            print("\nClosed Position:")
            print(f"  Exit Price: ${closed.exit_price}")
            print(f"  Realized P&L: ${closed.realized_pnl:.2f}")
            print(f"  Realized P&L %: {closed.realized_pnl_pct*100:.2f}%")
            print(f"  Hold Duration: {closed.get_hold_duration_hours():.2f} hours")

        # Get performance stats
        stats = manager.get_performance_stats(days=30)
        print("\nPerformance Stats (30 days):")
        print(f"  Total Trades: {stats.get('total_trades', 0)}")
        print(f"  Win Rate: {stats.get('win_rate', 0)*100:.1f}%")
        print(f"  Total P&L: ${stats.get('total_pnl', 0):.2f}")
        print(f"  Avg P&L %: {stats.get('avg_pnl_pct', 0)*100:.2f}%")

        # Disconnect
        await broker.disconnect()

    # Run demo
    asyncio.run(demo())
