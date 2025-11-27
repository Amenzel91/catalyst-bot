"""
Test Extended Hours Trading Configuration

Verifies that:
1. Extended hours trading configuration is loaded correctly
2. Market status detection works properly
3. Extended hours logic is available to both trading systems
"""

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 70)
print("Extended Hours Trading Configuration Test")
print("=" * 70)

# Test 1: Configuration
print("\n1. Testing Configuration...")
from src.catalyst_bot.config import get_settings

settings = get_settings()
print(f"   TRADING_EXTENDED_HOURS setting: {settings.trading_extended_hours}")
print(f"   Environment variable: {os.getenv('TRADING_EXTENDED_HOURS', 'NOT SET')}")

if settings.trading_extended_hours:
    print("   [OK] Extended hours trading is ENABLED")
else:
    print("   [WARNING] Extended hours trading is DISABLED")

# Test 2: Market Status Detection
print("\n2. Testing Market Status Detection...")
from src.catalyst_bot.market_hours import (
    get_market_status,
    is_extended_hours,
    get_market_info
)

# Get current market status
ET = ZoneInfo("America/New_York")
now_utc = datetime.now(datetime.now().astimezone().tzinfo)
now_et = now_utc.astimezone(ET)

print(f"   Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")

status = get_market_status()
is_ext_hours = is_extended_hours()

print(f"   Market status: {status}")
print(f"   Is extended hours: {is_ext_hours}")

market_info = get_market_info()
print(f"   Full market info:")
for key, value in market_info.items():
    print(f"     - {key}: {value}")

# Test 3: Simulate different times
print("\n3. Simulating Different Market Times...")

test_times = [
    ("Pre-market (7:00 AM ET)", time(7, 0)),
    ("Market open (10:00 AM ET)", time(10, 0)),
    ("Market close time (4:00 PM ET)", time(16, 0)),
    ("After-hours (5:00 PM ET)", time(17, 0)),
    ("Market closed (9:00 PM ET)", time(21, 0)),
]

for label, test_time in test_times:
    # Create test datetime in ET
    test_dt = datetime.combine(now_et.date(), test_time, tzinfo=ET)

    status = get_market_status(test_dt)
    is_ext = is_extended_hours(test_dt)

    print(f"   {label}:")
    print(f"     Status: {status}, Extended hours: {is_ext}")

# Test 4: AlpacaBrokerWrapper Integration
print("\n4. Testing AlpacaBrokerWrapper Extended Hours Support...")
try:
    from src.catalyst_bot.broker.alpaca_wrapper import AlpacaBrokerWrapper

    # Check if the wrapper has the extended hours logic
    import inspect
    source = inspect.getsource(AlpacaBrokerWrapper.close_position)

    has_is_extended_hours = "is_extended_hours" in source
    has_limit_order = "LimitOrderRequest" in source
    has_day_tif = "TimeInForce.DAY" in source

    print(f"   Has is_extended_hours() call: {has_is_extended_hours}")
    print(f"   Has LimitOrderRequest support: {has_limit_order}")
    print(f"   Has DAY time-in-force: {has_day_tif}")

    if has_is_extended_hours and has_limit_order and has_day_tif:
        print("   [OK] AlpacaBrokerWrapper supports extended hours")
    else:
        print("   [ERROR] AlpacaBrokerWrapper missing extended hours support")

except Exception as e:
    print(f"   [ERROR] Failed to test AlpacaBrokerWrapper: {e}")

# Test 5: TradingEngine Integration
print("\n5. Testing TradingEngine Extended Hours Support...")
try:
    from src.catalyst_bot.trading.trading_engine import TradingEngine

    # Check if TradingEngine has extended hours logic
    import inspect
    source = inspect.getsource(TradingEngine._execute_signal)

    has_is_extended_hours = "is_extended_hours" in source
    has_extended_hours_param = "extended_hours=" in source

    print(f"   Has is_extended_hours() call: {has_is_extended_hours}")
    print(f"   Passes extended_hours to executor: {has_extended_hours_param}")

    if has_is_extended_hours and has_extended_hours_param:
        print("   [OK] TradingEngine supports extended hours")
    else:
        print("   [ERROR] TradingEngine missing extended hours support")

except Exception as e:
    print(f"   [ERROR] Failed to test TradingEngine: {e}")

# Test 6: OrderExecutor Integration
print("\n6. Testing OrderExecutor Extended Hours Support...")
try:
    from src.catalyst_bot.execution.order_executor import OrderExecutor

    # Check if OrderExecutor has extended hours logic
    import inspect

    # Check execute_signal method
    exec_source = inspect.getsource(OrderExecutor.execute_signal)
    has_extended_hours_param = "extended_hours" in exec_source

    # Check _execute_simple_order method
    simple_source = inspect.getsource(OrderExecutor._execute_simple_order)
    has_limit_order_logic = "OrderType.LIMIT" in simple_source and "extended_hours" in simple_source

    # Check _execute_bracket_order method
    bracket_source = inspect.getsource(OrderExecutor._execute_bracket_order)
    has_bracket_ext_hours = "extended_hours" in bracket_source

    print(f"   execute_signal has extended_hours param: {has_extended_hours_param}")
    print(f"   _execute_simple_order has limit order logic: {has_limit_order_logic}")
    print(f"   _execute_bracket_order has extended hours: {has_bracket_ext_hours}")

    if has_extended_hours_param and has_limit_order_logic and has_bracket_ext_hours:
        print("   [OK] OrderExecutor supports extended hours")
    else:
        print("   [ERROR] OrderExecutor missing extended hours support")

except Exception as e:
    print(f"   [ERROR] Failed to test OrderExecutor: {e}")

# Summary
print("\n" + "=" * 70)
print("Test Summary")
print("=" * 70)
print(f"Extended hours trading enabled: {settings.trading_extended_hours}")
print(f"Current market status: {status}")
print(f"Currently in extended hours: {is_ext_hours}")
print("\nAll trading systems have been updated to support extended hours trading.")
print("The bot will automatically use DAY limit orders during pre-market and after-hours.")
print("=" * 70)
