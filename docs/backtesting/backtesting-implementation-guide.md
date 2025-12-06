# Backtesting Implementation Guide - Practical Examples

## Overview

This document provides practical implementation examples and code patterns for the backtesting frameworks discussed in the main research document. Use these as starting points for implementing your own trading strategies.

---

## 1. VectorBT Implementation Examples

### 1.1 Basic Moving Average Crossover Strategy

```python
import vectorbt as vbt
import pandas as pd
import numpy as np

# Download data
symbol = 'AAPL'
start = '2020-01-01'
end = '2025-01-01'

data = vbt.YFData.download(symbol, start=start, end=end).get('Close')

# Define parameters
fast_windows = [10, 20, 30]
slow_windows = [50, 100, 200]

# Calculate moving averages (broadcasting)
fast_ma = vbt.MA.run(data, window=fast_windows)
slow_ma = vbt.MA.run(data, window=slow_windows)

# Generate entry and exit signals
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# Run backtest
portfolio = vbt.Portfolio.from_signals(
    data,
    entries=entries,
    exits=exits,
    init_cash=10000,
    fees=0.001,  # 0.1% commission
    slippage=0.001  # 0.1% slippage
)

# Get performance metrics
print(portfolio.stats())
print(f"Sharpe Ratio: {portfolio.sharpe_ratio()}")
print(f"Max Drawdown: {portfolio.max_drawdown()}")
print(f"Total Return: {portfolio.total_return()}")

# Plot results
portfolio.plot().show()
```

### 1.2 Walk-Forward Optimization with VectorBT

```python
import vectorbt as vbt
import pandas as pd
from datetime import datetime, timedelta

# Download data
data = vbt.YFData.download('SPY', start='2018-01-01', end='2025-01-01').get('Close')

# Walk-forward parameters
in_sample_days = 252  # 1 year
out_sample_days = 63  # 3 months
step_days = 63  # Advance by 3 months

# Parameters to optimize
fast_windows = np.arange(10, 50, 5)
slow_windows = np.arange(50, 200, 10)

# Storage for results
wf_results = []

# Walk-forward loop
start_idx = 0
while start_idx + in_sample_days + out_sample_days < len(data):
    # Define in-sample and out-of-sample periods
    is_end_idx = start_idx + in_sample_days
    oos_end_idx = is_end_idx + out_sample_days

    is_data = data.iloc[start_idx:is_end_idx]
    oos_data = data.iloc[is_end_idx:oos_end_idx]

    # Optimize on in-sample data
    fast_ma_is = vbt.MA.run(is_data, window=fast_windows)
    slow_ma_is = vbt.MA.run(is_data, window=slow_windows)

    entries_is = fast_ma_is.ma_crossed_above(slow_ma_is)
    exits_is = fast_ma_is.ma_crossed_below(slow_ma_is)

    portfolio_is = vbt.Portfolio.from_signals(
        is_data, entries_is, exits_is,
        init_cash=10000, fees=0.001, slippage=0.001
    )

    # Find best parameters
    best_idx = portfolio_is.sharpe_ratio().idxmax()
    best_fast = best_idx[0] if isinstance(best_idx, tuple) else fast_windows[0]
    best_slow = best_idx[1] if isinstance(best_idx, tuple) else slow_windows[0]

    # Test on out-of-sample data
    fast_ma_oos = vbt.MA.run(oos_data, window=best_fast)
    slow_ma_oos = vbt.MA.run(oos_data, window=best_slow)

    entries_oos = fast_ma_oos.ma_crossed_above(slow_ma_oos)
    exits_oos = fast_ma_oos.ma_crossed_below(slow_ma_oos)

    portfolio_oos = vbt.Portfolio.from_signals(
        oos_data, entries_oos, exits_oos,
        init_cash=10000, fees=0.001, slippage=0.001
    )

    # Store results
    wf_results.append({
        'period': f"{data.index[is_end_idx]} to {data.index[oos_end_idx-1]}",
        'best_fast': best_fast,
        'best_slow': best_slow,
        'is_sharpe': portfolio_is.sharpe_ratio().max(),
        'oos_sharpe': portfolio_oos.sharpe_ratio(),
        'oos_return': portfolio_oos.total_return()
    })

    # Advance window
    start_idx += step_days

# Analyze walk-forward results
wf_df = pd.DataFrame(wf_results)
print("\nWalk-Forward Results:")
print(wf_df)
print(f"\nAverage OOS Sharpe: {wf_df['oos_sharpe'].mean():.2f}")
print(f"Average OOS Return: {wf_df['oos_return'].mean():.2%}")
```

