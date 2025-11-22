"""
EnsembleAgent: Combine multiple RL agents for robust predictions.

This module implements ensemble methods for combining multiple trained RL agents
to produce more robust trading signals. The ensemble uses Sharpe-ratio weighted
averaging to combine predictions from multiple models.

Key Features:
  - Load and manage multiple trained agents (PPO, SAC, A2C)
  - Sharpe-weighted averaging (agents with better risk-adjusted returns get more weight)
  - Dynamic weight adjustment based on recent performance
  - Performance tracking per agent
  - Fallback to best single agent if ensemble underperforms

Example usage:
    >>> from catalyst_bot.ml.ensemble import EnsembleAgent
    >>> ensemble = EnsembleAgent()
    >>> ensemble.add_agent("checkpoints/ppo_agent.zip", "ppo", weight=1.0)
    >>> ensemble.add_agent("checkpoints/sac_agent.zip", "sac", weight=1.0)
    >>> action = ensemble.predict(observation)
    >>> ensemble.update_performance(reward)

Architecture:
    - Maintains a pool of trained agents with individual weights
    - Computes weighted average of actions from all agents
    - Tracks performance metrics (Sharpe ratio) for each agent
    - Periodically reweights agents based on recent performance
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from stable_baselines3 import A2C, PPO, SAC

from ..config import get_settings
from ..logging_utils import get_logger

log = get_logger(__name__)


class EnsembleAgent:
    """
    Ensemble of multiple RL agents with Sharpe-weighted predictions.

    This class manages a portfolio of trained RL agents and combines their
    predictions using Sharpe-ratio weighted averaging. Agents with better
    risk-adjusted performance receive higher weights.

    Parameters
    ----------
    reweight_frequency : int, optional
        How often to reweight agents based on performance (in steps) (default: 1000)
    min_weight : float, optional
        Minimum weight for any agent (prevents complete exclusion) (default: 0.1)
    lookback_window : int, optional
        Window for calculating Sharpe ratios (default: 100)
    """

    def __init__(
        self,
        reweight_frequency: int = 1000,
        min_weight: float = 0.1,
        lookback_window: int = 100,
    ):
        self.agents: List[Dict[str, Any]] = []  # List of agent dicts
        self.reweight_frequency = reweight_frequency
        self.min_weight = min_weight
        self.lookback_window = lookback_window

        # Performance tracking
        self.step_count = 0
        self.agent_returns: List[List[float]] = []  # Returns per agent
        self.ensemble_returns: List[float] = []  # Overall ensemble returns

        log.info(
            "ensemble_agent_initialized reweight_freq=%d min_weight=%.2f "
            "lookback=%d",
            reweight_frequency,
            min_weight,
            lookback_window,
        )

    def add_agent(
        self,
        model_path: str,
        model_type: str,
        weight: float = 1.0,
        name: Optional[str] = None,
    ) -> None:
        """
        Add a trained agent to the ensemble.

        Parameters
        ----------
        model_path : str
            Path to saved model file
        model_type : str
            Model type ("ppo", "sac", "a2c")
        weight : float, optional
            Initial weight for this agent (default: 1.0)
        name : str, optional
            Human-readable name for agent (default: model filename)

        Raises
        ------
        ValueError
            If model_type is not supported or model fails to load
        """
        # TODO: Implement robust model loading with error handling

        # Load model
        try:
            if model_type.lower() == "ppo":
                model = PPO.load(model_path)
            elif model_type.lower() == "sac":
                model = SAC.load(model_path)
            elif model_type.lower() == "a2c":
                model = A2C.load(model_path)
            else:
                raise ValueError(f"Unsupported model type: {model_type}")
        except Exception as e:
            log.error(
                "ensemble_agent_load_failed path=%s type=%s error=%s",
                model_path,
                model_type,
                str(e),
            )
            raise

        # Default name is filename
        if name is None:
            name = Path(model_path).stem

        # Add to ensemble
        agent_dict = {
            "model": model,
            "type": model_type,
            "path": model_path,
            "name": name,
            "weight": weight,
            "sharpe": 0.0,  # Will be computed from performance
        }

        self.agents.append(agent_dict)
        self.agent_returns.append([])  # Initialize returns tracking

        log.info(
            "ensemble_agent_added name=%s type=%s path=%s weight=%.2f total_agents=%d",
            name,
            model_type,
            model_path,
            weight,
            len(self.agents),
        )

    def predict(
        self,
        observation: np.ndarray,
        deterministic: bool = True,
    ) -> Tuple[np.ndarray, Optional[Dict[str, Any]]]:
        """
        Predict action using weighted ensemble of agents.

        The ensemble computes actions from all agents and combines them using
        Sharpe-weighted averaging. Agents with better recent performance
        contribute more to the final action.

        Parameters
        ----------
        observation : np.ndarray
            Current environment observation
        deterministic : bool, optional
            Whether to use deterministic actions (default: True)

        Returns
        -------
        action : np.ndarray
            Combined action from ensemble
        info : dict or None
            Additional information (individual agent actions, weights)
        """
        if not self.agents:
            raise ValueError("No agents in ensemble. Add agents first.")

        # TODO: Implement weighted prediction
        # Consider:
        #   - Handling agents that fail to predict
        #   - Logging individual agent predictions for analysis
        #   - Optional: Use voting or other aggregation methods

        actions = []
        weights = []
        agent_info = {}

        for i, agent_dict in enumerate(self.agents):
            model = agent_dict["model"]
            weight = agent_dict["weight"]

            try:
                # Get action from agent
                action, _ = model.predict(observation, deterministic=deterministic)
                actions.append(action)
                weights.append(weight)

                # Store for logging
                agent_info[f"agent_{i}_{agent_dict['name']}"] = {
                    "action": float(action[0]),
                    "weight": weight,
                    "sharpe": agent_dict["sharpe"],
                }

            except Exception as e:
                log.warning(
                    "ensemble_prediction_failed agent=%s error=%s",
                    agent_dict["name"],
                    str(e),
                )
                # Skip failed agent
                continue

        if not actions:
            raise RuntimeError("All agents failed to predict")

        # Normalize weights
        weights = np.array(weights)
        weights = weights / weights.sum()

        # Compute weighted average action
        actions = np.array(actions)
        ensemble_action = np.average(actions, axis=0, weights=weights)

        info = {
            "agent_predictions": agent_info,
            "ensemble_action": float(ensemble_action[0]),
            "n_agents": len(actions),
        }

        log.debug(
            "ensemble_predict action=%.3f n_agents=%d weights=%s",
            ensemble_action[0],
            len(actions),
            ",".join([f"{w:.3f}" for w in weights]),
        )

        return ensemble_action, info

    def update_performance(
        self,
        observation: np.ndarray,
        action: np.ndarray,
        reward: float,
    ) -> None:
        """
        Update performance tracking for all agents.

        This method tracks how each agent would have performed (even if the
        ensemble didn't use their exact action). Used for reweighting agents.

        Parameters
        ----------
        observation : np.ndarray
            Previous observation
        action : np.ndarray
            Action taken by ensemble
        reward : float
            Reward received
        """
        # TODO: Implement sophisticated performance tracking
        # Consider:
        #   - Counterfactual returns (what would each agent have earned?)
        #   - Rolling Sharpe ratio calculation
        #   - Handling edge cases (no recent returns)

        self.step_count += 1
        self.ensemble_returns.append(reward)

        # Get what each agent would have done
        for i, agent_dict in enumerate(self.agents):
            model = agent_dict["model"]

            try:
                # Get agent's action
                agent_action, _ = model.predict(observation, deterministic=True)

                # Approximate agent's reward (simple heuristic)
                # TODO: Use more sophisticated counterfactual estimation
                # For now, scale ensemble reward by action similarity
                action_similarity = 1.0 - abs(agent_action[0] - action[0])
                agent_reward = reward * action_similarity

                self.agent_returns[i].append(agent_reward)

            except Exception as e:
                log.debug(
                    "performance_update_failed agent=%s error=%s",
                    agent_dict["name"],
                    str(e),
                )
                continue

        # Periodically reweight agents
        if self.step_count % self.reweight_frequency == 0:
            self._reweight_agents()

    def _reweight_agents(self) -> None:
        """
        Reweight agents based on recent performance (Sharpe ratios).

        Agents with higher Sharpe ratios receive higher weights. This implements
        dynamic weight adjustment based on rolling performance.
        """
        # TODO: Implement Sharpe-based reweighting
        # Formula: weight_i = max(min_weight, sharpe_i / sum(sharpe_all))

        log.info("ensemble_reweighting agents=%d step=%d", len(self.agents), self.step_count)

        sharpe_ratios = []

        for i, agent_dict in enumerate(self.agents):
            # Get recent returns
            recent_returns = self.agent_returns[i][-self.lookback_window :]

            if len(recent_returns) < 10:
                # Not enough data, use current weight
                sharpe_ratios.append(1.0)
                continue

            # Calculate Sharpe ratio
            mean_return = np.mean(recent_returns)
            std_return = np.std(recent_returns) + 1e-8
            sharpe = mean_return / std_return

            # Store and use for weighting
            agent_dict["sharpe"] = sharpe
            sharpe_ratios.append(max(0.0, sharpe))  # Clip negative Sharpe to 0

        # Convert to weights (softmax for stability)
        sharpe_array = np.array(sharpe_ratios)

        # Handle all-zero case
        if sharpe_array.sum() == 0:
            weights = np.ones(len(self.agents)) / len(self.agents)
        else:
            # Apply softmax with temperature for smoother weights
            temperature = 0.5
            exp_sharpe = np.exp(sharpe_array / temperature)
            weights = exp_sharpe / exp_sharpe.sum()

        # Apply minimum weight constraint
        weights = np.maximum(weights, self.min_weight)
        weights = weights / weights.sum()  # Renormalize

        # Update agent weights
        for i, agent_dict in enumerate(self.agents):
            old_weight = agent_dict["weight"]
            new_weight = weights[i]
            agent_dict["weight"] = new_weight

            log.info(
                "ensemble_agent_reweighted name=%s sharpe=%.4f "
                "old_weight=%.3f new_weight=%.3f",
                agent_dict["name"],
                agent_dict["sharpe"],
                old_weight,
                new_weight,
            )

    def get_agent_stats(self) -> List[Dict[str, Any]]:
        """
        Get performance statistics for all agents.

        Returns
        -------
        list of dict
            Stats for each agent containing:
                - name: Agent name
                - type: Model type
                - weight: Current weight
                - sharpe: Recent Sharpe ratio
                - mean_return: Mean return
                - std_return: Return volatility
        """
        stats = []

        for i, agent_dict in enumerate(self.agents):
            recent_returns = self.agent_returns[i][-self.lookback_window :]

            if len(recent_returns) >= 2:
                mean_return = np.mean(recent_returns)
                std_return = np.std(recent_returns)
            else:
                mean_return = 0.0
                std_return = 0.0

            stats.append(
                {
                    "name": agent_dict["name"],
                    "type": agent_dict["type"],
                    "weight": agent_dict["weight"],
                    "sharpe": agent_dict["sharpe"],
                    "mean_return": mean_return,
                    "std_return": std_return,
                    "n_predictions": len(self.agent_returns[i]),
                }
            )

        return stats

    def save_weights(self, path: str) -> None:
        """
        Save current agent weights to JSON file.

        Parameters
        ----------
        path : str
            Output path for weights JSON
        """
        weights_data = {
            "step_count": self.step_count,
            "agents": [
                {
                    "name": agent["name"],
                    "type": agent["type"],
                    "path": agent["path"],
                    "weight": agent["weight"],
                    "sharpe": agent["sharpe"],
                }
                for agent in self.agents
            ],
        }

        with open(path, "w") as f:
            json.dump(weights_data, f, indent=2)

        log.info("ensemble_weights_saved path=%s agents=%d", path, len(self.agents))

    def load_weights(self, path: str) -> None:
        """
        Load agent weights from JSON file.

        Parameters
        ----------
        path : str
            Path to weights JSON
        """
        with open(path, "r") as f:
            weights_data = json.load(f)

        # Update weights for matching agents
        for agent_data in weights_data["agents"]:
            # Find matching agent by name or path
            for agent in self.agents:
                if agent["name"] == agent_data["name"] or agent["path"] == agent_data["path"]:
                    agent["weight"] = agent_data["weight"]
                    agent["sharpe"] = agent_data.get("sharpe", 0.0)
                    log.info(
                        "ensemble_weight_loaded agent=%s weight=%.3f sharpe=%.3f",
                        agent["name"],
                        agent["weight"],
                        agent["sharpe"],
                    )
                    break

        log.info("ensemble_weights_loaded path=%s", path)

    def reset(self) -> None:
        """Reset performance tracking (for new episode)."""
        self.step_count = 0
        self.agent_returns = [[] for _ in self.agents]
        self.ensemble_returns = []
        log.debug("ensemble_reset agents=%d", len(self.agents))


# Example usage
if __name__ == "__main__":
    # TODO: Add command-line interface for ensemble evaluation
    # Example:
    #   python ensemble.py --agents ppo:checkpoints/ppo.zip sac:checkpoints/sac.zip

    import argparse

    parser = argparse.ArgumentParser(description="Ensemble RL agent evaluation")
    parser.add_argument(
        "--agents",
        nargs="+",
        required=True,
        help="Agents in format type:path (e.g., ppo:checkpoints/ppo.zip)",
    )
    parser.add_argument("--data", type=str, required=True, help="Test data CSV path")
    parser.add_argument(
        "--weights-out",
        type=str,
        default="ensemble_weights.json",
        help="Output path for weights",
    )

    args = parser.parse_args()

    # Create ensemble
    ensemble = EnsembleAgent()

    # Add agents
    for agent_spec in args.agents:
        model_type, model_path = agent_spec.split(":")
        ensemble.add_agent(model_path, model_type)

    # TODO: Evaluate ensemble on test data
    print(f"Ensemble created with {len(ensemble.agents)} agents")

    # Save weights
    ensemble.save_weights(args.weights_out)
    print(f"Weights saved to {args.weights_out}")
