"""
Monte Carlo Simulation for Parameter Optimization
==================================================

Run Monte Carlo simulations to test parameter sensitivity and
find optimal strategy configurations.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import numpy as np

from ..logging_utils import get_logger
from .engine import BacktestEngine

log = get_logger("backtesting.monte_carlo")


class MonteCarloSimulator:
    """
    Run Monte Carlo simulations to test parameter sensitivity.

    Example: Test MIN_SCORE from 0.20 to 0.40 in 0.05 increments.
    Run 100 simulations per value, measure average Sharpe ratio.
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000.0,
        base_strategy_params: Optional[Dict] = None,
    ):
        """
        Initialize Monte Carlo simulator.

        Parameters
        ----------
        start_date : str
            Backtest start date (YYYY-MM-DD)
        end_date : str
            Backtest end date (YYYY-MM-DD)
        initial_capital : float
            Starting capital
        base_strategy_params : dict, optional
            Base strategy parameters (will be modified during sweep)
        """
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.base_strategy_params = base_strategy_params or {}

        log.info(
            "monte_carlo_initialized start=%s end=%s capital=%.2f",
            start_date,
            end_date,
            initial_capital,
        )

    def run_parameter_sweep(
        self,
        parameter: str,
        values: List[Any],
        num_simulations: int = 100,
        randomize: bool = True,
    ) -> Dict:
        """
        Test different parameter values and measure impact.

        Parameters
        ----------
        parameter : str
            Parameter name to sweep (e.g., 'min_score', 'take_profit_pct')
        values : list
            List of values to test
        num_simulations : int
            Number of simulations per value (with bootstrapping)
        randomize : bool
            Whether to randomize entry times slightly for each simulation

        Returns
        -------
        dict
            {
                'parameter': str,
                'results': [
                    {
                        'value': Any,
                        'avg_sharpe': float,
                        'avg_return_pct': float,
                        'avg_win_rate': float,
                        'std_dev_return': float,
                        'best_sharpe': float,
                        'worst_sharpe': float
                    },
                    ...
                ],
                'optimal_value': Any,
                'confidence': float
            }
        """
        log.info(
            "starting_parameter_sweep parameter=%s values=%d simulations=%d",
            parameter,
            len(values),
            num_simulations,
        )

        results = []

        for value in values:
            log.info("testing_value parameter=%s value=%s", parameter, value)

            # Create strategy params with this value
            strategy_params = self.base_strategy_params.copy()
            strategy_params[parameter] = value

            # Run multiple simulations
            simulation_results = []

            for sim_num in range(num_simulations):
                if randomize:
                    # Add small random variations to simulate different market conditions
                    random_seed = random.randint(0, 1000000)
                    random.seed(random_seed)

                try:
                    # Run backtest
                    engine = BacktestEngine(
                        start_date=self.start_date,
                        end_date=self.end_date,
                        initial_capital=self.initial_capital,
                        strategy_params=strategy_params,
                    )

                    result = engine.run_backtest()
                    metrics = result["metrics"]

                    simulation_results.append(
                        {
                            "sharpe": metrics.get("sharpe_ratio", 0),
                            "return_pct": metrics.get("total_return_pct", 0),
                            "win_rate": metrics.get("win_rate", 0),
                        }
                    )

                except Exception as e:
                    log.warning(
                        "simulation_failed parameter=%s value=%s sim=%d error=%s",
                        parameter,
                        value,
                        sim_num,
                        str(e),
                    )
                    continue

            if not simulation_results:
                log.warning(
                    "no_valid_simulations parameter=%s value=%s", parameter, value
                )
                continue

            # Calculate statistics
            sharpe_values = [r["sharpe"] for r in simulation_results]
            return_values = [r["return_pct"] for r in simulation_results]
            win_rate_values = [r["win_rate"] for r in simulation_results]

            avg_sharpe = np.mean(sharpe_values)
            avg_return = np.mean(return_values)
            avg_win_rate = np.mean(win_rate_values)
            std_dev_return = np.std(return_values)
            best_sharpe = np.max(sharpe_values)
            worst_sharpe = np.min(sharpe_values)

            results.append(
                {
                    "value": value,
                    "avg_sharpe": float(avg_sharpe),
                    "avg_return_pct": float(avg_return),
                    "avg_win_rate": float(avg_win_rate),
                    "std_dev_return": float(std_dev_return),
                    "best_sharpe": float(best_sharpe),
                    "worst_sharpe": float(worst_sharpe),
                    "num_simulations": len(simulation_results),
                }
            )

            log.info(
                "value_tested parameter=%s value=%s avg_sharpe=%.2f avg_return=%.2f%% "
                "avg_win_rate=%.1f%% std_dev=%.2f",
                parameter,
                value,
                avg_sharpe,
                avg_return,
                avg_win_rate * 100,
                std_dev_return,
            )

        # Find optimal value (highest average Sharpe)
        if results:
            optimal_result = max(results, key=lambda r: r["avg_sharpe"])
            optimal_value = optimal_result["value"]

            # Calculate confidence (inverse of std dev, normalized)
            confidence = 1.0 / (1.0 + optimal_result["std_dev_return"] / 10.0)
        else:
            optimal_value = None
            confidence = 0.0

        sweep_results = {
            "parameter": parameter,
            "results": results,
            "optimal_value": optimal_value,
            "confidence": float(confidence),
        }

        log.info(
            "parameter_sweep_complete parameter=%s optimal_value=%s confidence=%.2f",
            parameter,
            optimal_value,
            confidence,
        )

        return sweep_results

    def run_random_walk_simulation(
        self,
        num_simulations: int = 1000,
        num_trades_per_sim: int = 100,
    ) -> Dict:
        """
        Simulate random entry/exit to establish baseline.

        This helps determine if the bot performance is better than
        random chance.

        Parameters
        ----------
        num_simulations : int
            Number of random walk simulations
        num_trades_per_sim : int
            Number of trades per simulation

        Returns
        -------
        dict
            {
                'avg_return_pct': float,
                'std_dev_return': float,
                'avg_sharpe': float,
                'percentile_25': float,
                'percentile_50': float,
                'percentile_75': float
            }
        """
        log.info(
            "starting_random_walk num_simulations=%d trades_per_sim=%d",
            num_simulations,
            num_trades_per_sim,
        )

        simulation_returns = []

        for sim_num in range(num_simulations):
            # Simulate random trades
            # Penny stock moves: -20% to +50% with bias toward small losses
            trades = []
            for _ in range(num_trades_per_sim):
                # Random return with realistic penny stock distribution
                # 60% chance of loss, 40% chance of win (realistic for random trading)
                if random.random() < 0.6:
                    # Loss: -20% to -2%
                    ret = random.uniform(-20, -2)
                else:
                    # Win: +2% to +50%
                    ret = random.uniform(2, 50)

                trades.append(ret)

            # Calculate portfolio return (simplified)
            # Assuming equal position sizing
            avg_return = np.mean(trades)
            simulation_returns.append(avg_return)

        # Calculate statistics
        avg_return = np.mean(simulation_returns)
        std_dev = np.std(simulation_returns)
        percentile_25 = np.percentile(simulation_returns, 25)
        percentile_50 = np.percentile(simulation_returns, 50)
        percentile_75 = np.percentile(simulation_returns, 75)

        # Estimate Sharpe (simplified)
        sharpe = avg_return / std_dev if std_dev > 0 else 0

        results = {
            "avg_return_pct": float(avg_return),
            "std_dev_return": float(std_dev),
            "avg_sharpe": float(sharpe),
            "percentile_25": float(percentile_25),
            "percentile_50": float(percentile_50),
            "percentile_75": float(percentile_75),
        }

        log.info(
            "random_walk_complete avg_return=%.2f%% std_dev=%.2f sharpe=%.2f",
            avg_return,
            std_dev,
            sharpe,
        )

        return results

    def optimize_multi_parameter(
        self,
        parameters: Dict[str, List[Any]],
        num_iterations: int = 100,
        optimization_metric: str = "sharpe_ratio",
    ) -> Dict:
        """
        Optimize multiple parameters simultaneously using grid search.

        Parameters
        ----------
        parameters : dict
            Dict mapping parameter_name -> [list of values]
        num_iterations : int
            Number of iterations (for large grids, samples randomly)
        optimization_metric : str
            Metric to optimize ('sharpe_ratio', 'total_return_pct', 'win_rate')

        Returns
        -------
        dict
            {
                'optimal_params': dict,
                'optimal_metric_value': float,
                'all_results': list
            }
        """
        log.info(
            "starting_multi_parameter_optimization params=%s iterations=%d metric=%s",
            list(parameters.keys()),
            num_iterations,
            optimization_metric,
        )

        # Generate parameter combinations
        param_names = list(parameters.keys())
        param_values = list(parameters.values())

        # Calculate total combinations
        total_combinations = np.prod([len(v) for v in param_values])

        log.info("total_combinations=%d", total_combinations)

        # If too many combinations, sample randomly
        if total_combinations > num_iterations:
            log.info("sampling_combinations n=%d", num_iterations)
            combinations = []
            for _ in range(num_iterations):
                combo = {
                    name: random.choice(values) for name, values in parameters.items()
                }
                combinations.append(combo)
        else:
            # Generate all combinations
            import itertools

            combinations = []
            for combo_values in itertools.product(*param_values):
                combo = dict(zip(param_names, combo_values))
                combinations.append(combo)

        # Test each combination
        results = []
        best_metric_value = float("-inf")
        best_params = None

        for i, combo in enumerate(combinations):
            log.info(
                "testing_combination %d/%d params=%s", i + 1, len(combinations), combo
            )

            try:
                # Merge with base params
                strategy_params = self.base_strategy_params.copy()
                strategy_params.update(combo)

                # Run backtest
                engine = BacktestEngine(
                    start_date=self.start_date,
                    end_date=self.end_date,
                    initial_capital=self.initial_capital,
                    strategy_params=strategy_params,
                )

                result = engine.run_backtest()
                metrics = result["metrics"]

                metric_value = metrics.get(optimization_metric, 0)

                results.append(
                    {
                        "params": combo,
                        "metric_value": metric_value,
                        "total_return_pct": metrics.get("total_return_pct", 0),
                        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                        "win_rate": metrics.get("win_rate", 0),
                        "total_trades": metrics.get("total_trades", 0),
                    }
                )

                # Track best
                if metric_value > best_metric_value:
                    best_metric_value = metric_value
                    best_params = combo

            except Exception as e:
                log.warning("combination_failed params=%s error=%s", combo, str(e))
                continue

        optimization_results = {
            "optimal_params": best_params,
            "optimal_metric_value": float(best_metric_value),
            "all_results": results,
        }

        log.info(
            "multi_parameter_optimization_complete optimal_params=%s optimal_value=%.2f",
            best_params,
            best_metric_value,
        )

        return optimization_results