### 1.3 Multiple Asset Portfolio with VectorBT

```python
import vectorbt as vbt
import numpy as np

# Download multiple assets
symbols = ['SPY', 'QQQ', 'IWM', 'EFA', 'AGG']
data = vbt.YFData.download(symbols, start='2020-01-01').get('Close')

# Momentum strategy: Buy top 2 performers each month
lookback = 60  # 3 months
rebalance_freq = '1M'

# Calculate momentum for each asset
returns = data.pct_change(lookback)

# Create signals: Buy top 2, sell others
def create_rotation_signals(returns_df, top_n=2):
    entries = pd.DataFrame(False, index=returns_df.index, columns=returns_df.columns)
    exits = pd.DataFrame(False, index=returns_df.index, columns=returns_df.columns)

    for date in returns_df.resample(rebalance_freq).last().index:
        if date in returns_df.index:
            # Rank assets by momentum
            momentum = returns_df.loc[date]
            top_assets = momentum.nlargest(top_n).index

            # Set signals
            entries.loc[date, top_assets] = True
            exits.loc[date, ~entries.columns.isin(top_assets)] = True

    return entries, exits

entries, exits = create_rotation_signals(returns, top_n=2)

# Run backtest
portfolio = vbt.Portfolio.from_signals(
    data,
    entries=entries,
    exits=exits,
    init_cash=10000,
    fees=0.001,
    slippage=0.001,
    size=0.5,  # 50% of available cash per position
    size_type='percent'
)

print(portfolio.stats())
```

---

## 2. backtesting.py Implementation Examples

### 2.1 Basic Strategy Template

```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA
import pandas as pd

class SmaCross(Strategy):
    # Define parameters
    n1 = 10  # Fast MA period
    n2 = 20  # Slow MA period

    def init(self):
        # Precompute indicators
        close = self.data.Close
        self.sma1 = self.I(SMA, close, self.n1)
        self.sma2 = self.I(SMA, close, self.n2)

    def next(self):
        # Trading logic executed on each bar

        # Entry condition
        if crossover(self.sma1, self.sma2):
            self.buy()

        # Exit condition
        elif crossover(self.sma2, self.sma1):
            self.position.close()

# Load data
df = pd.read_csv('AAPL.csv', index_col=0, parse_dates=True)

# Run backtest
bt = Backtest(
    df,
    SmaCross,
    cash=10000,
    commission=0.001,  # 0.1%
    exclusive_orders=True
)

# Run with default parameters
stats = bt.run()
print(stats)

# Optimize parameters
stats = bt.optimize(
    n1=range(5, 50, 5),
    n2=range(20, 200, 10),
    maximize='Sharpe Ratio',
    constraint=lambda param: param.n1 < param.n2
)

print(stats)
bt.plot()
```

### 2.2 Advanced Strategy with Risk Management

