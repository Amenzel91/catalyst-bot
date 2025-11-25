"""
Position Manager (Synchronous Version)

Manages trading positions and automated exits for paper trading.
This is a simplified synchronous version adapted from the async scaffold.

Key responsibilities:
- Track open positions in database
- Calculate real-time P&L
- Monitor stop-loss and take-profit triggers
- Execute automated exits
- Maintain position history for ML training
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from .broker.alpaca_wrapper import AlpacaBrokerWrapper
from .logging_utils import get_logger

log = get_logger("position_manager")


@dataclass
class ManagedPosition:
    """Represents a managed trading position with P&L tracking."""

    # Identity
    position_id: str
    ticker: str

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
    opened_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Tracking
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"

    def should_stop_loss(self) -> bool:
        """Check if current price has hit stop loss."""
        if not self.stop_loss_price:
            return False
        return self.current_price <= self.stop_loss_price

    def should_take_profit(self) -> bool:
        """Check if current price has hit take profit."""
        if not self.take_profit_price:
            return False
        return self.current_price >= self.take_profit_price

    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held."""
        return datetime.now() - self.opened_at


@dataclass
class ClosedPosition:
    """Represents a closed trading position with realized P&L."""

    position_id: str
    ticker: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    hold_duration_seconds: int
    exit_reason: str  # 'stop_loss', 'take_profit', 'manual', 'max_hold_time'
    exit_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "catalyst_alert"


