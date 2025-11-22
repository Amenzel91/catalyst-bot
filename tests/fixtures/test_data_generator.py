"""Test data generators for paper trading bot tests."""

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal


def generate_random_price(
    base_price: float = 100.0,
    volatility: float = 0.02,
    trend: float = 0.0,
) -> float:
    """
    Generate a random price using GBM.

    Args:
        base_price: Starting price
        volatility: Price volatility (std dev of returns)
        trend: Expected return

    Returns:
        New price
    """
    return_val = random.gauss(trend, volatility)
    new_price = base_price * (1 + return_val)
    return round(new_price, 2)


def generate_order_book(
    symbol: str = "AAPL",
    mid_price: float = 175.00,
    spread_bps: float = 2.0,
    levels: int = 5,
) -> Dict[str, List[Tuple[float, int]]]:
    """
    Generate a realistic order book.

    Args:
        symbol: Stock symbol
        mid_price: Mid-market price
        spread_bps: Bid-ask spread in basis points
        levels: Number of price levels on each side

    Returns:
        Dictionary with 'bids' and 'asks' lists of (price, size) tuples
    """
    spread = mid_price * (spread_bps / 10000)
    half_spread = spread / 2

    bids = []
    asks = []

    # Generate bid levels
    for i in range(levels):
        level_offset = i * spread
        bid_price = round(mid_price - half_spread - level_offset, 2)
        bid_size = random.randint(100, 1000) * 100
        bids.append((bid_price, bid_size))

    # Generate ask levels
    for i in range(levels):
        level_offset = i * spread
        ask_price = round(mid_price + half_spread + level_offset, 2)
        ask_size = random.randint(100, 1000) * 100
        asks.append((ask_price, ask_size))

    return {
        "symbol": symbol,
        "bids": bids,
        "asks": asks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def generate_trade_history(
    num_trades: int = 10,
    tickers: Optional[List[str]] = None,
    win_rate: float = 0.6,
) -> List[Dict]:
    """
    Generate synthetic trade history for backtesting.

    Args:
        num_trades: Number of trades to generate
        tickers: List of tickers to use (default: common stocks)
        win_rate: Percentage of winning trades

    Returns:
        List of trade dictionaries
    """
    if tickers is None:
        tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]

    trades = []
    base_date = datetime.now(timezone.utc) - timedelta(days=num_trades * 2)

    for i in range(num_trades):
        ticker = random.choice(tickers)
        entry_price = random.uniform(50, 500)
        quantity = random.randint(10, 200)

        # Determine if winning or losing trade
        is_winner = random.random() < win_rate

        if is_winner:
            # Winning trade: 2-10% profit
            pnl_pct = random.uniform(0.02, 0.10)
        else:
            # Losing trade: 1-5% loss
            pnl_pct = -random.uniform(0.01, 0.05)

        exit_price = entry_price * (1 + pnl_pct)
        pnl = (exit_price - entry_price) * quantity

        entry_time = base_date + timedelta(days=i * 2)
        hold_time = random.randint(30, 480)  # 30 min to 8 hours
        exit_time = entry_time + timedelta(minutes=hold_time)

        trade = {
            "id": f"trade-{uuid.uuid4()}",
            "ticker": ticker,
            "quantity": quantity,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "entry_time": entry_time.isoformat(),
            "exit_time": exit_time.isoformat(),
            "hold_time_minutes": hold_time,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 2),
            "signal_type": random.choice(["breakout", "earnings", "insider_buying"]),
            "exit_reason": "take_profit" if is_winner else "stop_loss",
        }

        trades.append(trade)

    return trades


