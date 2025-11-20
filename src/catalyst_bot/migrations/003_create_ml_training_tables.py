"""
Migration 003: Create ML Training Database Tables

Creates tables for RL training runs, agent performance, hyperparameters, and ensemble weights.
Database: data/ml_training.db

Tables:
- training_runs: RL training session metadata
- agent_performance: Validation results for trained agents
- hyperparameters: Hyperparameter configurations tested
- ensemble_weights: Historical ensemble agent weights
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from catalyst_bot.storage import _ensure_dir, init_optimized_connection


ML_TRAINING_DB_PATH = "data/ml_training.db"


def create_training_runs_table(conn: sqlite3.Connection) -> None:
    """
    Create the training_runs table for RL training session tracking.

    Schema Design:
    - run_id: Unique training run identifier
    - algorithm: RL algorithm used (PPO, SAC, A2C, TD3, DQN)
    - model_name: Descriptive name for this model
    - start_time: When training started
    - end_time: When training completed
    - duration_seconds: Total training duration
    - total_timesteps: Number of environment steps trained
    - train_start_date: Start of training data period
    - train_end_date: End of training data period
    - val_start_date: Start of validation data period
    - val_end_date: End of validation data period
    - status: running, completed, failed, stopped
    - final_reward: Final episode reward
    - model_path: Path to saved model file
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS training_runs (
            run_id TEXT PRIMARY KEY,
            algorithm TEXT NOT NULL CHECK(
                algorithm IN ('PPO', 'SAC', 'A2C', 'TD3', 'DQN', 'DDPG', 'Ensemble')
            ),
            model_name TEXT NOT NULL,
            start_time INTEGER NOT NULL,
            end_time INTEGER,
            duration_seconds REAL,
            total_timesteps INTEGER NOT NULL,
            train_start_date TEXT NOT NULL,
            train_end_date TEXT NOT NULL,
            val_start_date TEXT,
            val_end_date TEXT,
            status TEXT NOT NULL DEFAULT 'running' CHECK(
                status IN ('running', 'completed', 'failed', 'stopped', 'aborted')
            ),
            final_reward REAL,
            best_reward REAL,
            final_loss REAL,
            convergence_achieved INTEGER DEFAULT 0,
            early_stopped INTEGER DEFAULT 0,
            model_path TEXT,
            tensorboard_log_dir TEXT,
            python_version TEXT,
            stable_baselines_version TEXT,
            random_seed INTEGER,
            device TEXT,
            num_envs INTEGER DEFAULT 1,
            notes TEXT,
            metadata TEXT,
            CONSTRAINT valid_duration CHECK(
                (end_time IS NULL) OR (duration_seconds >= 0)
            ),
            CONSTRAINT valid_timesteps CHECK(total_timesteps > 0)
        );
        """
    )

    print("✓ Created 'training_runs' table")


def create_agent_performance_table(conn: sqlite3.Connection) -> None:
    """
    Create the agent_performance table for validation results.

    Stores performance metrics from validation/testing of trained agents.
    Used to compare different agents and select best performers.

    Schema Design:
    - performance_id: Unique identifier
    - run_id: Reference to training run
    - evaluation_date: When this evaluation was performed
    - data_period_start: Start of evaluation data
    - data_period_end: End of evaluation data
    - sharpe_ratio: Risk-adjusted return
    - sortino_ratio: Downside risk-adjusted return
    - max_drawdown: Maximum drawdown percentage
    - total_return: Cumulative return percentage
    - win_rate: Percentage of profitable trades
    - profit_factor: Gross profit / Gross loss
    - total_trades: Number of trades executed
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_performance (
            performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            evaluation_time INTEGER NOT NULL,
            data_period_start TEXT NOT NULL,
            data_period_end TEXT NOT NULL,
            evaluation_type TEXT NOT NULL CHECK(
                evaluation_type IN ('train', 'validation', 'test', 'live_paper', 'backtest')
            ),
            -- Return metrics
            total_return REAL,
            total_return_pct REAL,
            annualized_return REAL,
            cumulative_reward REAL,
            avg_episode_reward REAL,
            -- Risk metrics
            sharpe_ratio REAL,
            sortino_ratio REAL,
            calmar_ratio REAL,
            max_drawdown REAL,
            max_drawdown_pct REAL,
            volatility REAL,
            downside_deviation REAL,
            -- Trade statistics
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            win_rate REAL,
            avg_win REAL,
            avg_loss REAL,
            profit_factor REAL,
            expectancy REAL,
            largest_win REAL,
            largest_loss REAL,
            avg_holding_period_hours REAL,
            -- Performance vs baseline
            buy_and_hold_return REAL,
            excess_return REAL,
            information_ratio REAL,
            -- Episode statistics
            num_episodes INTEGER,
            avg_episode_length REAL,
            successful_episodes INTEGER,
            -- Model confidence
            avg_action_entropy REAL,
            avg_value_estimate REAL,
            policy_stability REAL,
            -- Metadata
            notes TEXT,
            metadata TEXT,
            FOREIGN KEY (run_id) REFERENCES training_runs(run_id)
        );
        """
    )

    print("✓ Created 'agent_performance' table")


def create_hyperparameters_table(conn: sqlite3.Connection) -> None:
    """
    Create the hyperparameters table for tracking hyperparameter configurations.

    Stores all hyperparameters used in each training run.
    Essential for hyperparameter optimization and reproducibility.

    Schema Design:
    - hyperparameter_id: Unique identifier
    - run_id: Reference to training run
    - algorithm: Which algorithm these parameters are for
    - learning_rate: Learning rate for optimizer
    - batch_size: Batch size for training
    - n_steps: Number of steps per update (for on-policy algorithms)
    - gamma: Discount factor
    - Other algorithm-specific parameters stored in params_json
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hyperparameters (
            hyperparameter_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            algorithm TEXT NOT NULL,
            -- Common hyperparameters
            learning_rate REAL,
            batch_size INTEGER,
            n_steps INTEGER,
            gamma REAL,
            -- Policy network architecture
            policy_type TEXT,
            net_arch TEXT,
            activation_fn TEXT,
            -- Training parameters
            n_epochs INTEGER,
            buffer_size INTEGER,
            learning_starts INTEGER,
            tau REAL,
            gradient_steps INTEGER,
            -- Exploration parameters
            ent_coef REAL,
            vf_coef REAL,
            max_grad_norm REAL,
            target_kl REAL,
            -- Environment parameters
            normalize_observations INTEGER DEFAULT 0,
            normalize_rewards INTEGER DEFAULT 0,
            clip_range REAL,
            clip_range_vf REAL,
            -- Optimizer parameters
            optimizer TEXT,
            epsilon REAL,
            weight_decay REAL,
            -- Custom reward function parameters
            reward_function TEXT,
            reward_scaling REAL DEFAULT 1.0,
            transaction_cost_pct REAL DEFAULT 0.001,
            slippage_pct REAL DEFAULT 0.0005,
            -- All parameters as JSON (for flexibility)
            params_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (run_id) REFERENCES training_runs(run_id),
            CONSTRAINT valid_learning_rate CHECK(learning_rate IS NULL OR learning_rate > 0),
            CONSTRAINT valid_batch_size CHECK(batch_size IS NULL OR batch_size > 0),
            CONSTRAINT valid_gamma CHECK(gamma IS NULL OR (gamma >= 0 AND gamma <= 1))
        );
        """
    )

    print("✓ Created 'hyperparameters' table")


def create_ensemble_weights_table(conn: sqlite3.Connection) -> None:
    """
    Create the ensemble_weights table for tracking ensemble agent weights over time.

    Stores the weights assigned to each agent in an ensemble.
    Weights can change over time based on recent performance.

    Schema Design:
    - weight_id: Unique identifier
    - ensemble_id: Identifier for this ensemble configuration
    - update_time: When weights were updated
    - run_id: Reference to agent's training run
    - weight: Weight assigned to this agent (0.0-1.0)
    - performance_score: Performance metric used to calculate weight
    - is_active: Whether this agent is currently active
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ensemble_weights (
            weight_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ensemble_id TEXT NOT NULL,
            update_time INTEGER NOT NULL,
            update_date TEXT NOT NULL,
            run_id TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            weight REAL NOT NULL CHECK(weight >= 0 AND weight <= 1),
            performance_score REAL,
            sharpe_ratio REAL,
            win_rate REAL,
            is_active INTEGER NOT NULL DEFAULT 1,
            weighting_method TEXT CHECK(
                weighting_method IN (
                    'equal',
                    'sharpe_weighted',
                    'performance_weighted',
                    'adaptive',
                    'manual'
                )
            ),
            lookback_days INTEGER,
            notes TEXT,
            metadata TEXT,
            FOREIGN KEY (run_id) REFERENCES training_runs(run_id)
        );
        """
    )

    # Create composite index for efficient ensemble lookups
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ensemble_weights_ensemble_time
        ON ensemble_weights(ensemble_id, update_time DESC);
        """
    )

    print("✓ Created 'ensemble_weights' table")


