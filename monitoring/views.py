from django.shortcuts import render
from django.http import JsonResponse
from datetime import datetime, timedelta
import random
from .ml_predictor import predictor
from django.contrib.auth.decorators import login_required
from .alerts import alert_system

@login_required
def dashboard(request):
    return render(request, 'monitoring/dashboard.html')

def home(request):
    """Redirect to dashboard"""
    return render(request, 'registration/login.html')

def dashboard(request):
    """Main dashboard view"""
    return render(request, 'monitoring/dashboard.html')

def analytics(request):
    """Analytics page view"""
    return render(request, 'monitoring/analytics.html')

def get_sensor_data(request):
    """
    API endpoint for sensor data
    NOTE: Currently returns MOCK DATA
    In production: Will read from ESP32 via serial port
    
    Future Integration:
    import serial
    ser = serial.Serial('/dev/ttyUSB0', 9600)
    data = ser.readline().decode('utf-8').strip()
    """
    # MOCK DATA - Replace with serial.read() from ESP32
    sensors = []
    for i in range(1, 7):
        sensor_data = {
            'id': f'sensor-{i}',
            'sector': f'Sector {i}',
            'carbonMonoxide': round(random.uniform(15, 45), 2) if i == 1 else 0,
            'temperature': round(random.uniform(22, 33), 2) if i == 1 else 0,
            'timestamp': datetime.now().isoformat(),
            'isActive': i == 1  # Only Sector 1 active in demo
        }
        sensors.append(sensor_data)
    
    return JsonResponse({'sensors': sensors})

def get_predictions(request):
    """
    API endpoint for AI predictions using risk_model.joblib
    NOW WITH INTELLIGENT EMAIL ALERTS
    """
    predictions = []
    
    # Get current sensor data (mock)
    current_co = random.uniform(30, 45)
    current_temp = random.uniform(28, 33)
    
    # Use ML model for prediction
    prediction_result = predictor.predict_risk(current_co, current_temp)
    
    # CO Prediction
    if current_co > 30:
        time_to_reach = random.randint(10, 40)
        severity = 'critical' if prediction_result['predicted_co'] > 50 else 'warning'
        
        prediction_data = {
            'id': 'pred-co',
            'sector': 'Sector 1',
            'gasType': 'Carbon Monoxide',
            'currentLevel': round(current_co, 2),
            'predictedLevel': round(prediction_result['predicted_co'], 2),
            'timeToReach': time_to_reach,
            'severity': severity,
            'recommendation': 'Critical CO levels predicted. Evacuate personnel immediately.' if severity == 'critical' else 'Elevated CO detected. Check ventilation system.',
            'timestamp': datetime.now().isoformat()
        }
        
        predictions.append(prediction_data)
        
        # 🚨 SEND PREDICTIVE EMAIL ALERT
        # Only send if it's a critical prediction or warning with short time
        if severity == 'critical' or (severity == 'warning' and time_to_reach <= 15):
            alert_system.send_prediction_alert(prediction_data, 'Sector 1')
    
    # Temperature Prediction
    if current_temp > 28:
        time_to_reach = random.randint(20, 60)
        severity = 'critical' if prediction_result['predicted_temp'] > 35 else 'warning'
        
        prediction_data = {
            'id': 'pred-temp',
            'sector': 'Sector 1',
            'gasType': 'Temperature',
            'currentLevel': round(current_temp, 2),
            'predictedLevel': round(prediction_result['predicted_temp'], 2),
            'timeToReach': time_to_reach,
            'severity': severity,
            'recommendation': 'Extreme temperature predicted. Implement cooling protocols.' if severity == 'critical' else 'Rising temperature. Monitor closely.',
            'timestamp': datetime.now().isoformat()
        }
        
        predictions.append(prediction_data)
        
        # 🚨 SEND PREDICTIVE EMAIL ALERT
        if severity == 'critical' or (severity == 'warning' and time_to_reach <= 20):
            alert_system.send_prediction_alert(prediction_data, 'Sector 1')
    
    return JsonResponse({
        'predictions': predictions,
        'modelInfo': {
            'modelUsed': prediction_result['model_used'],
            'riskLevel': prediction_result['risk_level']
        }
    })

# get_historical_data
def get_historical_data(request):
    now = datetime.now()
    historical = []

    # Generate from OLDEST to NEWEST (0h → 23h ago becomes 23h ago → now)
    for hour in range(24):
        # Go backwards: 23h ago, 22h ago, ..., now
        timestamp = now - timedelta(hours=23 - hour)
        co = round(random.uniform(10, 50), 2)
        temp = round(random.uniform(20, 36), 2)
        historical.append({
            'timestamp': timestamp.isoformat(),
            'carbonMonoxide': co,
            'temperature': temp
        })

    return JsonResponse({'historicalData': historical})  # Note: key must match frontend!