```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import talib
import pandas as pd

class MomentumStrategy(Strategy):
    lookback = 20
    rsi_period = 14
    stop_loss = 0.02  # 2% stop loss
    take_profit = 0.06  # 6% take profit

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low

        # Calculate indicators
        self.rsi = self.I(talib.RSI, close, self.rsi_period)
        self.returns = self.I(lambda x: pd.Series(x).pct_change(self.lookback), close)

    def next(self):
        price = self.data.Close[-1]

        # Entry logic
        if not self.position:
            # Buy if momentum positive and RSI not overbought
            if self.returns[-1] > 0 and self.rsi[-1] < 70:
                self.buy(sl=price * (1 - self.stop_loss),
                        tp=price * (1 + self.take_profit))

        # Exit logic (beyond stop/take profit)
        else:
            # Exit if RSI becomes overbought
            if self.rsi[-1] > 80:
                self.position.close()

# Load data
df = pd.read_csv('SPY.csv', index_col=0, parse_dates=True)

# Run backtest
bt = Backtest(df, MomentumStrategy, cash=10000, commission=0.001)
stats = bt.run()
print(stats)
```

### 2.3 Walk-Forward Analysis with backtesting.py

```python
from backtesting import Backtest, Strategy
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class OptimizableStrategy(Strategy):
    n1 = 10
    n2 = 50

    def init(self):
        close = self.data.Close
        self.sma1 = self.I(SMA, close, self.n1)
        self.sma2 = self.I(SMA, close, self.n2)

    def next(self):
        if crossover(self.sma1, self.sma2):
            self.buy()
        elif crossover(self.sma2, self.sma1):
            self.position.close()

def walk_forward_analysis(data, in_sample_days=252, out_sample_days=63, step_days=63):
    """
    Perform walk-forward analysis
    """
    results = []

    start = 0
    while start + in_sample_days + out_sample_days < len(data):
        # Split data
        is_end = start + in_sample_days
        oos_end = is_end + out_sample_days

        is_data = data.iloc[start:is_end]
        oos_data = data.iloc[is_end:oos_end]

        # Optimize on in-sample
        bt_is = Backtest(is_data, OptimizableStrategy, cash=10000, commission=0.001)
        stats_is = bt_is.optimize(
            n1=range(5, 50, 5),
            n2=range(20, 200, 20),
            maximize='Sharpe Ratio',
            constraint=lambda p: p.n1 < p.n2
        )

        # Get best parameters
        best_n1 = stats_is._strategy.n1
        best_n2 = stats_is._strategy.n2

        # Test on out-of-sample
        bt_oos = Backtest(oos_data, OptimizableStrategy, cash=10000, commission=0.001)
        stats_oos = bt_oos.run(n1=best_n1, n2=best_n2)

        # Store results
        results.append({
            'period': f"{oos_data.index[0]} to {oos_data.index[-1]}",
            'n1': best_n1,
            'n2': best_n2,
            'is_sharpe': stats_is['Sharpe Ratio'],
            'oos_sharpe': stats_oos['Sharpe Ratio'],
            'oos_return': stats_oos['Return [%]']
        })

        start += step_days

    return pd.DataFrame(results)

# Load data
df = pd.read_csv('SPY.csv', index_col=0, parse_dates=True)

# Run walk-forward analysis
wf_results = walk_forward_analysis(df)
print(wf_results)
print(f"\nAverage OOS Sharpe: {wf_results['oos_sharpe'].mean():.2f}")
```

---

## 3. Backtrader Implementation Examples

### 3.1 Basic Strategy with Backtrader