def create_training_episodes_table(conn: sqlite3.Connection) -> None:
    """
    Create the training_episodes table for tracking individual training episodes.

    Stores metrics for each episode during training.
    Useful for monitoring training progress and detecting issues.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS training_episodes (
            episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            episode_number INTEGER NOT NULL,
            episode_reward REAL NOT NULL,
            episode_length INTEGER NOT NULL,
            episode_time INTEGER NOT NULL,
            mean_action REAL,
            std_action REAL,
            mean_value REAL,
            mean_loss REAL,
            learning_rate REAL,
            exploration_rate REAL,
            metadata TEXT,
            FOREIGN KEY (run_id) REFERENCES training_runs(run_id),
            CONSTRAINT unique_episode UNIQUE(run_id, episode_number)
        );
        """
    )

    print("✓ Created 'training_episodes' table")


def create_indexes(conn: sqlite3.Connection) -> None:
    """
    Create indexes for common query patterns.
    """
    indexes = [
        # Training runs indexes
        (
            "idx_training_runs_algorithm",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_algorithm ON training_runs(algorithm);"
        ),
        (
            "idx_training_runs_status",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_status ON training_runs(status);"
        ),
        (
            "idx_training_runs_start_time",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_start_time ON training_runs(start_time DESC);"
        ),
        (
            "idx_training_runs_model_name",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_model_name ON training_runs(model_name);"
        ),

        # Agent performance indexes
        (
            "idx_agent_performance_run_id",
            "CREATE INDEX IF NOT EXISTS idx_agent_performance_run_id ON agent_performance(run_id);"
        ),
        (
            "idx_agent_performance_evaluation_type",
            "CREATE INDEX IF NOT EXISTS idx_agent_performance_evaluation_type ON agent_performance(evaluation_type);"
        ),
        (
            "idx_agent_performance_sharpe",
            "CREATE INDEX IF NOT EXISTS idx_agent_performance_sharpe ON agent_performance(sharpe_ratio DESC);"
        ),
        (
            "idx_agent_performance_date",
            "CREATE INDEX IF NOT EXISTS idx_agent_performance_date ON agent_performance(evaluation_date DESC);"
        ),

        # Hyperparameters indexes
        (
            "idx_hyperparameters_run_id",
            "CREATE INDEX IF NOT EXISTS idx_hyperparameters_run_id ON hyperparameters(run_id);"
        ),
        (
            "idx_hyperparameters_algorithm",
            "CREATE INDEX IF NOT EXISTS idx_hyperparameters_algorithm ON hyperparameters(algorithm);"
        ),

        # Training episodes indexes
        (
            "idx_training_episodes_run_id",
            "CREATE INDEX IF NOT EXISTS idx_training_episodes_run_id ON training_episodes(run_id);"
        ),
        (
            "idx_training_episodes_run_episode",
            "CREATE INDEX IF NOT EXISTS idx_training_episodes_run_episode ON training_episodes(run_id, episode_number);"
        ),
    ]

    for idx_name, sql in indexes:
        try:
            conn.execute(sql)
            print(f"✓ Created index '{idx_name}'")
        except sqlite3.OperationalError as e:
            print(f"⚠ Warning: Could not create index '{idx_name}': {e}")


