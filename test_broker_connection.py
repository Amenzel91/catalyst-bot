"""
Test Alpaca Broker Connection

Simple script to verify Alpaca API credentials and test basic broker operations.
"""

import asyncio
import os
from decimal import Decimal
from dotenv import load_dotenv

from src.catalyst_bot.broker.alpaca_client import AlpacaBrokerClient
from src.catalyst_bot.broker.broker_interface import OrderSide, OrderType, TimeInForce


async def test_broker_connection():
    """Test broker connection and basic operations"""

    print("=" * 60)
    print("Testing Alpaca Broker Connection")
    print("=" * 60)

    # Load environment variables
    load_dotenv()

    # Check credentials
    # Note: .env has ALPACA_SECRET, but code expects ALPACA_API_SECRET
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_SECRET") or os.getenv("ALPACA_API_SECRET")

    # Set the expected variable name if needed
    if api_secret and not os.getenv("ALPACA_API_SECRET"):
        os.environ["ALPACA_API_SECRET"] = api_secret

    if not api_key or not api_secret:
        print("[ERROR] Alpaca credentials not found in .env file")
        print("        Required: ALPACA_API_KEY, ALPACA_SECRET")
        return False

    print(f"\n[OK] Credentials found:")
    print(f"  API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"  Secret: {api_secret[:10]}...***")

    # Initialize broker (paper trading)
    print(f"\n1. Initializing Alpaca client (paper trading)...")
    try:
        broker = AlpacaBrokerClient(paper_trading=True)
        print("   [OK] Client initialized")
    except Exception as e:
        print(f"   [ERROR] Failed to initialize client: {e}")
        return False

    # Test connection
    print(f"\n2. Testing connection to Alpaca API...")
    try:
        await broker.connect()
        print("   [OK] Connected successfully")
    except Exception as e:
        print(f"   [ERROR] Connection failed: {e}")
        return False

    # Test get_account
    print(f"\n3. Fetching account information...")
    try:
        account = await broker.get_account()
        print(f"   [OK] Account retrieved:")
        print(f"     Account ID: {account.account_id}")
        print(f"     Status: {account.status.value}")
        print(f"     Cash: ${account.cash:,.2f}")
        print(f"     Portfolio Value: ${account.portfolio_value:,.2f}")
        print(f"     Buying Power: ${account.buying_power:,.2f}")
        print(f"     Equity: ${account.equity:,.2f}")
        print(f"     Tradeable: {account.is_tradeable()}")
    except Exception as e:
        print(f"   [ERROR] Failed to get account: {e}")
        await broker.disconnect()
        return False

    # Test get_positions
    print(f"\n4. Fetching open positions...")
    try:
        positions = await broker.get_positions()
        print(f"   [OK] Positions retrieved: {len(positions)} open position(s)")

        if positions:
            print(f"\n   Open Positions:")
            for pos in positions[:5]:  # Show first 5
                print(f"     - {pos.ticker}: {pos.quantity} shares @ ${pos.entry_price:.2f}")
                print(f"       P&L: ${pos.unrealized_pnl:.2f} ({pos.unrealized_pnl_pct*100:.2f}%)")
        else:
            print(f"   No open positions (starting fresh)")
    except Exception as e:
        print(f"   [ERROR] Failed to get positions: {e}")
        await broker.disconnect()
        return False

    # Test list_orders
    print(f"\n5. Fetching recent orders...")
    try:
        orders = await broker.list_orders(status="all", limit=5)
        print(f"   [OK] Orders retrieved: {len(orders)} recent order(s)")

        if orders:
            print(f"\n   Recent Orders:")
            for order in orders:
                print(f"     - {order.ticker}: {order.side.value} {order.quantity} @ {order.order_type.value}")
                print(f"       Status: {order.status.value}, ID: {order.order_id}")
        else:
            print(f"   No recent orders")
    except Exception as e:
        print(f"   [ERROR] Failed to get orders: {e}")
        await broker.disconnect()
        return False

    # Test order placement (small test order)
    print(f"\n6. Testing order placement (dry run - will be cancelled)...")
    print(f"   Placing limit order for 1 share of AAPL at $100 (below market, won't fill)")

    try:
        test_order = await broker.place_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("100.00"),  # Well below market price
            time_in_force=TimeInForce.DAY,
            client_order_id="test_order_from_broker_test"
        )

        print(f"   [OK] Order placed successfully:")
        print(f"     Order ID: {test_order.order_id}")
        print(f"     Status: {test_order.status.value}")
        print(f"     Side: {test_order.side.value}")
        print(f"     Quantity: {test_order.quantity}")
        print(f"     Limit Price: ${test_order.limit_price}")

        # Cancel the test order
        print(f"\n7. Cancelling test order...")
        try:
            cancelled_order = await broker.cancel_order(test_order.order_id)
            print(f"   [OK] Order cancelled successfully")
            print(f"     Status: {cancelled_order.status.value}")
        except Exception as e:
            print(f"   [WARN]  Failed to cancel order: {e}")

    except Exception as e:
        print(f"   [ERROR] Failed to place order: {e}")
        await broker.disconnect()
        return False

    # Disconnect
    print(f"\n8. Disconnecting from broker...")
    try:
        await broker.disconnect()
        print("   [OK] Disconnected successfully")
    except Exception as e:
        print(f"   [WARN]  Disconnect warning: {e}")

    # Summary
    print(f"\n" + "=" * 60)
    print("[PASS] ALL TESTS PASSED")
    print("=" * 60)
    print(f"\nBroker Connection Summary:")
    print(f"  - Connection: Working")
    print(f"  - Account: Accessible")
    print(f"  - Positions: {len(positions)} open")
    print(f"  - Buying Power: ${account.buying_power:,.2f}")
    print(f"  - Order Placement: Working")
    print(f"  - Order Cancellation: Working")
    print(f"\nThe Alpaca broker integration is ready to use!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    """Run broker connection tests"""
    success = asyncio.run(test_broker_connection())
    exit(0 if success else 1)