```python
import backtrader as bt
import datetime

class SMAStrategy(bt.Strategy):
    params = (
        ('fast_period', 10),
        ('slow_period', 30),
    )

    def __init__(self):
        # Keep reference to close prices
        self.dataclose = self.datas[0].close

        # Create indicators
        self.sma_fast = bt.indicators.SimpleMovingAverage(
            self.dataclose, period=self.params.fast_period
        )
        self.sma_slow = bt.indicators.SimpleMovingAverage(
            self.dataclose, period=self.params.slow_period
        )

        # Crossover signal
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)

    def next(self):
        # Entry
        if not self.position:
            if self.crossover > 0:
                self.buy()

        # Exit
        else:
            if self.crossover < 0:
                self.close()

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED, Price: {order.executed.price:.2f}')
            elif order.issell():
                self.log(f'SELL EXECUTED, Price: {order.executed.price:.2f}')

    def log(self, txt):
        dt = self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} {txt}')

# Initialize Cerebro
cerebro = bt.Cerebro()

# Add strategy
cerebro.addstrategy(SMAStrategy)

# Load data
data = bt.feeds.YahooFinanceData(
    dataname='AAPL',
    fromdate=datetime.datetime(2020, 1, 1),
    todate=datetime.datetime(2025, 1, 1)
)
cerebro.adddata(data)

# Set initial cash
cerebro.broker.setcash(10000.0)

# Set commission
cerebro.broker.setcommission(commission=0.001)

# Add analyzers
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

# Run backtest
print(f'Starting Portfolio Value: {cerebro.broker.getvalue():.2f}')
results = cerebro.run()
print(f'Final Portfolio Value: {cerebro.broker.getvalue():.2f}')

# Get analysis
strat = results[0]
print(f"Sharpe Ratio: {strat.analyzers.sharpe.get_analysis()['sharperatio']:.2f}")
print(f"Max Drawdown: {strat.analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%")
print(f"Total Return: {strat.analyzers.returns.get_analysis()['rtot']:.2%}")

# Plot
cerebro.plot()
```

### 3.2 Alpaca Integration with Backtrader

```python
import backtrader as bt
from alpaca_backtrader_api import AlpacaStore
import datetime

class LiveStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SimpleMovingAverage(period=20)

    def next(self):
        if not self.position:
            if self.data.close[0] > self.sma[0]:
                self.buy()
        else:
            if self.data.close[0] < self.sma[0]:
                self.close()

# Alpaca credentials
ALPACA_API_KEY = 'your_api_key'
ALPACA_SECRET_KEY = 'your_secret_key'
ALPACA_PAPER = True  # Use paper trading

# Initialize Cerebro
cerebro = bt.Cerebro()

# Create Alpaca store
store = AlpacaStore(
    key_id=ALPACA_API_KEY,
    secret_key=ALPACA_SECRET_KEY,
    paper=ALPACA_PAPER
)

# Set broker
cerebro.setbroker(store.getbroker())

# Add data feed
data = store.getdata(
    dataname='AAPL',
    timeframe=bt.TimeFrame.Days,
    historical=True,
    fromdate=datetime.datetime(2024, 1, 1),
    todate=datetime.datetime(2025, 1, 1)
)
cerebro.adddata(data)

# Add strategy
cerebro.addstrategy(LiveStrategy)

# Run
cerebro.run()
```

---

## 4. QuantConnect LEAN Implementation

### 4.1 Basic Algorithm Template

```python
from AlgorithmImports import *

class BasicAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Set start and end dates
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2025, 1, 1)

        # Set initial cash
        self.SetCash(10000)

        # Add equity
        self.symbol = self.AddEquity("SPY", Resolution.Daily).Symbol

        # Create indicators
        self.fast_sma = self.SMA(self.symbol, 10, Resolution.Daily)
        self.slow_sma = self.SMA(self.symbol, 30, Resolution.Daily)

        # Warm up indicators
        self.SetWarmUp(30)

    def OnData(self, data):
        # Skip if warming up
        if self.IsWarmingUp:
            return

        # Check if data exists
        if not data.ContainsKey(self.symbol):
            return

        # Trading logic
        if not self.Portfolio.Invested:
            if self.fast_sma.Current.Value > self.slow_sma.Current.Value:
                self.SetHoldings(self.symbol, 1.0)
                self.Debug(f"BUY at {data[self.symbol].Close}")

        else:
            if self.fast_sma.Current.Value < self.slow_sma.Current.Value:
                self.Liquidate(self.symbol)
                self.Debug(f"SELL at {data[self.symbol].Close}")
```

### 4.2 Multi-Asset Momentum Strategy

