# monitoring/ml_predictor.py - EXACT MATCH TO YOUR TRAINING

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
        self.gas_history = deque(maxlen=5)
    
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
        Predict risk level using the trained model
        Input: CO level (ppm), Temperature (°C)
        Output: Predicted risk level and future values
        
        Model expects these 6 features (in this exact order):
        1. temperature
        2. gas (CO level)
        3. temp_avg_5min
        4. gas_avg_5min
        5. temp_rate_of_change
        6. gas_rate_of_change
        """
        if self.model is None:
            return self._fallback_prediction(co_level, temperature)
        
        try:
            # Add current readings to history
            self.temp_history.append(temperature)
            self.gas_history.append(co_level)
            
            # Calculate rolling averages (5-minute window)
            temp_avg_5min = np.mean(self.temp_history) if len(self.temp_history) > 0 else temperature
            gas_avg_5min = np.mean(self.gas_history) if len(self.gas_history) > 0 else co_level
            
            # Calculate rate of change
            # (Current value - Value from 5 readings ago)
            if len(self.temp_history) >= 5:
                temp_rate_of_change = temperature - self.temp_history[0]
                gas_rate_of_change = co_level - self.gas_history[0]
            else:
                # Not enough history yet, use simple difference
                temp_rate_of_change = 0 if len(self.temp_history) < 2 else temperature - self.temp_history[0]
                gas_rate_of_change = 0 if len(self.gas_history) < 2 else co_level - self.gas_history[0]
            
            # Create feature array with the EXACT order from training
            features = pd.DataFrame([[
                temperature,              # 1. temperature
                co_level,                 # 2. gas
                temp_avg_5min,           # 3. temp_avg_5min
                gas_avg_5min,            # 4. gas_avg_5min
                temp_rate_of_change,     # 5. temp_rate_of_change
                gas_rate_of_change       # 6. gas_rate_of_change
            ]], columns=[
                'temperature',
                'gas',
                'temp_avg_5min',
                'gas_avg_5min',
                'temp_rate_of_change',
                'gas_rate_of_change'
            ])
            
            # Get prediction (0=SAFE, 1=CAUTION, 2=DANGER)
            prediction = self.model.predict(features)[0]
            
            # Get prediction probabilities
            try:
                probabilities = self.model.predict_proba(features)[0]
                confidence = max(probabilities) * 100
            except:
                confidence = 0
            
            # Predict future values (based on rate of change)
            predicted_co = co_level + (gas_rate_of_change * 3)  # 3x the current rate
            predicted_temp = temperature + (temp_rate_of_change * 3)
            
            # Map numeric prediction to risk level
            risk_level_map = {
                0: 'normal',   # SAFE
                1: 'warning',  # CAUTION
                2: 'critical'  # DANGER
            }
            risk_level = risk_level_map.get(prediction, 'normal')
            
            return {
                'predicted_co': max(0, predicted_co),  # Don't predict negative values
                'predicted_temp': max(0, predicted_temp),
                'risk_level': risk_level,
                'model_used': f'ML Model (RandomForest) - {confidence:.1f}% confidence',
                'raw_prediction': int(prediction),
                'temp_rate': temp_rate_of_change,
                'gas_rate': gas_rate_of_change
            }
            
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_prediction(co_level, temperature)
    
    def _fallback_prediction(self, co_level, temperature):
        """Rule-based fallback when ML model is unavailable"""
        predicted_co = co_level + (co_level * 0.15)
        predicted_temp = temperature + (temperature * 0.08)
        
        # Determine risk level
        if co_level > 50 or temperature > 35:
            risk_level = 'critical'
        elif co_level > 30 or temperature > 30:
            risk_level = 'warning'
        else:
            risk_level = 'normal'
        
        return {
            'predicted_co': predicted_co,
            'predicted_temp': predicted_temp,
            'risk_level': risk_level,
            'model_used': 'Rule-based (Fallback)',
            'raw_prediction': 2 if risk_level == 'critical' else 1 if risk_level == 'warning' else 0
        }
    
    def reset_history(self):
        """Reset the history buffers (useful for new monitoring sessions)"""
        self.temp_history.clear()
        self.gas_history.clear()


# Initialize predictor instance
predictor = RiskPredictor()