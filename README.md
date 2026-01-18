# 🚨 Mine Safety Monitoring System

Real-time mine safety monitoring system with ESP32 IoT sensors, Django backend, and AI-powered risk predictions.

## 🎯 Features

- **Real-time Monitoring**: Live sensor data from ESP32 (MQ2 gas sensor + LM35 temperature sensor)
- **AI Predictions**: Machine learning-powered risk forecasting using scikit-learn
- **Historical Analytics**: Interactive charts with 24-hour trend analysis
- **Professional Dashboard**: Modern UI with Tailwind CSS
- **Admin Panel**: Complete management interface

## 🛠️ Tech Stack

- **Backend**: Django 4.2
- **IoT Hardware**: ESP32 + MQ2 (CO sensor) + LM35 (Temperature sensor)
- **Machine Learning**: Scikit-learn, Joblib, NumPy
- **Frontend**: HTML5, Tailwind CSS, Chart.js
- **Communication**: PySerial (USB serial)

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/justGiveMeOneThen/mine-safety-monitoring-system.git
cd mine-safety-monitoring-system
```

2. Create virtual environment:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Run development server:
```bash
python manage.py runserver
```

## 🌐 Access Points

- **Home**: http://127.0.0.1:8000/
- **Dashboard**: http://127.0.0.1:8000/dashboard/
- **Analytics**: http://127.0.0.1:8000/analytics/
- **Admin**: http://127.0.0.1:8000/admin/

## 📊 System Architecture
```
ESP32 + Sensors → Serial USB → Django Backend → Web Dashboard
                                      ↓
                                 ML Model (risk_model.joblib)
                                      ↓
                              Real-time Predictions
```

## 🔬 Current Status

- ✅ Django backend fully functional
- ✅ ML model integration ready
- ✅ Professional UI/UX complete
- ⏳ ESP32 IoT hardware setup pending (currently uses mock data)

## 📸 Screenshots

_Add screenshots of your dashboard here_

## 👨‍💻 Author

Your Name - [Simbanai](https://github.com/justGiveMeOneThen)

## 📄 License

This project is for educational purposes.