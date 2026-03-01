# monitoring/ml_predictor.py
# Updated to use 10 features matching the new training script

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
        # Store recent readings for rolling calculations (5-minute window)
        self.temp_history = deque(maxlen=5)
        self.gas_history  = deque(maxlen=5)

    def load_model(self):
        """Load the trained risk_model.joblib"""
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

    def predict_risk(self, co_level, temperature):
        """
        Predict risk level using the trained model.
        Input:  CO level (ppm), Temperature (°C)
        Output: dict with predicted risk level and future values

        Model expects these 10 features (exact order):
        1.  temperature
        2.  gas                  (CO level)
        3.  temp_avg_5min
        4.  gas_avg_5min
        5.  temp_rate_of_change
        6.  gas_rate_of_change
        7.  temp_x_gas           (interaction term)
        8.  gas_squared
        9.  temp_above_35        (binary flag)
        10. gas_above_50         (binary flag)
        """
        if self.model is None:
            return self._fallback_prediction(co_level, temperature)

        try:
            # Add current readings to rolling history
            self.temp_history.append(temperature)
            self.gas_history.append(co_level)

            # ── Features 3 & 4: Rolling averages ──────────────────────
            temp_avg_5min = np.mean(self.temp_history)
            gas_avg_5min  = np.mean(self.gas_history)

            # ── Features 5 & 6: Rate of change ────────────────────────
            if len(self.temp_history) >= 2:
                temp_rate_of_change = temperature - self.temp_history[0]
                gas_rate_of_change  = co_level    - self.gas_history[0]
            else:
                temp_rate_of_change = 0.0
                gas_rate_of_change  = 0.0

            # ── Features 7–10: New engineered features ─────────────────
            temp_x_gas   = temperature * co_level          # interaction term
            gas_squared  = co_level ** 2                   # non-linear CO signal
            temp_above_35 = 1 if temperature > 35 else 0  # binary danger flag
            gas_above_50  = 1 if co_level > 50  else 0    # binary danger flag

            # ── Build feature DataFrame (order must match training) ─────
            features = pd.DataFrame([[
                temperature,            # 1
                co_level,               # 2
                temp_avg_5min,          # 3
                gas_avg_5min,           # 4
                temp_rate_of_change,    # 5
                gas_rate_of_change,     # 6
                temp_x_gas,             # 7
                gas_squared,            # 8
                temp_above_35,          # 9
                gas_above_50,           # 10
            ]], columns=[
                'temperature',
                'gas',
                'temp_avg_5min',
                'gas_avg_5min',
                'temp_rate_of_change',
                'gas_rate_of_change',
                'temp_x_gas',
                'gas_squared',
                'temp_above_35',
                'gas_above_50',
            ])

            # ── Predict ────────────────────────────────────────────────
            prediction = self.model.predict(features)[0]

            # Confidence from probabilities
            try:
                probabilities = self.model.predict_proba(features)[0]
                confidence = max(probabilities) * 100
            except Exception:
                confidence = 0.0

            # ── Predict future values (rate-of-change projection) ──────
            predicted_co   = co_level    + (gas_rate_of_change  * 3)
            predicted_temp = temperature + (temp_rate_of_change * 3)

            # ── Map numeric label to risk string ───────────────────────
            risk_level_map = {
                0: 'normal',    # SAFE
                1: 'warning',   # CAUTION
                2: 'critical',  # DANGER
            }
            risk_level = risk_level_map.get(int(prediction), 'normal')

            return {
                'predicted_co':   max(0, predicted_co),
                'predicted_temp': max(0, predicted_temp),
                'risk_level':     risk_level,
                'model_used':     f'ML Model (RandomForest) - {confidence:.1f}% confidence',
                'raw_prediction': int(prediction),
                'temp_rate':      temp_rate_of_change,
                'gas_rate':       gas_rate_of_change,
            }

        except Exception as e:
            print(f"❌ Prediction error: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_prediction(co_level, temperature)

    def _fallback_prediction(self, co_level, temperature):
        """Rule-based fallback when ML model is unavailable."""
        predicted_co   = co_level    + (co_level    * 0.15)
        predicted_temp = temperature + (temperature * 0.08)

        if co_level > 50 or temperature > 35:
            risk_level = 'critical'
        elif co_level > 30 or temperature > 28:
            risk_level = 'warning'
        else:
            risk_level = 'normal'

        return {
            'predicted_co':   max(0, predicted_co),
            'predicted_temp': max(0, predicted_temp),
            'risk_level':     risk_level,
            'model_used':     'Rule-based (Fallback)',
            'raw_prediction': 2 if risk_level == 'critical' else 1 if risk_level == 'warning' else 0,
        }

    def reset_history(self):
        """Reset rolling history buffers (useful for new monitoring sessions)."""
        self.temp_history.clear()
        self.gas_history.clear()


# Singleton instance — imported by views.py and alerts.py
predictor = RiskPredictor()