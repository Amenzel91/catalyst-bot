-- ============================================================================
-- ML TRAINING DATABASE SCHEMA
-- Database: data/ml_training.db
-- Migration: 003_create_ml_training_tables.py
-- ============================================================================
-- This file contains the complete SQL schema for the ML training database.
-- It tracks RL training runs, agent performance, hyperparameters, and ensemble weights.
-- ============================================================================

-- ============================================================================
-- TABLE: training_runs
-- ============================================================================
-- Metadata for each RL training session.
-- ============================================================================

CREATE TABLE IF NOT EXISTS training_runs (
    -- Primary key
    run_id TEXT PRIMARY KEY,

    -- Algorithm details
    algorithm TEXT NOT NULL CHECK(
        algorithm IN ('PPO', 'SAC', 'A2C', 'TD3', 'DQN', 'DDPG', 'Ensemble')
    ),
    model_name TEXT NOT NULL,

    -- Timing
    start_time INTEGER NOT NULL,
    end_time INTEGER,
    duration_seconds REAL,

    -- Training configuration
    total_timesteps INTEGER NOT NULL,
    train_start_date TEXT NOT NULL,
    train_end_date TEXT NOT NULL,
    val_start_date TEXT,
    val_end_date TEXT,

    -- Status and results
    status TEXT NOT NULL DEFAULT 'running' CHECK(
        status IN ('running', 'completed', 'failed', 'stopped', 'aborted')
    ),
    final_reward REAL,
    best_reward REAL,
    final_loss REAL,
    convergence_achieved INTEGER DEFAULT 0,
    early_stopped INTEGER DEFAULT 0,

    -- Model artifacts
    model_path TEXT,
    tensorboard_log_dir TEXT,

    -- Environment details
    python_version TEXT,
    stable_baselines_version TEXT,
    random_seed INTEGER,
    device TEXT,
    num_envs INTEGER DEFAULT 1,

    -- Additional information
    notes TEXT,
    metadata TEXT,

    -- Constraints
    CONSTRAINT valid_duration CHECK(
        (end_time IS NULL) OR (duration_seconds >= 0)
    ),
    CONSTRAINT valid_timesteps CHECK(total_timesteps > 0)
);

-- ============================================================================
-- TABLE: agent_performance
-- ============================================================================
-- Performance metrics for trained agents on validation/test sets.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_performance (
    -- Primary key
    performance_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- References
    run_id TEXT NOT NULL,

    -- Evaluation timing
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

    -- Additional information
    notes TEXT,
    metadata TEXT,

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES training_runs(run_id)
);

-- ============================================================================
-- TABLE: hyperparameters
-- ============================================================================
-- Hyperparameter configurations for each training run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS hyperparameters (
    -- Primary key
    hyperparameter_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- References
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

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES training_runs(run_id),

    -- Constraints
    CONSTRAINT valid_learning_rate CHECK(learning_rate IS NULL OR learning_rate > 0),
    CONSTRAINT valid_batch_size CHECK(batch_size IS NULL OR batch_size > 0),
    CONSTRAINT valid_gamma CHECK(gamma IS NULL OR (gamma >= 0 AND gamma <= 1))
);

-- ============================================================================
-- TABLE: ensemble_weights
-- ============================================================================
-- Weights assigned to agents in ensemble configurations.
-- ============================================================================

CREATE TABLE IF NOT EXISTS ensemble_weights (
    -- Primary key
    weight_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Ensemble configuration
    ensemble_id TEXT NOT NULL,
    update_time INTEGER NOT NULL,
    update_date TEXT NOT NULL,

    -- Agent reference
    run_id TEXT NOT NULL,
    algorithm TEXT NOT NULL,

    -- Weight and performance
    weight REAL NOT NULL CHECK(weight >= 0 AND weight <= 1),
    performance_score REAL,
    sharpe_ratio REAL,
    win_rate REAL,

    -- Status
    is_active INTEGER NOT NULL DEFAULT 1,

    -- Weighting configuration
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

    -- Additional information
    notes TEXT,
    metadata TEXT,

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES training_runs(run_id)
);

