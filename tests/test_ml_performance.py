# =============================================================================
# FILE 2: tests/test_ml_performance.py
# PURPOSE: Evaluates ML model Accuracy, Precision, and Recall
# WHERE TO PUT IT: tests/ folder (same folder as test_latency.py)
# HOW TO RUN: python tests/test_ml_performance.py
# WHAT TO EXPECT: Accuracy %, Precision %, Recall % per class + confusion matrix
# NOTE: Run from project root so Django settings load correctly
# =============================================================================

import os
import sys
import django
import numpy as np
import pandas as pd
import joblib

# ── Django setup (needed to access settings.py for ML_MODEL_PATH) ─────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mine_safety_project.settings")
django.setup()

from django.conf import settings
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    classification_report,
    confusion_matrix
)


def separator(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


# ── Load the trained model ────────────────────────────────────────────────────

def load_model():
    model_path = settings.ML_MODEL_PATH
    print(f"  Loading model from: {model_path}")
    if not os.path.exists(model_path):
        print("  ❌ Model file not found! Check ML_MODEL_PATH in settings.py")
        sys.exit(1)
    model = joblib.load(model_path)
    print("  ✅ Model loaded successfully")
    return model


# ── Build a test dataset ──────────────────────────────────────────────────────
# These are hand-crafted test cases where we KNOW the correct label
# based on the thresholds defined in your Arduino code and fallback logic:
#   SAFE     (0): CO <= 30, Temp <= 28
#   WARNING  (1): CO 30-50, Temp 28-35
#   CRITICAL (2): CO > 50, Temp > 35

def build_test_dataset():
    """
    Returns X (features) and y (true labels) for evaluation.
    Each row = [temp, gas, temp_avg, gas_avg, temp_rate, gas_rate,
                temp_x_gas, gas_squared, temp_above_35, gas_above_50]
    Labels: 0=SAFE, 1=WARNING, 2=CRITICAL
    """

    # Helper to compute the 4 derived features automatically
    def row(temp, gas, t_avg, g_avg, t_rate, g_rate, label):
        return [
            temp, gas, t_avg, g_avg, t_rate, g_rate,
            temp * gas,          # temp_x_gas
            gas ** 2,            # gas_squared
            1 if temp > 35 else 0,  # temp_above_35
            1 if gas  > 50 else 0,  # gas_above_50
            label
        ]

    test_cases = [
        # ── SAFE cases (label=0) — temp≤28, CO≤30 ────────────────────────
        row(22.0,  15.0,  22.0,  15.0,   0.0,   0.0,  0),
        row(24.0,  20.0,  23.5,  18.0,   0.5,   2.0,  0),
        row(25.0,  25.0,  24.8,  24.0,   0.2,   1.0,  0),
        row(20.0,  10.0,  20.5,  11.0,  -0.5,   1.0,  0),
        row(27.0,  28.0,  26.5,  27.0,   0.5,   1.0,  0),
        row(18.0,   5.0,  19.0,   6.0,  -1.0,  -1.0,  0),
        row(23.0,  22.0,  22.8,  21.5,   0.2,   0.5,  0),
        row(26.0,  29.0,  25.5,  28.0,   0.5,   1.0,  0),
        row(21.0,  12.0,  21.5,  13.0,  -0.5,  -1.0,  0),
        row(19.0,   8.0,  20.0,   9.0,  -1.0,  -1.0,  0),

        # ── WARNING cases (label=1) — temp 28–35, CO 30–50 ───────────────
        row(29.0,  35.0,  28.5,  33.0,   1.0,   2.0,  1),
        row(31.0,  40.0,  30.0,  38.0,   2.0,   3.0,  1),
        row(30.0,  45.0,  29.5,  42.0,   1.5,   4.0,  1),
        row(32.0,  33.0,  31.0,  32.0,   2.0,   1.5,  1),
        row(28.5,  48.0,  28.0,  45.0,   0.5,   5.0,  1),
        row(33.0,  32.0,  32.0,  31.0,   2.0,   1.0,  1),
        row(29.5,  42.0,  29.0,  40.0,   1.0,   3.0,  1),
        row(34.0,  31.0,  33.0,  30.0,   2.5,   1.0,  1),
        row(30.5,  46.0,  30.0,  44.0,   1.0,   4.0,  1),
        row(31.5,  38.0,  31.0,  37.0,   1.5,   2.0,  1),

        # ── CRITICAL cases (label=2) — temp>35, CO>50 ────────────────────
        row(38.0,  60.0,  37.0,  58.0,   5.0,   8.0,  2),
        row(42.0,  80.0,  40.0,  75.0,   7.0,  12.0,  2),
        row(45.0, 100.0,  43.0,  95.0,  10.0,  15.0,  2),
        row(36.0,  55.0,  35.0,  52.0,   4.0,   6.0,  2),
        row(50.0, 150.0,  48.0, 140.0,  12.0,  20.0,  2),
        row(40.0,  70.0,  39.0,  68.0,   6.0,  10.0,  2),
        row(37.0,  58.0,  36.0,  56.0,   4.0,   7.0,  2),
        row(44.0,  90.0,  42.0,  88.0,   8.0,  13.0,  2),
        row(39.0,  65.0,  38.0,  63.0,   5.0,   9.0,  2),
        row(46.0, 120.0,  45.0, 115.0,  11.0,  18.0,  2),
    ]

    columns = [
        'temperature', 'gas', 'temp_avg_5min', 'gas_avg_5min',
        'temp_rate_of_change', 'gas_rate_of_change',
        'temp_x_gas', 'gas_squared', 'temp_above_35', 'gas_above_50',
        'true_label'
    ]
    df = pd.DataFrame(test_cases, columns=columns)

    FEATURES = [
        'temperature', 'gas', 'temp_avg_5min', 'gas_avg_5min',
        'temp_rate_of_change', 'gas_rate_of_change',
        'temp_x_gas', 'gas_squared', 'temp_above_35', 'gas_above_50',
    ]
    X = df[FEATURES]
    y = df['true_label']

    return X, y


# ── Run evaluation ────────────────────────────────────────────────────────────

def evaluate_model(model, X, y_true):
    y_pred = model.predict(X)

    # Try to get probabilities for confidence reporting
    try:
        y_proba = model.predict_proba(X)
        avg_confidence = np.max(y_proba, axis=1).mean() * 100
        has_proba = True
    except Exception:
        has_proba = False
        avg_confidence = 0

    # Core metrics
    accuracy  = accuracy_score(y_true, y_pred) * 100
    precision = precision_score(y_true, y_pred, average='weighted', zero_division=0) * 100
    recall    = recall_score(y_true, y_pred, average='weighted', zero_division=0) * 100

    # Per-class metrics
    class_names = ['SAFE (0)', 'WARNING (1)', 'CRITICAL (2)']
    report = classification_report(
        y_true, y_pred,
        target_names=class_names,
        zero_division=0
    )

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)

    return {
        'accuracy':         accuracy,
        'precision':        precision,
        'recall':           recall,
        'confidence':       avg_confidence,
        'has_proba':        has_proba,
        'report':           report,
        'confusion_matrix': cm,
        'y_pred':           y_pred,
        'y_true':           y_true,
    }