def create_views(conn: sqlite3.Connection) -> None:
    """
    Create helpful views for common queries.
    """
    # View for comparing agent performance
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS v_agent_leaderboard AS
        SELECT
            tr.algorithm,
            tr.model_name,
            ap.sharpe_ratio,
            ap.total_return_pct,
            ap.max_drawdown_pct,
            ap.win_rate,
            ap.total_trades,
            ap.evaluation_type,
            ap.evaluation_date,
            tr.run_id
        FROM agent_performance ap
        JOIN training_runs tr ON ap.run_id = tr.run_id
        WHERE ap.evaluation_type = 'validation'
        ORDER BY ap.sharpe_ratio DESC;
        """
    )

    # View for current ensemble composition
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS v_current_ensemble AS
        SELECT
            ew.ensemble_id,
            tr.algorithm,
            tr.model_name,
            ew.weight,
            ew.performance_score,
            ew.sharpe_ratio,
            datetime(ew.update_time, 'unixepoch') as last_updated
        FROM ensemble_weights ew
        JOIN training_runs tr ON ew.run_id = tr.run_id
        WHERE ew.is_active = 1
        AND ew.update_time = (
            SELECT MAX(update_time)
            FROM ensemble_weights
            WHERE ensemble_id = ew.ensemble_id
        )
        ORDER BY ew.weight DESC;
        """
    )

    # View for training run summary
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS v_training_summary AS
        SELECT
            tr.run_id,
            tr.algorithm,
            tr.model_name,
            tr.status,
            tr.total_timesteps,
            ROUND(tr.duration_seconds / 3600.0, 2) as duration_hours,
            datetime(tr.start_time, 'unixepoch') as started_at,
            ap.sharpe_ratio,
            ap.win_rate,
            ap.total_return_pct,
            hp.learning_rate,
            hp.batch_size
        FROM training_runs tr
        LEFT JOIN agent_performance ap ON tr.run_id = ap.run_id
            AND ap.evaluation_type = 'validation'
        LEFT JOIN hyperparameters hp ON tr.run_id = hp.run_id
        ORDER BY tr.start_time DESC;
        """
    )

    # View for hyperparameter optimization results
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS v_hyperparameter_results AS
        SELECT
            hp.algorithm,
            hp.learning_rate,
            hp.batch_size,
            hp.n_steps,
            hp.gamma,
            ap.sharpe_ratio,
            ap.win_rate,
            ap.total_return_pct,
            tr.run_id
        FROM hyperparameters hp
        JOIN training_runs tr ON hp.run_id = tr.run_id
        LEFT JOIN agent_performance ap ON tr.run_id = ap.run_id
            AND ap.evaluation_type = 'validation'
        WHERE tr.status = 'completed'
        ORDER BY ap.sharpe_ratio DESC;
        """
    )

    print("✓ Created helpful query views")


