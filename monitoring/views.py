# monitoring/views.py - COMPLETE VERSION

from django.shortcuts import render
from django.http import JsonResponse
from datetime import datetime, timedelta
import random
from .ml_predictor import predictor

def home(request):
    """Redirect to dashboard"""
    return render(request, 'monitoring/home.html')

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
        
        predictions.append({
            'id': 'pred-co',
            'sector': 'Sector 1',
            'gasType': 'Carbon Monoxide',
            'currentLevel': round(current_co, 2),
            'predictedLevel': round(prediction_result['predicted_co'], 2),
            'timeToReach': time_to_reach,
            'severity': severity,
            'recommendation': 'Critical CO levels predicted. Evacuate personnel immediately.' if severity == 'critical' else 'Elevated CO detected. Check ventilation system.',
            'timestamp': datetime.now().isoformat()
        })
    
    # Temperature Prediction
    if current_temp > 28:
        time_to_reach = random.randint(20, 60)
        severity = 'critical' if prediction_result['predicted_temp'] > 35 else 'warning'
        
        predictions.append({
            'id': 'pred-temp',
            'sector': 'Sector 1',
            'gasType': 'Temperature',
            'currentLevel': round(current_temp, 2),
            'predictedLevel': round(prediction_result['predicted_temp'], 2),
            'timeToReach': time_to_reach,
            'severity': severity,
            'recommendation': 'Extreme temperature predicted. Implement cooling protocols.' if severity == 'critical' else 'Rising temperature. Monitor closely.',
            'timestamp': datetime.now().isoformat()
        })
    
    return JsonResponse({
        'predictions': predictions,
        'modelInfo': {
            'modelUsed': prediction_result['model_used'],
            'riskLevel': prediction_result['risk_level']
        }
    })

def get_historical_data(request):
    """
    API endpoint for historical data (24 hours)
    NOTE: Currently generates MOCK DATA
    In production: Will query database of ESP32 readings
    """
    hours = 24
    now = datetime.now()
    
    # Generate historical data points
    historical_data = []
    for i in range(hours):
        timestamp = now - timedelta(hours=hours-i)
        
        # Simulate realistic patterns
        base_co = 25 + (i % 6) * 3
        base_temp = 26 + (i % 4) * 1.5
        
        historical_data.append({
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'carbonMonoxide': round(base_co + random.uniform(-2, 2), 2),
            'temperature': round(base_temp + random.uniform(-1, 1), 2),
            'sector': 'Sector 1'
        })
    
    return JsonResponse({'historicalData': historical_data})