-- ============================================================================
-- TABLE: training_episodes
-- ============================================================================
-- Individual episode metrics during training.
-- ============================================================================

CREATE TABLE IF NOT EXISTS training_episodes (
    -- Primary key
    episode_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- References
    run_id TEXT NOT NULL,

    -- Episode details
    episode_number INTEGER NOT NULL,
    episode_reward REAL NOT NULL,
    episode_length INTEGER NOT NULL,
    episode_time INTEGER NOT NULL,

    -- Episode statistics
    mean_action REAL,
    std_action REAL,
    mean_value REAL,
    mean_loss REAL,
    learning_rate REAL,
    exploration_rate REAL,

    -- Additional information
    metadata TEXT,

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES training_runs(run_id),

    -- Constraints
    CONSTRAINT unique_episode UNIQUE(run_id, episode_number)
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Indexes for common query patterns and performance optimization.
-- ============================================================================

-- Training runs indexes
CREATE INDEX IF NOT EXISTS idx_training_runs_algorithm ON training_runs(algorithm);
CREATE INDEX IF NOT EXISTS idx_training_runs_status ON training_runs(status);
CREATE INDEX IF NOT EXISTS idx_training_runs_start_time ON training_runs(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_training_runs_model_name ON training_runs(model_name);

-- Agent performance indexes
CREATE INDEX IF NOT EXISTS idx_agent_performance_run_id ON agent_performance(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_performance_evaluation_type ON agent_performance(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_agent_performance_sharpe ON agent_performance(sharpe_ratio DESC);
CREATE INDEX IF NOT EXISTS idx_agent_performance_date ON agent_performance(evaluation_date DESC);

-- Hyperparameters indexes
CREATE INDEX IF NOT EXISTS idx_hyperparameters_run_id ON hyperparameters(run_id);
CREATE INDEX IF NOT EXISTS idx_hyperparameters_algorithm ON hyperparameters(algorithm);

-- Ensemble weights indexes
CREATE INDEX IF NOT EXISTS idx_ensemble_weights_ensemble_time ON ensemble_weights(ensemble_id, update_time DESC);

-- Training episodes indexes
CREATE INDEX IF NOT EXISTS idx_training_episodes_run_id ON training_episodes(run_id);
CREATE INDEX IF NOT EXISTS idx_training_episodes_run_episode ON training_episodes(run_id, episode_number);

-- ============================================================================
-- VIEWS
-- ============================================================================
-- Pre-built views for common queries with calculated fields.
-- ============================================================================

-- View: Agent leaderboard (best performing agents)
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

-- View: Current ensemble composition
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

-- View: Training run summary
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

-- View: Hyperparameter optimization results
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

-- ============================================================================
-- SAMPLE QUERIES
-- ============================================================================

/*
-- Get all completed training runs
SELECT * FROM training_runs WHERE status = 'completed' ORDER BY start_time DESC;

-- Get best performing agents by Sharpe ratio
SELECT * FROM v_agent_leaderboard LIMIT 10;

-- Get current ensemble composition
SELECT * FROM v_current_ensemble;

-- Compare hyperparameters for top performers
SELECT * FROM v_hyperparameter_results LIMIT 10;

-- Get training run details with performance
SELECT * FROM v_training_summary;

-- Get performance metrics for a specific run
SELECT * FROM agent_performance WHERE run_id = 'your-run-id';

-- Get training progress for a run
SELECT
    episode_number,
    episode_reward,
    episode_length,
    datetime(episode_time, 'unixepoch') as episode_time
FROM training_episodes
WHERE run_id = 'your-run-id'
ORDER BY episode_number;

-- Find best hyperparameters for PPO
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

-- Get ensemble weight changes over time
SELECT
    update_date,
    algorithm,
    weight,
    sharpe_ratio
FROM ensemble_weights
WHERE ensemble_id = 'production'
ORDER BY update_time DESC
LIMIT 20;

-- Compare algorithm performance
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
*/
