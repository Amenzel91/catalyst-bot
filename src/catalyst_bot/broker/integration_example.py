"""
Broker Integration Example

This module demonstrates the complete trading workflow using all broker integration components:
- BrokerInterface (Alpaca implementation)
- OrderExecutor
- PositionManager

This example shows:
1. Connecting to the broker
2. Analyzing trading signals
3. Executing trades with proper position sizing
4. Managing open positions
5. Monitoring stop-losses and take-profits
6. Closing positions and calculating P&L
7. Generating performance reports

Usage:
    python -m catalyst_bot.broker.integration_example
"""

import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import List

from ..logging_utils import get_logger, setup_logging
from .alpaca_client import AlpacaBrokerClient
from ..execution.order_executor import (
    OrderExecutor,
    PositionSizingConfig,
    TradingSignal,
)
from ..portfolio.position_manager import PositionManager

logger = get_logger(__name__)


class TradingBot:
    """
    Complete trading bot example that integrates all components.
    """

    def __init__(
        self,
        paper_trading: bool = True,
        max_position_pct: float = 0.10,
        risk_per_trade_pct: float = 0.02,
    ):
        """
        Initialize trading bot.

        Args:
            paper_trading: Use paper trading (default: True)
            max_position_pct: Maximum position size as % of portfolio
            risk_per_trade_pct: Risk per trade as % of portfolio
        """
        self.paper_trading = paper_trading

        # Initialize broker
        self.broker = AlpacaBrokerClient(paper_trading=paper_trading)

        # Initialize position sizing configuration
        self.sizing_config = PositionSizingConfig(
            max_position_size_pct=max_position_pct,
            risk_per_trade_pct=risk_per_trade_pct,
        )

        # Initialize order executor
        self.executor = OrderExecutor(
            broker=self.broker,
            position_sizing_config=self.sizing_config,
        )

        # Initialize position manager
        self.position_manager = PositionManager(broker=self.broker)

        # Trading state
        self.is_running = False

        logger.info(
            f"Initialized TradingBot (paper={paper_trading}, "
            f"max_position={max_position_pct*100}%, risk={risk_per_trade_pct*100}%)"
        )

    async def start(self) -> None:
        """Start the trading bot."""
        logger.info("Starting trading bot...")

        # Connect to broker
        await self.broker.connect()

        # Get account info
        account = await self.broker.get_account()
        logger.info(
            f"Connected to broker: Account ${account.equity:.2f}, "
            f"Buying Power ${account.buying_power:.2f}"
        )

        self.is_running = True

    async def stop(self) -> None:
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")

        # Disconnect from broker
        await self.broker.disconnect()

        self.is_running = False
        logger.info("Trading bot stopped")

    async def process_signal(self, signal: TradingSignal) -> bool:
        """
        Process a trading signal and execute if valid.

        Args:
            signal: Trading signal to process

        Returns:
            True if signal was executed successfully
        """
        logger.info(
            f"Processing signal: {signal.ticker} {signal.action} "
            f"(confidence={signal.confidence:.2f})"
        )

        # Check if we already have a position in this ticker
        existing_position = self.position_manager.get_position_by_ticker(signal.ticker)
        if existing_position:
            logger.warning(
                f"Already have position in {signal.ticker}, skipping signal"
            )
            return False

        # Execute signal
        result = await self.executor.execute_signal(
            signal=signal,
            use_bracket_order=True,
        )

        if not result.success:
            logger.error(f"Failed to execute signal: {result.error_message}")
            return False

        logger.info(
            f"Signal executed successfully: {signal.ticker} {result.quantity} shares"
        )

        # If we have a filled order, open position in position manager
        if result.bracket_order and result.bracket_order.entry_order.is_filled():
            await self.position_manager.open_position(
                order=result.bracket_order.entry_order,
                signal_id=signal.signal_id,
                strategy=signal.strategy,
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
            )

        return True

    async def monitor_positions(self) -> None:
        """
        Monitor open positions and update prices.

        This should be called periodically (e.g., every minute).
        """
        # Get current positions from broker
        broker_positions = await self.broker.get_positions()

        if not broker_positions:
            logger.debug("No open positions to monitor")
            return

        # Build price updates from broker positions
        price_updates = {
            pos.ticker: pos.current_price
            for pos in broker_positions
        }

        # Update managed positions
        updated_count = await self.position_manager.update_position_prices(
            price_updates=price_updates
        )

        logger.debug(f"Updated {updated_count} positions")

        # Check for stop-loss and take-profit triggers
        closed_positions = await self.position_manager.auto_close_triggered_positions()

        if closed_positions:
            for closed in closed_positions:
                logger.info(
                    f"Auto-closed position: {closed.ticker} "
                    f"P&L=${closed.realized_pnl:.2f} ({closed.realized_pnl_pct*100:.2f}%) "
                    f"reason={closed.exit_reason}"
                )

    async def get_portfolio_summary(self) -> dict:
        """
        Get current portfolio summary.

        Returns:
            Dictionary with portfolio information
        """
        # Get account
        account = await self.broker.get_account()

        # Get portfolio metrics
        metrics = self.position_manager.calculate_portfolio_metrics(
            account_value=account.equity
        )

        # Get performance stats
        performance = self.position_manager.get_performance_stats(days=30)

        return {
            "account": {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
            },
            "positions": {
                "total": metrics.total_positions,
                "long": metrics.long_positions,
                "short": metrics.short_positions,
                "total_exposure": float(metrics.total_exposure),
                "unrealized_pnl": float(metrics.total_unrealized_pnl),
                "unrealized_pnl_pct": float(metrics.total_unrealized_pnl_pct),
            },
            "performance_30d": performance,
        }

    async def run_trading_loop(
        self,
        signals: List[TradingSignal],
        monitor_interval: int = 60,
    ) -> None:
        """
        Run the main trading loop.

        Args:
            signals: List of trading signals to process
            monitor_interval: How often to monitor positions (seconds)
        """
        logger.info(f"Starting trading loop with {len(signals)} signals")

        # Process all signals
        for signal in signals:
            if not self.is_running:
                break

            await self.process_signal(signal)

            # Small delay between signals
            await asyncio.sleep(1)

        # Monitor positions
        logger.info("Signal processing complete, monitoring positions...")

        while self.is_running:
            await self.monitor_positions()

            # Print portfolio summary
            summary = await self.get_portfolio_summary()
            logger.info(
                f"Portfolio: {summary['positions']['total']} positions, "
                f"${summary['account']['equity']:.2f} equity, "
                f"${summary['positions']['unrealized_pnl']:.2f} unrealized P&L"
            )

            # Wait before next check
            await asyncio.sleep(monitor_interval)


