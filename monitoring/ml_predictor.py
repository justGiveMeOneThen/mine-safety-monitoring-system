import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from collections import deque
import os

class RiskPredictor:
    def __init__(self):
        self.model = None
        self.load_model()
        self.temp_history = deque(maxlen=5)
        self.gas_history  = deque(maxlen=5)

    def load_model(self):
        try:
            if os.path.exists(settings.ML_MODEL_PATH):
                self.model = joblib.load(settings.ML_MODEL_PATH)
                print("✅ ML Model loaded successfully: risk_model.joblib")
            else:
                print("⚠️ ML Model not found. Using fallback predictions.")
                self.model = None
        except Exception as e:
            print(f"❌ Error loading ML model: {e}")
            self.model = None

    def _build_features(self, co_level, temperature):
        """Build the 10-feature DataFrame expected by the model."""
        self.temp_history.append(temperature)
        self.gas_history.append(co_level)

        temp_avg_5min = np.mean(self.temp_history)
        gas_avg_5min  = np.mean(self.gas_history)

        if len(self.temp_history) >= 2:
            temp_rate_of_change = temperature - self.temp_history[0]
            gas_rate_of_change  = co_level    - self.gas_history[0]
        else:
            temp_rate_of_change = 0.0
            gas_rate_of_change  = 0.0

        return pd.DataFrame([[
            temperature, co_level,
            temp_avg_5min, gas_avg_5min,
            temp_rate_of_change, gas_rate_of_change,
            temperature * co_level,
            co_level ** 2,
            1 if temperature > 35 else 0,
            1 if co_level > 50  else 0,
        ]], columns=[
            'temperature', 'gas',
            'temp_avg_5min', 'gas_avg_5min',
            'temp_rate_of_change', 'gas_rate_of_change',
            'temp_x_gas', 'gas_squared',
            'temp_above_35', 'gas_above_50',
        ]), temp_rate_of_change, gas_rate_of_change

    def _tree_confidence_interval(self, features, confidence=0.95):
        """
        Compute confidence interval using individual tree predictions.
        RandomForest is an ensemble — each tree votes independently.
        We use the spread of tree probabilities as our uncertainty measure.
        Returns (lower_bound, upper_bound) for the predicted class probability.
        """
        try:
            # Collect predicted probability from every tree for the predicted class
            tree_probs = np.array([
                tree.predict_proba(features)[0]
                for tree in self.model.estimators_
            ])  # shape: (n_trees, n_classes)

            # Mean probability per class across all trees
            mean_probs = tree_probs.mean(axis=0)
            predicted_class = np.argmax(mean_probs)

            # Probabilities for the predicted class across all trees
            class_probs = tree_probs[:, predicted_class]

            alpha = 1 - confidence
            lower = np.percentile(class_probs, alpha / 2 * 100)
            upper = np.percentile(class_probs, (1 - alpha / 2) * 100)

            return round(lower * 100, 1), round(upper * 100, 1)
        except Exception:
            return None, None

    def predict_risk(self, co_level, temperature):
        if self.model is None:
            return self._fallback_prediction(co_level, temperature)

        try:
            features, temp_rate, gas_rate = self._build_features(co_level, temperature)

            # ── Primary prediction ─────────────────────────────
            prediction   = self.model.predict(features)[0]
            probabilities = self.model.predict_proba(features)[0]

            # ── All 3 class probabilities ──────────────────────
            prob_normal   = round(float(probabilities[0]) * 100, 1)
            prob_warning  = round(float(probabilities[1]) * 100, 1)
            prob_critical = round(float(probabilities[2]) * 100, 1)
            confidence    = round(float(max(probabilities)) * 100, 1)

            # ── 95% confidence interval via tree variance ──────
            ci_lower, ci_upper = self._tree_confidence_interval(features)

            # ── Projected future values ────────────────────────
            predicted_co   = max(0, co_level    + gas_rate  * 3)
            predicted_temp = max(0, temperature + temp_rate * 3)

            risk_map = {0: 'normal', 1: 'warning', 2: 'critical'}
            risk_level = risk_map.get(int(prediction), 'normal')

            return {
                'predicted_co':    round(predicted_co, 2),
                'predicted_temp':  round(predicted_temp, 2),
                'risk_level':      risk_level,
                'confidence':      confidence,
                'prob_normal':     prob_normal,
                'prob_warning':    prob_warning,
                'prob_critical':   prob_critical,
                'ci_lower':        ci_lower,
                'ci_upper':        ci_upper,
                'model_used':      'RandomForest (200 trees)',
                'raw_prediction':  int(prediction),
                'temp_rate':       round(temp_rate, 3),
                'gas_rate':        round(gas_rate, 3),
            }

        except Exception as e:
            print(f"❌ Prediction error: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_prediction(co_level, temperature)

    def _fallback_prediction(self, co_level, temperature):
        predicted_co   = co_level    + (co_level    * 0.15)
        predicted_temp = temperature + (temperature * 0.08)

        if co_level > 50 or temperature > 35:
            risk_level = 'critical'
        elif co_level > 30 or temperature > 28:
            risk_level = 'warning'
        else:
            risk_level = 'normal'

        return {
            'predicted_co':   round(max(0, predicted_co), 2),
            'predicted_temp': round(max(0, predicted_temp), 2),
            'risk_level':     risk_level,
            'confidence':     None,
            'prob_normal':    None,
            'prob_warning':   None,
            'prob_critical':  None,
            'ci_lower':       None,
            'ci_upper':       None,
            'model_used':     'Rule-based (Fallback)',
            'raw_prediction': 2 if risk_level == 'critical' else 1 if risk_level == 'warning' else 0,
        }

    def reset_history(self):
        self.temp_history.clear()
        self.gas_history.clear()

predictor = RiskPredictor()