```python
from AlgorithmImports import *

class MomentumRotation(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(100000)

        # Universe of ETFs
        self.symbols = [
            self.AddEquity("SPY", Resolution.Daily).Symbol,
            self.AddEquity("QQQ", Resolution.Daily).Symbol,
            self.AddEquity("IWM", Resolution.Daily).Symbol,
            self.AddEquity("EFA", Resolution.Daily).Symbol,
            self.AddEquity("AGG", Resolution.Daily).Symbol
        ]

        # Momentum lookback
        self.lookback = 60
        self.num_positions = 2

        # Schedule rebalancing
        self.Schedule.On(
            self.DateRules.MonthStart(self.symbols[0]),
            self.TimeRules.AfterMarketOpen(self.symbols[0], 30),
            self.Rebalance
        )

    def Rebalance(self):
        # Calculate momentum for each symbol
        momentum = {}
        for symbol in self.symbols:
            history = self.History(symbol, self.lookback, Resolution.Daily)
            if len(history) < self.lookback:
                continue

            # Calculate return
            start_price = history['close'].iloc[0]
            end_price = history['close'].iloc[-1]
            momentum[symbol] = (end_price - start_price) / start_price

        # Sort by momentum
        sorted_symbols = sorted(momentum.items(), key=lambda x: x[1], reverse=True)

        # Select top performers
        winners = [x[0] for x in sorted_symbols[:self.num_positions]]

        # Liquidate positions not in winners
        for symbol in self.symbols:
            if symbol not in winners and self.Portfolio[symbol].Invested:
                self.Liquidate(symbol)

        # Equal weight in winners
        weight = 1.0 / self.num_positions
        for symbol in winners:
            self.SetHoldings(symbol, weight)
            self.Debug(f"Holding {symbol} with momentum {momentum[symbol]:.2%}")
```

---

## 5. Common Implementation Patterns

### 5.1 Data Loading and Preprocessing

```python
import pandas as pd
import yfinance as yf

def load_data(symbol, start, end):
    """Load and preprocess price data"""
    df = yf.download(symbol, start=start, end=end)

    # Ensure proper column names
    df.columns = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']

    # Use adjusted close for calculations
    df['Close'] = df['Adj Close']

    # Remove unnecessary column
    df = df.drop('Adj Close', axis=1)

    # Handle missing data
    df = df.dropna()

    return df

# Multiple symbols
def load_multiple_symbols(symbols, start, end):
    """Load data for multiple symbols"""
    data = {}
    for symbol in symbols:
        data[symbol] = load_data(symbol, start, end)
    return data
```

### 5.2 Performance Metrics Calculation

```python
import numpy as np
import pandas as pd

def calculate_metrics(returns, risk_free_rate=0.02):
    """
    Calculate comprehensive performance metrics

    Parameters:
    - returns: pandas Series of daily returns
    - risk_free_rate: annual risk-free rate (default 2%)
    """
    # Annualization factor
    periods_per_year = 252

    # Total return
    total_return = (1 + returns).prod() - 1

    # Annualized return
    years = len(returns) / periods_per_year
    annualized_return = (1 + total_return) ** (1 / years) - 1

    # Volatility
    volatility = returns.std() * np.sqrt(periods_per_year)

    # Sharpe Ratio
    excess_returns = returns - risk_free_rate / periods_per_year
    sharpe_ratio = np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()

    # Sortino Ratio
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() * np.sqrt(periods_per_year)
    sortino_ratio = (annualized_return - risk_free_rate) / downside_std

    # Maximum Drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    # Calmar Ratio
    calmar_ratio = annualized_return / abs(max_drawdown)

    # Win Rate
    win_rate = (returns > 0).sum() / len(returns)

    # Profit Factor
    gross_profits = returns[returns > 0].sum()
    gross_losses = abs(returns[returns < 0].sum())
    profit_factor = gross_profits / gross_losses if gross_losses != 0 else np.inf

    return {
        'Total Return': f"{total_return:.2%}",
        'Annual Return': f"{annualized_return:.2%}",
        'Volatility': f"{volatility:.2%}",
        'Sharpe Ratio': f"{sharpe_ratio:.2f}",
        'Sortino Ratio': f"{sortino_ratio:.2f}",
        'Calmar Ratio': f"{calmar_ratio:.2f}",
        'Max Drawdown': f"{max_drawdown:.2%}",
        'Win Rate': f"{win_rate:.2%}",
        'Profit Factor': f"{profit_factor:.2f}",
        'Number of Trades': len(returns)
    }

# Usage
portfolio_returns = pd.Series([...])  # Your strategy returns
metrics = calculate_metrics(portfolio_returns)
for key, value in metrics.items():
    print(f"{key}: {value}")
```