async def demo_simple() -> None:
    """
    Simple demo showing basic trading workflow.
    """
    print("\n" + "=" * 80)
    print("DEMO: Simple Trading Workflow")
    print("=" * 80 + "\n")

    # Initialize bot
    bot = TradingBot(paper_trading=True)

    try:
        # Start bot
        await bot.start()

        # Create a sample trading signal
        signal = TradingSignal(
            signal_id="demo_signal_001",
            ticker="AAPL",
            timestamp=datetime.now(),
            action="buy",
            confidence=0.85,
            current_price=Decimal("150.00"),
            entry_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),  # 3.3% stop loss
            take_profit_price=Decimal("160.00"),  # 6.7% profit target
            position_size_pct=0.05,  # 5% of portfolio
            signal_type="momentum",
            timeframe="intraday",
            strategy="demo_strategy",
        )

        # Process signal
        print("\n1. Processing trading signal...")
        success = await bot.process_signal(signal)
        print(f"   Signal execution: {'SUCCESS' if success else 'FAILED'}")

        # Wait a bit for order to fill
        await asyncio.sleep(2)

        # Monitor positions
        print("\n2. Monitoring positions...")
        await bot.monitor_positions()

        # Get portfolio summary
        print("\n3. Portfolio Summary:")
        summary = await bot.get_portfolio_summary()
        print(f"   Account Equity: ${summary['account']['equity']:.2f}")
        print(f"   Open Positions: {summary['positions']['total']}")
        print(f"   Unrealized P&L: ${summary['positions']['unrealized_pnl']:.2f}")

        # Get performance stats
        print("\n4. Performance Stats (30 days):")
        perf = summary['performance_30d']
        print(f"   Total Trades: {perf.get('total_trades', 0)}")
        print(f"   Win Rate: {perf.get('win_rate', 0)*100:.1f}%")
        print(f"   Total P&L: ${perf.get('total_pnl', 0):.2f}")

    finally:
        # Stop bot
        await bot.stop()

    print("\n" + "=" * 80)
    print("Demo complete!")
    print("=" * 80 + "\n")


