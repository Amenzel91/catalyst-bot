"""
ml_utils.py
===========

This module provides utility functions for machine‑learning based
alert ranking and classification.  Patch C introduces a mechanism
for training models on historical features and using them to assign
confidence scores to new alerts.  The functions here are designed
to be lightweight placeholders that can be extended with real
machine‑learning algorithms.  They avoid heavy dependencies so that
the bot can run in constrained environments.

Key Functions
-------------

* ``extract_features`` – Convert raw alert data into numerical feature
  vectors suitable for modeling.  The default implementation returns
  basic features such as price change, sentiment scores and indicators.

* ``train_model`` – Train a simple classifier/regressor on labeled
  feature data.  By default this returns a dummy model that memorizes
  the mean target value.

* ``score_alerts`` – Apply a trained model to compute confidence
  scores for new alerts.  Returns an array of floats between 0 and 1.

These stubs can be replaced or extended with more sophisticated
implementations using libraries such as scikit‑learn, XGBoost or
TensorFlow.  Additional functions may be added to save and load
models to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Tuple

import numpy as np
import pandas as pd


@dataclass
class DummyModel:
    """A trivial model that predicts the mean of the target values.

    This model is used as a fallback when no real machine‑learning
    library is available.  It stores the mean of the training targets
    and returns it for any input.  The ``predict`` method returns
    an array of constant scores between 0 and 1.
    """

    mean_target: float = 0.5

    def predict(self, X: Iterable) -> np.ndarray:
        length = len(X) if hasattr(X, "__len__") else 1
        return np.full(length, self.mean_target, dtype=float)


def extract_features(
    alerts: Iterable[dict[str, Any]]
) -> Tuple[pd.DataFrame, List[Any]]:
    """Extract numerical features and labels from a sequence of alert dicts.

    Each alert dict is expected to contain at minimum:
    - 'price_change': float or None – percentage change since previous close
    - 'sentiment_score': float or None – combined sentiment from news and social
    - 'indicator_score': float or None – composite indicator score
    - 'label': optional – ground truth label (1 for successful, 0 for failed)

    Parameters
    ----------
    alerts : iterable of dict
        Alerts containing raw fields.

    Returns
    -------
    (features_df, labels)
        ``features_df`` is a DataFrame with numeric columns.
        ``labels`` is a list of target values or ``None`` if not present.
    """
    rows = []
    labels = []
    for alert in alerts:
        price_change = float(alert.get("price_change") or 0.0)
        sent_score = float(alert.get("sentiment_score") or 0.0)
        indicator_score = float(alert.get("indicator_score") or 0.0)
        rows.append(
            {
                "price_change": price_change,
                "sentiment_score": sent_score,
                "indicator_score": indicator_score,
            }
        )
        labels.append(alert.get("label"))
    df = pd.DataFrame(rows)
    return df, labels


def train_model(X: pd.DataFrame, y: Iterable[Any]) -> DummyModel:
    """Train a simple model on the provided features and labels.

    In this stub implementation, a DummyModel is returned which simply
    memorizes the mean of the target values (ignoring None values).  If
    no valid labels are present, the default mean is 0.5.

    Parameters
    ----------
    X : pandas.DataFrame
        Feature matrix.
    y : iterable
        Target labels (1/0 values).  Non‑numeric or None values are
        ignored in the mean calculation.

    Returns
    -------
    DummyModel
        Trained model with a ``predict`` method.
    """
    clean_labels = [
        float(lbl) for lbl in y if lbl is not None and isinstance(lbl, (int, float))
    ]
    if clean_labels:
        mean_target = float(np.mean(clean_labels))
    else:
        mean_target = 0.5
    return DummyModel(mean_target=mean_target)


def score_alerts(model: DummyModel, X: pd.DataFrame) -> List[float]:
    """Score alerts using the provided model.

    The model should implement a ``predict`` method that accepts an
    iterable of feature vectors and returns an array of scores between
    0 and 1.  The stub implementation returns a constant value for
    all inputs.

    Parameters
    ----------
    model : DummyModel
        Trained model with a predict method.
    X : pandas.DataFrame
        DataFrame of features.

    Returns
    -------
    list of float
        Confidence scores between 0 and 1.
    """
    preds = model.predict(X.values)
    # Clip to [0,1] range just in case
    preds = np.clip(preds, 0.0, 1.0)
    return preds.tolist()


# ---------------------------------------------------------------------------
# Model persistence helpers
#
def load_model(path: str) -> DummyModel:
    """Load a model from the given JSON file.

    This helper expects a JSON file containing a single key ``mean_target``
    representing the average training target.  If the file cannot be read
    or does not contain the expected key, a ``DummyModel`` with the
    default mean target (0.5) is returned.

    Parameters
    ----------
    path : str
        Path to a JSON file containing model parameters.

    Returns
    -------
    DummyModel
        Loaded model with a ``predict`` method.
    """
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mean_target = float(data.get("mean_target", 0.5))
        return DummyModel(mean_target=mean_target)
    except Exception:
        # On any error, fall back to a default model
        return DummyModel(mean_target=0.5)


# Define the public API for this module.  The '__all__' list specifies
# which names will be exported when ``from catalyst_bot.ml_utils import *``
__all__ = [
    "DummyModel",
    "extract_features",
    "train_model",
    "score_alerts",
    "load_model",
]
