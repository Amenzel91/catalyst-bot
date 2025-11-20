"""
ML module for catalyst-bot: RL-based paper trading and sentiment analysis.

This module provides:
  - CatalystTradingEnv: Gymnasium environment for RL training
  - AgentTrainer: Training pipeline for PPO/SAC/A2C agents
  - EnsembleAgent: Sharpe-weighted ensemble of multiple agents
  - StrategyEvaluator: Backtesting and performance analysis

For sentiment analysis:
  - BatchSentimentScorer: GPU-accelerated sentiment analysis
  - load_sentiment_model: Model switcher for FinBERT/DistilBERT

Example usage:
    >>> from catalyst_bot.ml import CatalystTradingEnv, AgentTrainer
    >>> env = CatalystTradingEnv(data_df)
    >>> trainer = AgentTrainer(data_df)
    >>> trainer.train_ppo(total_timesteps=100000)
"""

# RL Training Components (NEW)
try:
    from .trading_env import CatalystTradingEnv
    from .train_agent import AgentTrainer
    from .ensemble import EnsembleAgent
    from .evaluate import StrategyEvaluator, PerformanceMetrics

    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False
    # These may fail if stable-baselines3 or gymnasium not installed

# Sentiment Analysis Components (EXISTING)
try:
    from .batch_sentiment import BatchSentimentScorer
    from .model_switcher import load_sentiment_model

    SENTIMENT_AVAILABLE = True
except ImportError:
    SENTIMENT_AVAILABLE = False

__all__ = [
    # RL Training
    "CatalystTradingEnv",
    "AgentTrainer",
    "EnsembleAgent",
    "StrategyEvaluator",
    "PerformanceMetrics",
    # Sentiment Analysis
    "BatchSentimentScorer",
    "load_sentiment_model",
    # Flags
    "RL_AVAILABLE",
    "SENTIMENT_AVAILABLE",
]