def upgrade(db_path: str = ML_TRAINING_DB_PATH) -> None:
    """
    Run the migration to create ML training tables.

    This migration is idempotent - safe to run multiple times.
    """
    print(f"\n=== Running Migration 003: Create ML Training Tables ===")
    print(f"Database: {db_path}\n")

    _ensure_dir(db_path)
    conn = init_optimized_connection(db_path)

    try:
        create_training_runs_table(conn)
        create_agent_performance_table(conn)
        create_hyperparameters_table(conn)
        create_ensemble_weights_table(conn)
        create_training_episodes_table(conn)
        create_indexes(conn)
        create_views(conn)

        conn.commit()
        print("\n✅ Migration 003 completed successfully!")

        # Print sample queries
        print("\n" + "="*60)
        print("SAMPLE QUERIES")
        print("="*60)
        print("""
# 1. Get all completed training runs
SELECT * FROM training_runs WHERE status = 'completed' ORDER BY start_time DESC;

# 2. Get best performing agents by Sharpe ratio
SELECT * FROM v_agent_leaderboard LIMIT 10;

# 3. Get current ensemble composition
SELECT * FROM v_current_ensemble;

# 4. Compare hyperparameters for top performers
SELECT * FROM v_hyperparameter_results LIMIT 10;

# 5. Get training run details with performance
SELECT * FROM v_training_summary;

# 6. Get performance metrics for a specific run
SELECT * FROM agent_performance WHERE run_id = 'your-run-id';

# 7. Get training progress for a run
SELECT
    episode_number,
    episode_reward,
    episode_length,
    datetime(episode_time, 'unixepoch') as episode_time
FROM training_episodes
WHERE run_id = 'your-run-id'
ORDER BY episode_number;

# 8. Find best hyperparameters for PPO
SELECT
    learning_rate,
    batch_size,
    n_steps,
    AVG(sharpe_ratio) as avg_sharpe
FROM hyperparameters hp
JOIN agent_performance ap ON hp.run_id = ap.run_id
WHERE hp.algorithm = 'PPO' AND ap.evaluation_type = 'validation'
GROUP BY learning_rate, batch_size, n_steps
ORDER BY avg_sharpe DESC
LIMIT 5;

# 9. Get ensemble weight changes over time
SELECT
    update_date,
    algorithm,
    weight,
    sharpe_ratio
FROM ensemble_weights
WHERE ensemble_id = 'production'
ORDER BY update_time DESC
LIMIT 20;

# 10. Compare algorithm performance
SELECT
    algorithm,
    COUNT(*) as num_runs,
    AVG(sharpe_ratio) as avg_sharpe,
    MAX(sharpe_ratio) as best_sharpe,
    AVG(win_rate) as avg_win_rate
FROM training_runs tr
JOIN agent_performance ap ON tr.run_id = ap.run_id
WHERE tr.status = 'completed' AND ap.evaluation_type = 'validation'
GROUP BY algorithm
ORDER BY avg_sharpe DESC;
        """)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration 003 failed: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str = ML_TRAINING_DB_PATH) -> None:
    """
    Rollback migration (drop tables).

    WARNING: This will delete all ML training data!
    """
    print(f"\n=== Rolling Back Migration 003 ===")
    print(f"Database: {db_path}\n")

    conn = init_optimized_connection(db_path)

    try:
        conn.execute("DROP VIEW IF EXISTS v_hyperparameter_results;")
        conn.execute("DROP VIEW IF EXISTS v_training_summary;")
        conn.execute("DROP VIEW IF EXISTS v_current_ensemble;")
        conn.execute("DROP VIEW IF EXISTS v_agent_leaderboard;")
        conn.execute("DROP TABLE IF EXISTS training_episodes;")
        conn.execute("DROP TABLE IF EXISTS ensemble_weights;")
        conn.execute("DROP TABLE IF EXISTS hyperparameters;")
        conn.execute("DROP TABLE IF EXISTS agent_performance;")
        conn.execute("DROP TABLE IF EXISTS training_runs;")

        conn.commit()
        print("\n✅ Migration 003 rolled back successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
