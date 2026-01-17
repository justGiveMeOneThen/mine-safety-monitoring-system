# monitoring/ml_predictor.py

import joblib
import numpy as np
from django.conf import settings
import os

class RiskPredictor:
    def __init__(self):
        self.model = None
        self.load_model()
    
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
        """
        if self.model is None:
            # Fallback: Rule-based prediction
            return self._fallback_prediction(co_level, temperature)
        
        try:
            # Prepare input features (adjust based on your model's training)
            features = np.array([[co_level, temperature]])
            
            # Get prediction
            prediction = self.model.predict(features)[0]
            
            # Predict future values (simple linear extrapolation)
            predicted_co = co_level + (co_level * 0.15)  # 15% increase
            predicted_temp = temperature + (temperature * 0.08)  # 8% increase
            
            return {
                'predicted_co': predicted_co,
                'predicted_temp': predicted_temp,
                'risk_level': prediction,
                'model_used': 'ML Model'
            }
        except Exception as e:
            print(f"Prediction error: {e}")
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
            'model_used': 'Rule-based (Fallback)'
        }


# Initialize predictor instance - THIS WAS MISSING!
predictor = RiskPredictor()