from catalyst_bot.backtest.metrics import HitDefinition, summarize_backtest


def test_metrics_summary_basic() -> None:
    rows = [
        {
            "realized_return": 0.05,
            "intraday_high_return": 0.09,
            "next_day_close_return": 0.01,
        },
        {
            "realized_return": -0.02,
            "intraday_high_return": 0.01,
            "next_day_close_return": 0.04,
        },
        {
            "realized_return": 0.00,
            "intraday_high_return": 0.03,
            "next_day_close_return": 0.00,
        },
    ]
    rule = HitDefinition(intraday_high_min=0.08, next_close_min=0.03)
    s = summarize_backtest(rows, rule)
    # There are 3 rows, 2 hits (first and second row)
    assert s.n == 3
    assert s.hits == 2
    assert abs(s.hit_rate - (2 / 3)) < 1e-9
    # Average realized return should be 0.01 ((0.05 - 0.02 + 0.0)/3)
    assert abs(s.avg_return - 0.01) < 1e-9
    # Max drawdown should be non-positive
    assert s.max_drawdown <= 0.0