def print_confusion_matrix(cm, class_names):
    print("\n  Confusion Matrix:")
    print(f"  {'':15}", end="")
    for name in class_names:
        print(f"  {name:>12}", end="")
    print()
    for i, row_name in enumerate(class_names):
        print(f"  {row_name:15}", end="")
        for val in cm[i]:
            print(f"  {val:>12}", end="")
        print()
    print("\n  Rows = Actual | Columns = Predicted")


def print_sample_predictions(model, X, y_true):
    y_pred = model.predict(X)
    label_map = {0: 'SAFE', 1: 'WARNING', 2: 'CRITICAL'}
    correct_symbol = {True: '✅', False: '❌'}

    print("\n  Sample Predictions (first 15):")
    print(f"  {'#':>3}  {'Temp':>6}  {'CO':>6}  {'Actual':>10}  {'Predicted':>10}  {'Match'}")
    print(f"  {'─'*55}")
    for i in range(min(15, len(X))):
        row       = X.iloc[i]
        actual    = label_map[int(y_true.iloc[i])]
        predicted = label_map[int(y_pred[i])]
        match     = int(y_true.iloc[i]) == int(y_pred[i])
        print(f"  {i+1:>3}  {row['temperature']:>6.1f}  {row['gas']:>6.1f}  "
              f"{actual:>10}  {predicted:>10}  {correct_symbol[match]}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import datetime

    print("\n" + "█"*60)
    print("  MINE SAFETY SYSTEM — ML MODEL EVALUATION")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)

    separator("Loading Model")
    model = load_model()

    separator("Building Test Dataset")
    X, y_true = build_test_dataset()
    print(f"  Total test samples: {len(X)}")
    print(f"  SAFE samples:       {(y_true == 0).sum()}")
    print(f"  WARNING samples:    {(y_true == 1).sum()}")
    print(f"  CRITICAL samples:   {(y_true == 2).sum()}")

    separator("Running Evaluation")
    results = evaluate_model(model, X, y_true)

    separator("RESULTS")
    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  Accuracy:   {results['accuracy']:>6.2f}%                │")
    print(f"  │  Precision:  {results['precision']:>6.2f}%                │")
    print(f"  │  Recall:     {results['recall']:>6.2f}%                │")
    if results['has_proba']:
        print(f"  │  Avg Conf:   {results['confidence']:>6.2f}%                │")
    print(f"  └─────────────────────────────────────┘")

    print(f"\n  ── Per-Class Report ──")
    print(f"  {results['report']}")

    class_names = ['SAFE', 'WARNING', 'CRITICAL']
    print_confusion_matrix(results['confusion_matrix'], class_names)
    print_sample_predictions(model, X, y_true)

    separator("Interpretation")
    acc = results['accuracy']
    if acc >= 95:
        print("  ✅ EXCELLENT — Model performing at production grade (≥95%)")
    elif acc >= 85:
        print("  ✅ GOOD — Model performing well (≥85%)")
    elif acc >= 70:
        print("  ⚠️  ACCEPTABLE — Consider retraining with more data (≥70%)")
    else:
        print("  ❌ POOR — Model needs retraining (<70%)")

    print(f"\n  Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60 + "\n")