async def demo_advanced() -> None:
    """
    Advanced demo showing multiple signals and position management.
    """
    print("\n" + "=" * 80)
    print("DEMO: Advanced Trading Workflow")
    print("=" * 80 + "\n")

    # Initialize bot with custom parameters
    bot = TradingBot(
        paper_trading=True,
        max_position_pct=0.10,  # 10% max per position
        risk_per_trade_pct=0.02,  # 2% risk per trade
    )

    try:
        # Start bot
        await bot.start()

        # Create multiple trading signals
        signals = [
            TradingSignal(
                signal_id=f"demo_signal_{i:03d}",
                ticker=ticker,
                timestamp=datetime.now(),
                action="buy",
                confidence=confidence,
                current_price=price,
                entry_price=price,
                stop_loss_price=price * Decimal("0.97"),  # 3% stop
                take_profit_price=price * Decimal("1.06"),  # 6% profit
                position_size_pct=0.05,
                signal_type="momentum",
                timeframe="intraday",
                strategy="demo_advanced",
            )
            for i, (ticker, price, confidence) in enumerate([
                ("AAPL", Decimal("150.00"), 0.85),
                ("MSFT", Decimal("350.00"), 0.80),
                ("GOOGL", Decimal("140.00"), 0.75),
                ("TSLA", Decimal("200.00"), 0.90),
                ("NVDA", Decimal("450.00"), 0.88),
            ])
        ]

        # Run trading loop (will process signals and monitor positions)
        # In production, this would run indefinitely
        # For demo, we'll run for 5 minutes
        print(f"\n1. Processing {len(signals)} trading signals...")

        # Create task for trading loop
        trading_task = asyncio.create_task(
            bot.run_trading_loop(signals, monitor_interval=30)
        )

        # Let it run for 5 minutes
        await asyncio.sleep(300)

        # Stop trading loop
        bot.is_running = False
        await trading_task

        # Final portfolio summary
        print("\n2. Final Portfolio Summary:")
        summary = await bot.get_portfolio_summary()

        print(f"\n   Account:")
        print(f"     Equity: ${summary['account']['equity']:.2f}")
        print(f"     Cash: ${summary['account']['cash']:.2f}")
        print(f"     Buying Power: ${summary['account']['buying_power']:.2f}")

        print(f"\n   Positions:")
        print(f"     Total: {summary['positions']['total']}")
        print(f"     Long: {summary['positions']['long']}")
        print(f"     Short: {summary['positions']['short']}")
        print(f"     Exposure: ${summary['positions']['total_exposure']:.2f}")
        print(f"     Unrealized P&L: ${summary['positions']['unrealized_pnl']:.2f}")

        print(f"\n   Performance (30 days):")
        perf = summary['performance_30d']
        print(f"     Total Trades: {perf.get('total_trades', 0)}")
        print(f"     Win Rate: {perf.get('win_rate', 0)*100:.1f}%")
        print(f"     Total P&L: ${perf.get('total_pnl', 0):.2f}")
        print(f"     Avg P&L: ${perf.get('avg_pnl', 0):.2f}")
        print(f"     Best Trade: ${perf.get('best_trade', 0):.2f}")
        print(f"     Worst Trade: ${perf.get('worst_trade', 0):.2f}")

    finally:
        # Stop bot
        await bot.stop()

    print("\n" + "=" * 80)
    print("Demo complete!")
    print("=" * 80 + "\n")


async def main():
    """
    Main entry point for integration example.
    """
    # Setup logging
    setup_logging(level="INFO")

    # Check for API credentials
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_API_SECRET"):
        print("\n" + "=" * 80)
        print("ERROR: Alpaca API credentials not found!")
        print("=" * 80)
        print("\nPlease set the following environment variables:")
        print("  ALPACA_API_KEY=your_api_key")
        print("  ALPACA_API_SECRET=your_api_secret")
        print("\nFor paper trading credentials, visit:")
        print("  https://alpaca.markets/docs/trading/paper-trading/")
        print("\n" + "=" * 80 + "\n")
        return

    # Run demos
    try:
        # Run simple demo
        await demo_simple()

        # Uncomment to run advanced demo
        # await demo_advanced()

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")

    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)


if __name__ == "__main__":
    """
    Run the integration example.

    Requirements:
    1. Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables
    2. Install required packages:
       pip install aiohttp

    Usage:
        python -m catalyst_bot.broker.integration_example
    """
    asyncio.run(main())
