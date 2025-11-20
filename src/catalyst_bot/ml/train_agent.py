"""
AgentTrainer: Training script for RL agents on catalyst trading.

This module provides a comprehensive training pipeline for reinforcement learning
agents (PPO, SAC, A2C) on catalyst trading data. Features include:
  - Data preparation and train/val/test splitting
  - Multi-algorithm support (PPO, SAC, A2C from stable-baselines3)
  - Hyperparameter optimization (Optuna)
  - Walk-forward validation for realistic backtesting
  - Model checkpointing and loading
  - TensorBoard logging

Example usage:
    >>> from catalyst_bot.ml.train_agent import AgentTrainer
    >>> trainer = AgentTrainer(data_df)
    >>> trainer.train_ppo(total_timesteps=100000)
    >>> trainer.save_model("checkpoints/ppo_agent.zip")
    >>>
    >>> # Walk-forward validation
    >>> results = trainer.walk_forward_validate(n_splits=5)

Architecture:
    - Uses stable-baselines3 for RL algorithms
    - Integrates with CatalystTradingEnv for environment
    - Optuna for hyperparameter search
    - TensorBoard for training visualization
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from stable_baselines3 import A2C, PPO, SAC
from stable_baselines3.common.callbacks import (
    CallbackList,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from ..config import get_settings
from ..logging_utils import get_logger
from .trading_env import CatalystTradingEnv

log = get_logger(__name__)

# Import Optuna for hyperparameter optimization
try:
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler

    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    log.warning("optuna_unavailable hint=install_with_pip_install_optuna")


class AgentTrainer:
    """
    Comprehensive training pipeline for RL agents on catalyst trading.

    This class handles:
      1. Data preparation and splitting (train/val/test)
      2. Environment setup (vectorized, normalized)
      3. Model training (PPO, SAC, A2C)
      4. Hyperparameter optimization (Optuna)
      5. Walk-forward validation
      6. Model persistence (save/load)

    Parameters
    ----------
    data_df : pd.DataFrame
        Historical catalyst data with required columns (see CatalystTradingEnv)
    train_ratio : float, optional
        Fraction of data for training (default: 0.7)
    val_ratio : float, optional
        Fraction of data for validation (default: 0.15)
    test_ratio : float, optional
        Fraction of data for testing (default: 0.15)
    initial_capital : float, optional
        Starting capital for paper trading (default: 10000.0)
    log_dir : str, optional
        Directory for TensorBoard logs (default: "logs/")
    checkpoint_dir : str, optional
        Directory for model checkpoints (default: "checkpoints/")
    """

    def __init__(
        self,
        data_df: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        initial_capital: float = 10000.0,
        log_dir: str = "logs/",
        checkpoint_dir: str = "checkpoints/",
    ):
        self.data_df = data_df.copy()
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.initial_capital = initial_capital
        self.log_dir = Path(log_dir)
        self.checkpoint_dir = Path(checkpoint_dir)

        # Create directories
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Data splits
        self.train_df: Optional[pd.DataFrame] = None
        self.val_df: Optional[pd.DataFrame] = None
        self.test_df: Optional[pd.DataFrame] = None

        # Models
        self.model: Optional[Any] = None  # Current trained model
        self.model_type: Optional[str] = None  # "ppo", "sac", "a2c"

        # Prepare data splits
        self._prepare_data_splits()

        log.info(
            "agent_trainer_initialized total_rows=%d train_rows=%d "
            "val_rows=%d test_rows=%d",
            len(self.data_df),
            len(self.train_df) if self.train_df is not None else 0,
            len(self.val_df) if self.val_df is not None else 0,
            len(self.test_df) if self.test_df is not None else 0,
        )

    def _prepare_data_splits(self) -> None:
        """
        Split data into train/val/test sets using temporal ordering.

        Notes
        -----
        Temporal splitting is critical for time-series data to prevent lookahead
        bias. We use chronological splits rather than random sampling.
        """
        # TODO: Implement sophisticated splitting logic
        # Consider:
        #   - Stratification by ticker
        #   - Handling gaps in time series
        #   - Ensuring sufficient samples per split

        # Ensure data is sorted by timestamp
        df = self.data_df.sort_values("ts_utc").reset_index(drop=True)

        # Calculate split indices
        n = len(df)
        train_end = int(n * self.train_ratio)
        val_end = int(n * (self.train_ratio + self.val_ratio))

        # Split
        self.train_df = df.iloc[:train_end].copy()
        self.val_df = df.iloc[train_end:val_end].copy()
        self.test_df = df.iloc[val_end:].copy()

        log.info(
            "data_splits_prepared train=%d val=%d test=%d",
            len(self.train_df),
            len(self.val_df),
            len(self.test_df),
        )

    def _create_env(
        self,
        data_df: pd.DataFrame,
        normalize: bool = True,
        n_envs: int = 1,
    ) -> Any:
        """
        Create vectorized and normalized environment.

        Parameters
        ----------
        data_df : pd.DataFrame
            Data for environment
        normalize : bool, optional
            Whether to normalize observations (default: True)
        n_envs : int, optional
            Number of parallel environments (default: 1)

        Returns
        -------
        VecEnv
            Vectorized (and optionally normalized) environment
        """
        # TODO: Implement robust environment creation
        # Consider:
        #   - VecNormalize for observation/reward normalization
        #   - Monitor wrapper for episode statistics
        #   - Parallel environments (SubprocVecEnv) for faster training

        def make_env():
            env = CatalystTradingEnv(
                data_df=data_df,
                initial_capital=self.initial_capital,
            )
            env = Monitor(env)  # Wrap with Monitor for episode stats
            return env

        # Create vectorized environment
        if n_envs > 1:
            # TODO: Use SubprocVecEnv for parallel training
            env = DummyVecEnv([make_env for _ in range(n_envs)])
        else:
            env = DummyVecEnv([make_env])

        # Normalize observations and rewards
        if normalize:
            env = VecNormalize(
                env,
                norm_obs=True,
                norm_reward=True,
                clip_obs=10.0,
                clip_reward=10.0,
            )

        return env

    def train_ppo(
        self,
        total_timesteps: int = 100000,
        learning_rate: float = 3e-4,
        n_steps: int = 2048,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        ent_coef: float = 0.0,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        use_sde: bool = False,
        tensorboard_log: Optional[str] = None,
    ) -> PPO:
        """
        Train PPO (Proximal Policy Optimization) agent.

        PPO is a policy gradient method that is sample-efficient and stable.
        It's well-suited for continuous action spaces like position sizing.

        Parameters
        ----------
        total_timesteps : int, optional
            Total training timesteps (default: 100000)
        learning_rate : float, optional
            Learning rate (default: 3e-4)
        n_steps : int, optional
            Number of steps per environment per update (default: 2048)
        batch_size : int, optional
            Minibatch size for SGD (default: 64)
        n_epochs : int, optional
            Number of epochs for policy update (default: 10)
        gamma : float, optional
            Discount factor (default: 0.99)
        gae_lambda : float, optional
            GAE lambda for advantage estimation (default: 0.95)
        clip_range : float, optional
            Clipping parameter for policy updates (default: 0.2)
        ent_coef : float, optional
            Entropy coefficient for exploration (default: 0.0)
        vf_coef : float, optional
            Value function coefficient (default: 0.5)
        max_grad_norm : float, optional
            Max gradient norm for clipping (default: 0.5)
        use_sde : bool, optional
            Whether to use State-Dependent Exploration (default: False)
        tensorboard_log : str, optional
            TensorBoard log directory (default: None = self.log_dir)

        Returns
        -------
        PPO
            Trained PPO model
        """
        # TODO: Implement comprehensive PPO training
        # Consider:
        #   - Callbacks (checkpoint, eval, early stopping)
        #   - Hyperparameter logging
        #   - Multi-environment training
        #   - Learning rate scheduling

        log.info(
            "training_ppo_start total_timesteps=%d learning_rate=%.5f "
            "batch_size=%d n_epochs=%d",
            total_timesteps,
            learning_rate,
            batch_size,
            n_epochs,
        )

        # Create training environment
        train_env = self._create_env(self.train_df, normalize=True, n_envs=4)

        # Create validation environment for eval callback
        val_env = self._create_env(self.val_df, normalize=True, n_envs=1)

        # Setup callbacks
        checkpoint_callback = CheckpointCallback(
            save_freq=10000,
            save_path=str(self.checkpoint_dir / "ppo"),
            name_prefix="ppo_model",
        )

        eval_callback = EvalCallback(
            val_env,
            best_model_save_path=str(self.checkpoint_dir / "ppo_best"),
            log_path=str(self.log_dir / "ppo_eval"),
            eval_freq=5000,
            deterministic=True,
            render=False,
        )

        callbacks = CallbackList([checkpoint_callback, eval_callback])

        # Create PPO model
        self.model = PPO(
            policy="MlpPolicy",
            env=train_env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            max_grad_norm=max_grad_norm,
            use_sde=use_sde,
            tensorboard_log=tensorboard_log or str(self.log_dir / "ppo"),
            verbose=1,
        )

        self.model_type = "ppo"

        # Train
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            tb_log_name="ppo_run",
        )

        log.info("training_ppo_complete timesteps=%d", total_timesteps)

        return self.model

    def train_sac(
        self,
        total_timesteps: int = 100000,
        learning_rate: float = 3e-4,
        buffer_size: int = 1000000,
        learning_starts: int = 100,
        batch_size: int = 256,
        tau: float = 0.005,
        gamma: float = 0.99,
        train_freq: int = 1,
        gradient_steps: int = 1,
        ent_coef: str = "auto",
        target_entropy: str = "auto",
        use_sde: bool = False,
        tensorboard_log: Optional[str] = None,
    ) -> SAC:
        """
        Train SAC (Soft Actor-Critic) agent.

        SAC is an off-policy actor-critic algorithm that maximizes both expected
        return and entropy. It's very sample-efficient and works well for
        continuous control tasks.

        Parameters
        ----------
        total_timesteps : int, optional
            Total training timesteps (default: 100000)
        learning_rate : float, optional
            Learning rate (default: 3e-4)
        buffer_size : int, optional
            Replay buffer size (default: 1000000)
        learning_starts : int, optional
            Timesteps before learning starts (default: 100)
        batch_size : int, optional
            Minibatch size for SGD (default: 256)
        tau : float, optional
            Soft update coefficient for target networks (default: 0.005)
        gamma : float, optional
            Discount factor (default: 0.99)
        train_freq : int, optional
            Update frequency (default: 1)
        gradient_steps : int, optional
            Gradient steps per update (default: 1)
        ent_coef : str or float, optional
            Entropy regularization coefficient (default: "auto")
        target_entropy : str or float, optional
            Target entropy for automatic tuning (default: "auto")
        use_sde : bool, optional
            Whether to use State-Dependent Exploration (default: False)
        tensorboard_log : str, optional
            TensorBoard log directory (default: None = self.log_dir)

        Returns
        -------
        SAC
            Trained SAC model
        """
        # TODO: Implement SAC training with replay buffer
        # SAC is off-policy and uses a replay buffer for sample efficiency

        log.info(
            "training_sac_start total_timesteps=%d learning_rate=%.5f "
            "buffer_size=%d batch_size=%d",
            total_timesteps,
            learning_rate,
            buffer_size,
            batch_size,
        )

        # Create training environment
        train_env = self._create_env(self.train_df, normalize=True, n_envs=1)

        # Create validation environment
        val_env = self._create_env(self.val_df, normalize=True, n_envs=1)

        # Setup callbacks
        checkpoint_callback = CheckpointCallback(
            save_freq=10000,
            save_path=str(self.checkpoint_dir / "sac"),
            name_prefix="sac_model",
        )

        eval_callback = EvalCallback(
            val_env,
            best_model_save_path=str(self.checkpoint_dir / "sac_best"),
            log_path=str(self.log_dir / "sac_eval"),
            eval_freq=5000,
            deterministic=True,
            render=False,
        )

        callbacks = CallbackList([checkpoint_callback, eval_callback])

        # Create SAC model
        self.model = SAC(
            policy="MlpPolicy",
            env=train_env,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            learning_starts=learning_starts,
            batch_size=batch_size,
            tau=tau,
            gamma=gamma,
            train_freq=train_freq,
            gradient_steps=gradient_steps,
            ent_coef=ent_coef,
            target_entropy=target_entropy,
            use_sde=use_sde,
            tensorboard_log=tensorboard_log or str(self.log_dir / "sac"),
            verbose=1,
        )

        self.model_type = "sac"

        # Train
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            tb_log_name="sac_run",
        )

        log.info("training_sac_complete timesteps=%d", total_timesteps)

        return self.model

    def train_a2c(
        self,
        total_timesteps: int = 100000,
        learning_rate: float = 7e-4,
        n_steps: int = 5,
        gamma: float = 0.99,
        gae_lambda: float = 1.0,
        ent_coef: float = 0.0,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        use_rms_prop: bool = True,
        use_sde: bool = False,
        tensorboard_log: Optional[str] = None,
    ) -> A2C:
        """
        Train A2C (Advantage Actor-Critic) agent.

        A2C is a synchronous version of A3C that's more stable and easier to
        tune. It's a good baseline algorithm for continuous control.

        Parameters
        ----------
        total_timesteps : int, optional
            Total training timesteps (default: 100000)
        learning_rate : float, optional
            Learning rate (default: 7e-4)
        n_steps : int, optional
            Number of steps per environment per update (default: 5)
        gamma : float, optional
            Discount factor (default: 0.99)
        gae_lambda : float, optional
            GAE lambda for advantage estimation (default: 1.0)
        ent_coef : float, optional
            Entropy coefficient for exploration (default: 0.0)
        vf_coef : float, optional
            Value function coefficient (default: 0.5)
        max_grad_norm : float, optional
            Max gradient norm for clipping (default: 0.5)
        use_rms_prop : bool, optional
            Whether to use RMSprop optimizer (default: True)
        use_sde : bool, optional
            Whether to use State-Dependent Exploration (default: False)
        tensorboard_log : str, optional
            TensorBoard log directory (default: None = self.log_dir)

        Returns
        -------
        A2C
            Trained A2C model
        """
        # TODO: Implement A2C training

        log.info(
            "training_a2c_start total_timesteps=%d learning_rate=%.5f n_steps=%d",
            total_timesteps,
            learning_rate,
            n_steps,
        )

        # Create training environment
        train_env = self._create_env(self.train_df, normalize=True, n_envs=4)

        # Create validation environment
        val_env = self._create_env(self.val_df, normalize=True, n_envs=1)

        # Setup callbacks
        checkpoint_callback = CheckpointCallback(
            save_freq=10000,
            save_path=str(self.checkpoint_dir / "a2c"),
            name_prefix="a2c_model",
        )

        eval_callback = EvalCallback(
            val_env,
            best_model_save_path=str(self.checkpoint_dir / "a2c_best"),
            log_path=str(self.log_dir / "a2c_eval"),
            eval_freq=5000,
            deterministic=True,
            render=False,
        )

        callbacks = CallbackList([checkpoint_callback, eval_callback])

        # Create A2C model
        self.model = A2C(
            policy="MlpPolicy",
            env=train_env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            gamma=gamma,
            gae_lambda=gae_lambda,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            max_grad_norm=max_grad_norm,
            use_rms_prop=use_rms_prop,
            use_sde=use_sde,
            tensorboard_log=tensorboard_log or str(self.log_dir / "a2c"),
            verbose=1,
        )

        self.model_type = "a2c"

        # Train
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks,
            tb_log_name="a2c_run",
        )

        log.info("training_a2c_complete timesteps=%d", total_timesteps)

        return self.model

    def optimize_hyperparameters(
        self,
        algorithm: str = "ppo",
        n_trials: int = 50,
        n_timesteps: int = 50000,
        n_eval_episodes: int = 10,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Hyperparameter optimization using Optuna.

        This method uses Bayesian optimization (TPE sampler) to find optimal
        hyperparameters for the specified algorithm.

        Parameters
        ----------
        algorithm : str, optional
            Algorithm to optimize ("ppo", "sac", "a2c") (default: "ppo")
        n_trials : int, optional
            Number of optimization trials (default: 50)
        n_timesteps : int, optional
            Timesteps per trial (default: 50000)
        n_eval_episodes : int, optional
            Episodes for evaluation (default: 10)
        timeout : int, optional
            Timeout in seconds (default: None = no timeout)

        Returns
        -------
        dict
            Best hyperparameters found

        Raises
        ------
        ImportError
            If Optuna is not installed
        """
        if not OPTUNA_AVAILABLE:
            raise ImportError(
                "Optuna not available. Install with: pip install optuna"
            )

        # TODO: Implement comprehensive hyperparameter optimization
        # Consider:
        #   - Different search spaces per algorithm
        #   - Pruning for early stopping of bad trials
        #   - Parallel trials for faster optimization
        #   - Saving study results to database

        log.info(
            "hyperparameter_optimization_start algorithm=%s n_trials=%d "
            "n_timesteps=%d",
            algorithm,
            n_trials,
            n_timesteps,
        )

        def objective(trial: optuna.Trial) -> float:
            """Optuna objective function."""
            # Sample hyperparameters
            if algorithm == "ppo":
                params = {
                    "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True),
                    "n_steps": trial.suggest_int("n_steps", 512, 4096, step=512),
                    "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128, 256]),
                    "n_epochs": trial.suggest_int("n_epochs", 5, 20),
                    "gamma": trial.suggest_float("gamma", 0.9, 0.9999),
                    "gae_lambda": trial.suggest_float("gae_lambda", 0.9, 0.99),
                    "clip_range": trial.suggest_float("clip_range", 0.1, 0.3),
                    "ent_coef": trial.suggest_float("ent_coef", 0.0, 0.1),
                }

                # Create environment
                env = self._create_env(self.train_df, normalize=True, n_envs=1)

                # Create model
                model = PPO(
                    policy="MlpPolicy",
                    env=env,
                    **params,
                    verbose=0,
                )

            elif algorithm == "sac":
                params = {
                    "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True),
                    "batch_size": trial.suggest_categorical("batch_size", [64, 128, 256, 512]),
                    "tau": trial.suggest_float("tau", 0.001, 0.02),
                    "gamma": trial.suggest_float("gamma", 0.9, 0.9999),
                    "train_freq": trial.suggest_int("train_freq", 1, 10),
                    "gradient_steps": trial.suggest_int("gradient_steps", 1, 10),
                }

                env = self._create_env(self.train_df, normalize=True, n_envs=1)
                model = SAC(policy="MlpPolicy", env=env, **params, verbose=0)

            elif algorithm == "a2c":
                params = {
                    "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True),
                    "n_steps": trial.suggest_int("n_steps", 5, 20),
                    "gamma": trial.suggest_float("gamma", 0.9, 0.9999),
                    "gae_lambda": trial.suggest_float("gae_lambda", 0.9, 1.0),
                    "ent_coef": trial.suggest_float("ent_coef", 0.0, 0.1),
                }

                env = self._create_env(self.train_df, normalize=True, n_envs=4)
                model = A2C(policy="MlpPolicy", env=env, **params, verbose=0)

            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")

            # Train
            model.learn(total_timesteps=n_timesteps)

            # Evaluate
            eval_env = self._create_env(self.val_df, normalize=True, n_envs=1)
            mean_reward, std_reward = evaluate_policy(
                model, eval_env, n_eval_episodes=n_eval_episodes
            )

            return mean_reward

        # Create Optuna study
        study = optuna.create_study(
            direction="maximize",
            sampler=TPESampler(n_startup_trials=10),
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10),
        )

        # Optimize
        study.optimize(objective, n_trials=n_trials, timeout=timeout, n_jobs=1)

        best_params = study.best_params
        best_value = study.best_value

        log.info(
            "hyperparameter_optimization_complete algorithm=%s best_value=%.4f "
            "best_params=%s",
            algorithm,
            best_value,
            json.dumps(best_params, indent=2),
        )

        return best_params

    def walk_forward_validate(
        self,
        n_splits: int = 5,
        algorithm: str = "ppo",
        timesteps_per_split: int = 50000,
    ) -> List[Dict[str, Any]]:
        """
        Walk-forward validation for realistic out-of-sample testing.

        Walk-forward validation mimics real-world trading by training on
        expanding windows and testing on subsequent unseen data. This is
        critical for preventing overfitting and measuring generalization.

        Process:
            1. Split data into n_splits temporal windows
            2. For each window:
                a. Train on all data up to window start
                b. Test on window data
                c. Record performance metrics
            3. Aggregate results across all windows

        Parameters
        ----------
        n_splits : int, optional
            Number of walk-forward splits (default: 5)
        algorithm : str, optional
            Algorithm to use ("ppo", "sac", "a2c") (default: "ppo")
        timesteps_per_split : int, optional
            Training timesteps per split (default: 50000)

        Returns
        -------
        list of dict
            Results for each split containing:
                - split_idx: Split index
                - train_end: Training end date
                - test_start: Testing start date
                - test_end: Testing end date
                - mean_reward: Mean reward during testing
                - total_return: Total return during testing
                - sharpe_ratio: Sharpe ratio during testing
        """
        # TODO: Implement walk-forward validation
        # This is critical for realistic performance estimation

        log.info(
            "walk_forward_validation_start n_splits=%d algorithm=%s "
            "timesteps_per_split=%d",
            n_splits,
            algorithm,
            timesteps_per_split,
        )

        results = []

        # Calculate split sizes
        n = len(self.data_df)
        test_size = n // (n_splits + 1)

        for i in range(n_splits):
            # Define train/test split for this iteration
            train_end_idx = test_size * (i + 1)
            test_start_idx = train_end_idx
            test_end_idx = min(train_end_idx + test_size, n)

            train_data = self.data_df.iloc[:train_end_idx].copy()
            test_data = self.data_df.iloc[test_start_idx:test_end_idx].copy()

            log.info(
                "walk_forward_split split=%d train_rows=%d test_rows=%d",
                i,
                len(train_data),
                len(test_data),
            )

            # Train model on expanding window
            train_env = self._create_env(train_data, normalize=True, n_envs=1)

            if algorithm == "ppo":
                model = PPO(policy="MlpPolicy", env=train_env, verbose=0)
            elif algorithm == "sac":
                model = SAC(policy="MlpPolicy", env=train_env, verbose=0)
            elif algorithm == "a2c":
                model = A2C(policy="MlpPolicy", env=train_env, verbose=0)
            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")

            model.learn(total_timesteps=timesteps_per_split)

            # Evaluate on test window
            test_env = self._create_env(test_data, normalize=True, n_envs=1)
            mean_reward, std_reward = evaluate_policy(
                model, test_env, n_eval_episodes=1, deterministic=True
            )

            # TODO: Extract additional metrics (total return, Sharpe, drawdown)
            results.append(
                {
                    "split_idx": i,
                    "train_end": train_data.iloc[-1]["ts_utc"],
                    "test_start": test_data.iloc[0]["ts_utc"],
                    "test_end": test_data.iloc[-1]["ts_utc"],
                    "mean_reward": mean_reward,
                    "std_reward": std_reward,
                    "train_rows": len(train_data),
                    "test_rows": len(test_data),
                }
            )

            log.info(
                "walk_forward_split_complete split=%d mean_reward=%.4f",
                i,
                mean_reward,
            )

        log.info("walk_forward_validation_complete n_splits=%d", n_splits)

        return results

    def save_model(self, path: str) -> None:
        """
        Save trained model to disk.

        Parameters
        ----------
        path : str
            Path to save model (e.g., "checkpoints/ppo_final.zip")
        """
        if self.model is None:
            raise ValueError("No model to save. Train a model first.")

        self.model.save(path)
        log.info("model_saved path=%s type=%s", path, self.model_type)

    def load_model(self, path: str, model_type: str) -> Any:
        """
        Load trained model from disk.

        Parameters
        ----------
        path : str
            Path to model file (e.g., "checkpoints/ppo_final.zip")
        model_type : str
            Model type ("ppo", "sac", "a2c")

        Returns
        -------
        model
            Loaded model
        """
        if model_type == "ppo":
            self.model = PPO.load(path)
        elif model_type == "sac":
            self.model = SAC.load(path)
        elif model_type == "a2c":
            self.model = A2C.load(path)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        self.model_type = model_type
        log.info("model_loaded path=%s type=%s", path, model_type)

        return self.model