def generate_portfolio_snapshot(
    total_value: float = 100000.00,
    num_positions: int = 3,
    cash_pct: float = 0.30,
) -> Dict:
    """
    Generate a portfolio snapshot.

    Args:
        total_value: Total portfolio value
        num_positions: Number of open positions
        cash_pct: Percentage held in cash

    Returns:
        Portfolio snapshot dictionary
    """
    cash = total_value * cash_pct
    positions_value = total_value - cash

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]
    selected_tickers = random.sample(tickers, min(num_positions, len(tickers)))

    positions = []
    remaining_value = positions_value

    for i, ticker in enumerate(selected_tickers):
        if i == len(selected_tickers) - 1:
            # Last position gets remaining value
            position_value = remaining_value
        else:
            # Allocate random portion
            position_value = remaining_value * random.uniform(0.2, 0.5)
            remaining_value -= position_value

        entry_price = random.uniform(50, 500)
        quantity = int(position_value / entry_price)
        current_price = entry_price * random.uniform(0.95, 1.10)  # -5% to +10%

        unrealized_pnl = (current_price - entry_price) * quantity

        positions.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "entry_price": round(entry_price, 2),
                "current_price": round(current_price, 2),
                "market_value": round(current_price * quantity, 2),
                "cost_basis": round(entry_price * quantity, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round((current_price / entry_price - 1) * 100, 2),
            }
        )

    total_unrealized_pnl = sum(p["unrealized_pnl"] for p in positions)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_value": round(total_value, 2),
        "cash": round(cash, 2),
        "positions_value": round(sum(p["market_value"] for p in positions), 2),
        "num_positions": len(positions),
        "unrealized_pnl": round(total_unrealized_pnl, 2),
        "positions": positions,
    }


def generate_risk_metrics(
    account_balance: float = 100000.00,
    position_size: float = 0.05,
    stop_loss_pct: float = 0.02,
) -> Dict:
    """
    Generate risk metrics for a trade.

    Args:
        account_balance: Total account balance
        position_size: Position size as fraction of account
        stop_loss_pct: Stop loss as percentage

    Returns:
        Risk metrics dictionary
    """
    position_value = account_balance * position_size
    risk_amount = position_value * stop_loss_pct

    return {
        "account_balance": round(account_balance, 2),
        "position_size_pct": round(position_size * 100, 2),
        "position_value": round(position_value, 2),
        "stop_loss_pct": round(stop_loss_pct * 100, 2),
        "risk_amount": round(risk_amount, 2),
        "risk_per_trade_pct": round((risk_amount / account_balance) * 100, 2),
        "reward_risk_ratio": round(random.uniform(2.0, 4.0), 2),
    }


def generate_backtesting_results(
    num_trades: int = 100,
    win_rate: float = 0.55,
    avg_win_pct: float = 0.05,
    avg_loss_pct: float = 0.02,
    starting_capital: float = 100000.00,
) -> Dict:
    """
    Generate realistic backtesting results.

    Args:
        num_trades: Number of trades
        win_rate: Percentage of winning trades
        avg_win_pct: Average winning trade percentage
        avg_loss_pct: Average losing trade percentage
        starting_capital: Starting capital

    Returns:
        Backtesting results dictionary
    """
    trades = generate_trade_history(num_trades=num_trades, win_rate=win_rate)

    total_pnl = sum(t["pnl"] for t in trades)
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] < 0]

    if winning_trades:
        avg_win = sum(t["pnl"] for t in winning_trades) / len(winning_trades)
        largest_win = max(t["pnl"] for t in winning_trades)
    else:
        avg_win = 0
        largest_win = 0

    if losing_trades:
        avg_loss = sum(t["pnl"] for t in losing_trades) / len(losing_trades)
        largest_loss = min(t["pnl"] for t in losing_trades)
    else:
        avg_loss = 0
        largest_loss = 0

    final_capital = starting_capital + total_pnl
    total_return_pct = (total_pnl / starting_capital) * 100

    # Calculate max drawdown
    equity_curve = [starting_capital]
    for trade in trades:
        equity_curve.append(equity_curve[-1] + trade["pnl"])

    peak = equity_curve[0]
    max_drawdown = 0
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return {
        "total_trades": num_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": round(len(winning_trades) / num_trades * 100, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "largest_win": round(largest_win, 2),
        "largest_loss": round(largest_loss, 2),
        "profit_factor": round(
            abs(sum(t["pnl"] for t in winning_trades) / sum(t["pnl"] for t in losing_trades))
            if losing_trades
            else float("inf"),
            2,
        ),
        "starting_capital": round(starting_capital, 2),
        "final_capital": round(final_capital, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(random.uniform(1.0, 2.5), 2),  # Simplified
        "trades": trades,
    }
