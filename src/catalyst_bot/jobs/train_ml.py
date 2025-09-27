"""
jobs.train_ml
=============

Command‑line interface for training machine‑learning models used in
Catalyst Bot.  Patch C proposes a workflow where historical alert
features are extracted, models are trained, and saved for future use
in ranking live alerts.

This script is a stub demonstrating how such a CLI might be structured.
It uses the functions in ``ml_utils.py`` to extract features from a
CSV file, train a model, and optionally save it to disk.  In practice,
this module should be invoked via a management command or a cron job.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd

from catalyst_bot.ml_utils import extract_features, train_model

def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train ML model for alert ranking")
    parser.add_argument('--input', '-i', required=True, help='Path to JSONL or CSV file of alerts with labels')
    parser.add_argument('--output', '-o', default='models/trained_model.json', help='Path to save trained model parameters')
    args = parser.parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    # Load alerts
    if input_path.suffix.lower() == '.csv':
        df = pd.read_csv(input_path)
        alerts = df.to_dict(orient='records')
    else:
        # Assume JSON Lines (one JSON object per line)
        alerts = []
        with input_path.open('r', encoding='utf-8') as f:
            for line in f:
                try:
                    alerts.append(json.loads(line))
                except Exception:
                    continue
    features_df, labels = extract_features(alerts)
    model = train_model(features_df, labels)
    # Save model parameters as JSON for later loading.  Real
    # implementations could use pickle or joblib instead.
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        json.dump({'mean_target': model.mean_target}, f, indent=2)
    print(f"Trained model saved to {out_path}")

if __name__ == '__main__':  # pragma: no cover
    main()