### 5.3 Slippage and Commission Models

```python
class TransactionCostModel:
    """Model for transaction costs"""

    def __init__(self, commission_rate=0.001, slippage_rate=0.001):
        """
        Parameters:
        - commission_rate: Fixed percentage commission (e.g., 0.001 = 0.1%)
        - slippage_rate: Expected slippage percentage
        """
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    def calculate_cost(self, price, shares, is_buy=True):
        """Calculate total transaction cost"""

        # Base cost
        notional = price * shares

        # Commission
        commission = notional * self.commission_rate

        # Slippage
        slippage_direction = 1 if is_buy else -1
        slippage = notional * self.slippage_rate * slippage_direction

        total_cost = commission + abs(slippage)

        return {
            'commission': commission,
            'slippage': slippage,
            'total_cost': total_cost,
            'effective_price': price * (1 + slippage_direction * self.slippage_rate)
        }

# Usage
cost_model = TransactionCostModel(commission_rate=0.001, slippage_rate=0.001)
buy_cost = cost_model.calculate_cost(price=100, shares=100, is_buy=True)
print(f"Total transaction cost: ${buy_cost['total_cost']:.2f}")
print(f"Effective buy price: ${buy_cost['effective_price']:.2f}")
```

### 5.4 Position Sizing

```python
class PositionSizer:
    """Various position sizing methods"""

    @staticmethod
    def fixed_fractional(account_value, risk_per_trade=0.02):
        """Risk fixed percentage of account per trade"""
        return account_value * risk_per_trade

    @staticmethod
    def kelly_criterion(win_rate, avg_win, avg_loss):
        """Kelly Criterion for optimal position sizing"""
        win_loss_ratio = avg_win / avg_loss
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        # Use half-Kelly for safety
        return max(0, kelly / 2)

    @staticmethod
    def volatility_based(account_value, target_volatility, asset_volatility):
        """Size based on volatility targeting"""
        return account_value * (target_volatility / asset_volatility)

    @staticmethod
    def shares_from_risk(account_value, risk_per_trade, entry_price, stop_loss_price):
        """Calculate shares based on risk and stop loss"""
        risk_amount = account_value * risk_per_trade
        risk_per_share = abs(entry_price - stop_loss_price)
        shares = int(risk_amount / risk_per_share)
        return shares

# Usage
account = 10000
shares = PositionSizer.shares_from_risk(
    account_value=account,
    risk_per_trade=0.02,  # 2% risk
    entry_price=100,
    stop_loss_price=98
)
print(f"Position size: {shares} shares")
```

---

## 6. Data Sources and APIs

### 6.1 Free Data Sources

```python
import yfinance as yf
import pandas_datareader as pdr

# Yahoo Finance (yfinance)
def get_yahoo_data(symbol, start, end):
    return yf.download(symbol, start=start, end=end)

# Alpha Vantage
from alpha_vantage.timeseries import TimeSeries

def get_alpha_vantage_data(symbol, api_key):
    ts = TimeSeries(key=api_key, output_format='pandas')
    data, meta = ts.get_daily(symbol=symbol, outputsize='full')
    return data

# Polygon.io (2 years free)
import requests

def get_polygon_data(symbol, start, end, api_key):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}"
    params = {'apiKey': api_key}
    response = requests.get(url, params=params)
    return response.json()
```

### 6.2 Crypto Data

```python
import ccxt

def get_crypto_data(exchange_name='binance', symbol='BTC/USDT', timeframe='1d', limit=365):
    """Get cryptocurrency data from exchanges"""
    exchange = getattr(ccxt, exchange_name)()

    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    df = pd.DataFrame(
        ohlcv,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    return df
```