# Example usage
if __name__ == "__main__":
    # TODO: Add command-line interface for training
    # Example:
    #   python train_agent.py --algorithm ppo --timesteps 100000 --data data/catalyst_history.csv

    import argparse

    parser = argparse.ArgumentParser(description="Train RL agent for catalyst trading")
    parser.add_argument("--data", type=str, required=True, help="Path to catalyst data CSV")
    parser.add_argument(
        "--algorithm",
        type=str,
        default="ppo",
        choices=["ppo", "sac", "a2c"],
        help="RL algorithm",
    )
    parser.add_argument(
        "--timesteps", type=int, default=100000, help="Total training timesteps"
    )
    parser.add_argument("--output", type=str, default="checkpoints/agent.zip", help="Output path")

    args = parser.parse_args()

    # Load data
    data_df = pd.read_csv(args.data)

    # Create trainer
    trainer = AgentTrainer(data_df)

    # Train
    if args.algorithm == "ppo":
        trainer.train_ppo(total_timesteps=args.timesteps)
    elif args.algorithm == "sac":
        trainer.train_sac(total_timesteps=args.timesteps)
    elif args.algorithm == "a2c":
        trainer.train_a2c(total_timesteps=args.timesteps)

    # Save
    trainer.save_model(args.output)

    print(f"Training complete. Model saved to {args.output}")