class PositionManagerSync:
    """
    Synchronous position manager for paper trading.

    Manages positions, tracks P&L, and executes automated exits.
    """

    def __init__(self, broker: AlpacaBrokerWrapper, db_path: Optional[Path] = None):
        """
        Initialize PositionManager.

        Args:
            broker: Alpaca broker wrapper
            db_path: Path to SQLite database (defaults to data/trading.db)
        """
        self.broker = broker

        # Database setup
        if db_path is None:
            data_dir = Path(__file__).parent.parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "trading.db"

        self.db_path = Path(db_path)
        self._init_database()

        # In-memory position cache
        self._positions: Dict[str, ManagedPosition] = {}
        self._load_positions_from_db()

        log.info("position_manager_initialized db=%s positions=%d",
                 self.db_path, len(self._positions))

    def _init_database(self) -> None:
        """Initialize database schema for position tracking."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                # Create positions table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS positions (
                        position_id TEXT PRIMARY KEY,
                        ticker TEXT NOT NULL,
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
                        strategy TEXT
                    )
                """)

                # Create closed_positions table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS closed_positions (
                        position_id TEXT PRIMARY KEY,
                        ticker TEXT NOT NULL,
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
                        strategy TEXT
                    )
                """)

                # Create indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_opened_at ON positions(opened_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_closed_positions_ticker ON closed_positions(ticker)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at ON closed_positions(closed_at)")

                conn.commit()
                log.debug("database_schema_initialized")

        except Exception as e:
            log.error("database_init_failed error=%s", str(e))
            raise

    def _load_positions_from_db(self) -> None:
        """Load open positions from database into memory cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM positions")
                rows = cursor.fetchall()

                for row in rows:
                    position = ManagedPosition(
                        position_id=row[0],
                        ticker=row[1],
                        quantity=row[2],
                        entry_price=Decimal(str(row[3])),
                        current_price=Decimal(str(row[4])),
                        cost_basis=Decimal(str(row[5])),
                        market_value=Decimal(str(row[6])),
                        unrealized_pnl=Decimal(str(row[7])),
                        unrealized_pnl_pct=Decimal(str(row[8])),
                        stop_loss_price=Decimal(str(row[9])) if row[9] else None,
                        take_profit_price=Decimal(str(row[10])) if row[10] else None,
                        opened_at=datetime.fromisoformat(row[11]),
                        updated_at=datetime.fromisoformat(row[12]),
                        entry_order_id=row[13],
                        signal_id=row[14],
                        strategy=row[15] or "catalyst_alert",
                    )
                    self._positions[position.position_id] = position

                log.info("positions_loaded_from_db count=%d", len(rows))

        except Exception as e:
            log.error("load_positions_failed error=%s", str(e))

    def _save_position_to_db(self, position: ManagedPosition) -> None:
        """Save position to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO positions (
                        position_id, ticker, quantity,
                        entry_price, current_price,
                        cost_basis, market_value,
                        unrealized_pnl, unrealized_pnl_pct,
                        stop_loss_price, take_profit_price,
                        opened_at, updated_at,
                        entry_order_id, signal_id, strategy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.position_id,
                        position.ticker,
                        position.quantity,
                        float(position.entry_price),
                        float(position.current_price),
                        float(position.cost_basis),
                        float(position.market_value),
                        float(position.unrealized_pnl),
                        float(position.unrealized_pnl_pct),
                        float(position.stop_loss_price) if position.stop_loss_price else None,
                        float(position.take_profit_price) if position.take_profit_price else None,
                        position.opened_at.isoformat(),
                        position.updated_at.isoformat(),
                        position.entry_order_id,
                        position.signal_id,
                        position.strategy,
                    ),
                )
                conn.commit()

        except Exception as e:
            log.error("save_position_failed position_id=%s error=%s",
                     position.position_id, str(e))

    def _save_closed_position_to_db(self, closed: ClosedPosition) -> None:
        """Save closed position to database and remove from open positions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO closed_positions (
                        position_id, ticker, quantity,
                        entry_price, exit_price,
                        cost_basis, realized_pnl, realized_pnl_pct,
                        opened_at, closed_at, hold_duration_seconds,
                        exit_reason, exit_order_id,
                        entry_order_id, signal_id, strategy
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        closed.position_id,
                        closed.ticker,
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
                    ),
                )

                # Remove from open positions table
                conn.execute("DELETE FROM positions WHERE position_id = ?",
                            (closed.position_id,))

                conn.commit()

                log.info(
                    "position_closed ticker=%s pnl=$%.2f pnl_pct=%.2f%% reason=%s",
                    closed.ticker, closed.realized_pnl, closed.realized_pnl_pct * 100,
                    closed.exit_reason
                )

        except Exception as e:
            log.error("save_closed_position_failed position_id=%s error=%s",
                     closed.position_id, str(e))

    def open_position(
        self,
        ticker: str,
        quantity: int,
        entry_price: Decimal,
        entry_order_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        stop_loss_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ) -> ManagedPosition:
        """
        Create a new position from a filled order.

        Args:
            ticker: Stock symbol
            quantity: Number of shares
            entry_price: Entry price
            entry_order_id: Order ID that opened this position
            signal_id: Alert ID that triggered this trade
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price

        Returns:
            ManagedPosition object
        """
        cost_basis = entry_price * quantity

        position = ManagedPosition(
            position_id=str(uuid.uuid4()),
            ticker=ticker,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            cost_basis=cost_basis,
            market_value=cost_basis,
            unrealized_pnl=Decimal("0"),
            unrealized_pnl_pct=Decimal("0"),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            opened_at=datetime.now(),
            updated_at=datetime.now(),
            entry_order_id=entry_order_id,
            signal_id=signal_id,
        )

        # Save to database
        self._save_position_to_db(position)

        # Cache in memory
        self._positions[position.position_id] = position

        log.info(
            "position_opened ticker=%s qty=%d entry=$%.2f stop=$%.2f target=$%.2f",
            ticker, quantity, entry_price,
            stop_loss_price or 0, take_profit_price or 0
        )

        return position

    def close_position(
        self,
        position_id: str,
        exit_reason: str = "manual",
    ) -> Optional[ClosedPosition]:
        """
        Close an existing position.

        Args:
            position_id: Position ID to close
            exit_reason: Reason for closing (stop_loss, take_profit, manual, max_hold_time)

        Returns:
            ClosedPosition object, or None if position not found
        """
        position = self._positions.get(position_id)
        if not position:
            log.warning("close_position_failed position_id=%s reason=not_found", position_id)
            return None

        # Close position via broker
        exit_order_id = None
        try:
            exit_order_id = self.broker.close_position(
                ticker=position.ticker,
                quantity=position.quantity,
            )
            exit_price = position.current_price

        except Exception as e:
            log.error("broker_close_failed ticker=%s error=%s", position.ticker, str(e))
            exit_price = position.current_price

        # Calculate realized P&L
        realized_pnl = (exit_price - position.entry_price) * position.quantity
        realized_pnl_pct = realized_pnl / position.cost_basis if position.cost_basis else Decimal("0")

        # Create closed position
        closed = ClosedPosition(
            position_id=position.position_id,
            ticker=position.ticker,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            cost_basis=position.cost_basis,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            opened_at=position.opened_at,
            closed_at=datetime.now(),
            hold_duration_seconds=int((datetime.now() - position.opened_at).total_seconds()),
            exit_reason=exit_reason,
            exit_order_id=exit_order_id,
            entry_order_id=position.entry_order_id,
            signal_id=position.signal_id,
            strategy=position.strategy,
        )

        # Save to database
        self._save_closed_position_to_db(closed)

        # Remove from memory cache
        del self._positions[position_id]

        return closed

    def update_position_prices(self) -> int:
        """
        Update all positions with current prices from broker.

        Returns:
            Number of positions updated
        """
        if not self._positions:
            return 0

        updated_count = 0

        for position_id, position in list(self._positions.items()):
            try:
                current_price = self.broker.get_current_price(position.ticker)

                if current_price is None:
                    continue

                # Update price and recalculate P&L
                position.current_price = current_price
                position.market_value = current_price * position.quantity
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                position.unrealized_pnl_pct = (
                    position.unrealized_pnl / position.cost_basis
                    if position.cost_basis
                    else Decimal("0")
                )
                position.updated_at = datetime.now()

                # Save to database
                self._save_position_to_db(position)

                updated_count += 1

            except Exception as e:
                log.error("update_price_failed ticker=%s error=%s",
                         position.ticker, str(e))

        if updated_count > 0:
            log.debug("prices_updated count=%d", updated_count)

        return updated_count

    def check_and_execute_exits(self, max_hold_hours: int = 24) -> List[ClosedPosition]:
        """
        Check all positions for exit triggers and execute exits.

        Args:
            max_hold_hours: Maximum hold time in hours

        Returns:
            List of closed positions
        """
        closed_positions = []

        for position in list(self._positions.values()):
            # Check stop-loss
            if position.should_stop_loss():
                log.warning(
                    "stop_loss_triggered ticker=%s current=$%.2f stop=$%.2f",
                    position.ticker, position.current_price, position.stop_loss_price
                )
                closed = self.close_position(position.position_id, exit_reason="stop_loss")
                if closed:
                    closed_positions.append(closed)
                continue

            # Check take-profit
            if position.should_take_profit():
                log.info(
                    "take_profit_triggered ticker=%s current=$%.2f target=$%.2f",
                    position.ticker, position.current_price, position.take_profit_price
                )
                closed = self.close_position(position.position_id, exit_reason="take_profit")
                if closed:
                    closed_positions.append(closed)
                continue

            # Check max hold time
            hold_hours = position.get_hold_duration().total_seconds() / 3600
            if hold_hours >= max_hold_hours:
                log.info(
                    "max_hold_time_triggered ticker=%s hold_hours=%.1f",
                    position.ticker, hold_hours
                )
                closed = self.close_position(position.position_id, exit_reason="max_hold_time")
                if closed:
                    closed_positions.append(closed)
                continue

        return closed_positions

    def get_all_positions(self) -> List[ManagedPosition]:
        """Get all open positions."""
        return list(self._positions.values())

    def get_position_by_ticker(self, ticker: str) -> Optional[ManagedPosition]:
        """Get position by ticker symbol."""
        for position in self._positions.values():
            if position.ticker == ticker:
                return position
        return None
