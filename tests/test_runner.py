"""Smoke tests for the runner module."""

from catalyst_bot.runner import main as runner_main


def test_runner_once_completes_without_errors(monkeypatch) -> None:
    # Ensure the runner does not send alerts or classify
    monkeypatch.setenv("FEATURE_RECORD_ONLY", "true")
    monkeypatch.setenv("FEATURE_ALERTS", "false")
    # Use a temporary directory for data to avoid clobbering real files
    monkeypatch.setenv("PRICE_CEILING", "10")
    # Run a single cycle; should return quickly without exceptions
    runner_main(once=True, loop=False)