---

## 7. Testing and Validation Checklist

### 7.1 Pre-Deployment Checklist

```python
def validate_strategy(strategy_results):
    """
    Validate strategy before live deployment
    Returns: dict with validation results
    """
    validation = {
        'passed': True,
        'warnings': [],
        'errors': []
    }

    # Check Sharpe Ratio
    if strategy_results['sharpe_ratio'] < 1.0:
        validation['errors'].append("Sharpe Ratio < 1.0 (too low)")
        validation['passed'] = False
    elif strategy_results['sharpe_ratio'] > 3.0:
        validation['warnings'].append("Sharpe Ratio > 3.0 (possible overfitting)")

    # Check Maximum Drawdown
    if abs(strategy_results['max_drawdown']) > 0.20:
        validation['errors'].append("Max Drawdown > 20% (too high)")
        validation['passed'] = False

    # Check Profit Factor
    if strategy_results['profit_factor'] < 1.5:
        validation['warnings'].append("Profit Factor < 1.5 (marginal)")

    # Check number of trades
    if strategy_results['num_trades'] < 30:
        validation['warnings'].append("< 30 trades (small sample size)")

    # Check OOS performance vs IS
    if 'oos_sharpe' in strategy_results and 'is_sharpe' in strategy_results:
        degradation = (strategy_results['is_sharpe'] - strategy_results['oos_sharpe']) / strategy_results['is_sharpe']
        if degradation > 0.3:
            validation['warnings'].append(f"OOS performance degraded {degradation:.1%} vs IS")

    return validation

# Usage
results = {
    'sharpe_ratio': 2.1,
    'max_drawdown': -0.12,
    'profit_factor': 1.8,
    'num_trades': 45,
    'is_sharpe': 2.5,
    'oos_sharpe': 2.1
}

validation = validate_strategy(results)
if validation['passed']:
    print("✓ Strategy validation passed")
else:
    print("✗ Strategy validation failed")

for error in validation['errors']:
    print(f"  ERROR: {error}")
for warning in validation['warnings']:
    print(f"  WARNING: {warning}")
```

---

## 8. Quick Start Recommendations

### For Beginners
1. Start with **backtesting.py**
2. Implement simple moving average crossover
3. Learn to interpret basic metrics
4. Progress to more complex strategies

### For Intermediate
1. Use **VectorBT** for rapid testing
2. Implement walk-forward optimization
3. Test multiple parameter combinations
4. Integrate with Alpaca for paper trading

### For Advanced
1. Use **QuantConnect LEAN** for production
2. Multi-asset portfolio strategies
3. Custom data sources
4. Professional risk management

---

## 9. Common Gotchas and Solutions

### Issue 1: Look-Ahead Bias in Indicators
```python
# WRONG - Uses current bar close
if current_close > sma[-1]:  # SMA includes current bar
    buy()

# CORRECT - Uses only past data
if previous_close > sma[-2]:  # SMA from previous bar
    buy()
```

### Issue 2: Unrealistic Fill Assumptions
```python
# Add realistic slippage and commissions
portfolio = vbt.Portfolio.from_signals(
    data, entries, exits,
    init_cash=10000,
    fees=0.001,  # 0.1% commission
    slippage=0.001  # 0.1% slippage
)
```

### Issue 3: Overfitting in Optimization
```python
# Limit parameter space
# WRONG - too many combinations
fast = range(1, 100, 1)  # 100 values
slow = range(1, 200, 1)  # 200 values
# = 20,000 combinations

# CORRECT - reasonable grid
fast = range(5, 50, 5)   # 9 values
slow = range(20, 200, 20)  # 9 values
# = 81 combinations
```

---

## Conclusion

These implementation examples provide practical starting points for building your trading system. Remember to:

1. Start simple
2. Validate thoroughly
3. Use walk-forward optimization
4. Model costs realistically
5. Paper trade extensively before going live

Refer to the main research document for theoretical background and framework comparisons.
