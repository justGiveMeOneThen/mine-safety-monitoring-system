import json
import threading
import serial
import serial.tools.list_ports
from datetime import datetime, timedelta
from collections import deque
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import SensorReading, Sector

# Import your ML predictor and alert system
try:
    from .ml_predictor import predictor
    ML_AVAILABLE = True
except Exception as e:
    print(f"ML predictor not available: {e}")
    ML_AVAILABLE = False

try:
    from .alerts import alert_system
    ALERTS_AVAILABLE = True
except Exception as e:
    print(f"Alert system not available: {e}")
    ALERTS_AVAILABLE = False


# ============================================================
# DATABASE HELPER
# ============================================================

def _save_to_database(reading_dict):  # sourcery skip: extract-method
    """
    Save sensor reading to PostgreSQL database.
    """
    try:
        # Get or create the sector
        sector, created = Sector.objects.get_or_create(
            name=reading_dict["sector"],
            defaults={"description": "Auto-created from sensor data"}
        )
        
        if created:
            print(f"✅ Created new sector: {sector.name}")
        
        # Create sensor reading
        SensorReading.objects.create(
            sector=sector,
            carbon_monoxide=reading_dict["carbon_monoxide"],
            temperature=reading_dict["temperature"],
        )
        
        # Optional: Clean old data (keep only last 7 days)
        cutoff = timezone.now() - timedelta(days=7)
        deleted_count, _ = SensorReading.objects.filter(timestamp__lt=cutoff).delete()
        
        if deleted_count > 0:
            print(f"🗑️ Cleaned {deleted_count} old readings")
            
    except Exception as e:
        print(f"❌ Database save error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# SERIAL READER - Runs in background thread
# ============================================================

class SerialDataManager:
    SERIAL_PORT = "COM9"
    BAUD_RATE   = 115200
    TIMEOUT     = 3

    MAX_HISTORY = 17280  # 24 hours at 5s intervals

    def __init__(self):
        self.latest_reading = None
        self.history        = deque(maxlen=self.MAX_HISTORY)
        self.lock           = threading.Lock()
        self.running        = False
        self.serial_conn    = None
        self._thread        = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        print(f"✅ Serial reader started on {self.SERIAL_PORT}")

    def stop(self):
        self.running = False
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass

    def get_latest(self):
        with self.lock:
            return self.latest_reading.copy() if self.latest_reading else None

    def get_history(self):
        with self.lock:
            return list(self.history)

    def _read_loop(self):
        while self.running:
            try:
                self._connect()
                while self.running:
                    line = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{") and line.endswith("}"):
                        self._parse_and_store(line)
            except serial.SerialException as e:
                print(f"Serial error: {e}. Retrying in 5s…")
                self._safe_close()
                threading.Event().wait(5)
            except Exception as e:
                print(f"Unexpected serial error: {e}")
                self._safe_close()
                threading.Event().wait(5)

    def _connect(self):
        self._safe_close()
        self.serial_conn = serial.Serial(
            port=self.SERIAL_PORT,
            baudrate=self.BAUD_RATE,
            timeout=self.TIMEOUT,
        )
        print(f"Connected to {self.SERIAL_PORT}")

    def _safe_close(self):
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

    def _parse_and_store(self, raw_json: str):
        try:
            data = json.loads(raw_json)

            reading = {
                "sector":          data.get("sector", "Sector 1"),
                "temperature":     float(data.get("temperature", 0)),
                "carbon_monoxide": float(data.get("carbon_monoxide", 0)),
                "timestamp":       datetime.now().isoformat(),
                "isActive":        True,
            }

            with self.lock:
                self.latest_reading = reading
                self.history.append({
                    "timestamp":      reading["timestamp"],
                    "carbonMonoxide": reading["carbon_monoxide"],
                    "temperature":    reading["temperature"],
                })

            # ✨ Save to database
            _save_to_database(reading)

            # Trigger async ML alert check
            _check_and_alert(reading)

        except (json.JSONDecodeError, ValueError) as e:
            pass


# Singleton manager + auto-start
serial_manager = SerialDataManager()
serial_manager.start()


# ============================================================
# ALERT HELPER
# ============================================================

def _check_and_alert(reading):
    if not (ML_AVAILABLE and ALERTS_AVAILABLE):
        return

    co   = reading["carbon_monoxide"]
    temp = reading["temperature"]

    try:
        result = predictor.predict_risk(co, temp)
        risk   = result.get("risk_level", "normal")

        if risk in ("warning", "critical"):
            if co > 30:
                alert_system.send_prediction_alert(
                    prediction_data={
                        "severity":       risk,
                        "gasType":        "Carbon Monoxide",
                        "currentLevel":   co,
                        "predictedLevel": result.get("predicted_co", co),
                        "timeToReach":    15 if risk == "critical" else 30,
                        "recommendation": (
                            "EVACUATE immediately. Contact mine safety team."
                            if risk == "critical"
                            else "Increase ventilation. Monitor closely."
                        ),
                    },
                    sector_name=reading["sector"],
                )

            if temp > 28:
                alert_system.send_prediction_alert(
                    prediction_data={
                        "severity":       risk,
                        "gasType":        "Temperature",
                        "currentLevel":   temp,
                        "predictedLevel": result.get("predicted_temp", temp),
                        "timeToReach":    15 if risk == "critical" else 30,
                        "recommendation": (
                            "EVACUATE immediately. Dangerously high temperature."
                            if risk == "critical"
                            else "Check cooling systems. Alert workers."
                        ),
                    },
                    sector_name=reading["sector"],
                )

    except Exception as e:
        print(f"Alert check error: {e}")


# ============================================================
# DEMO / FALLBACK DATA
# ============================================================

def _demo_sensor():
    import math, time
    t = time.time()
    return {
        "sector":          "Sector 1",
        "temperature":     round(25.0 + 3 * math.sin(t / 60), 2),
        "carbon_monoxide": round(20.0 + 10 * math.sin(t / 45), 1),
        "timestamp":       datetime.now().isoformat(),
        "isActive":        True,
    }


def _demo_history(hours=24):
    import math, random
    history = []
    now = datetime.now()
    points = hours * 12

    for i in range(points):
        ts = now - timedelta(minutes=(points - i) * 5)
        history.append({
            "timestamp":      ts.isoformat(),
            "carbonMonoxide": round(20 + 10 * math.sin(i / 30) + random.uniform(-2, 2), 1),
            "temperature":    round(26 + 4 * math.sin(i / 20) + random.uniform(-1, 1), 2),
        })
    return history


# ============================================================
# PAGE VIEWS
# ============================================================

@login_required
def home(request):
    return redirect("monitoring:dashboard")


@login_required
def dashboard(request):
    return render(request, "monitoring/dashboard.html")


@login_required
def analytics(request):
    return render(request, "monitoring/analytics.html")


# ============================================================
# API ENDPOINTS
# ============================================================

@login_required
@require_http_methods(["GET"])
def get_sensor_data(request):
    reading = serial_manager.get_latest() or _demo_sensor()
    
    sectors = []
    for i in range(1, 7):
        if i == 1:
            sectors.append({
                "sector":          reading["sector"],
                "carbonMonoxide":  reading["carbon_monoxide"],
                "temperature":     reading["temperature"],
                "timestamp":       reading["timestamp"],
                "isActive":        True,
            })
        else:
            sectors.append({
                "sector":          f"Sector {i}",
                "carbonMonoxide":  0,
                "temperature":     0,
                "timestamp":       datetime.now().isoformat(),
                "isActive":        False,
            })

    return JsonResponse({
        "sensors":   sectors,
        "timestamp": datetime.now().isoformat(),
    })


@login_required
@require_http_methods(["GET"])
def get_predictions(request):
    reading = serial_manager.get_latest() or _demo_sensor()
    co      = reading["carbon_monoxide"]
    temp    = reading["temperature"]
    sector  = reading["sector"]

    if ML_AVAILABLE:
        try:
            result     = predictor.predict_risk(co, temp)
            risk       = result.get("risk_level", "normal")
            pred_co    = result.get("predicted_co", co * 1.15)
            pred_temp  = result.get("predicted_temp", temp * 1.08)
            model_used = result.get("model_used", "ML Model")
        except Exception as e:
            print(f"⚠️ Prediction error: {e}")
            import traceback
            traceback.print_exc()
            risk      = "normal"
            pred_co   = co * 1.15
            pred_temp  = temp * 1.08
            model_used = "Rule-based (Fallback)"
    else:
        if co > 50 or temp > 35:
            risk = "critical"
        elif co > 30 or temp > 30:
            risk = "warning"
        else:
            risk = "normal"
        pred_co    = co * 1.15
        pred_temp  = temp * 1.08
        model_used = "Rule-based (Fallback)"

    predictions = []

    # CO Prediction (always show if any CO detected)
    if co >= 0:
        co_severity = "critical" if co > 50 else "warning" if co > 30 else "normal"
        predictions.append({
            "sector":         sector,
            "gasType":        "Carbon Monoxide",
            "severity":       co_severity,
            "currentLevel":   round(co, 2),
            "predictedLevel": round(pred_co, 2),
            "timeToReach":    10 if co_severity == "critical" else 20 if co_severity == "warning" else 30,
            "recommendation": (
                "EVACUATE IMMEDIATELY. CO levels dangerously high."
                if co_severity == "critical"
                else "Increase ventilation. Alert workers. Monitor closely."
                if co_severity == "warning"
                else "CO levels normal. Continue monitoring."
            ),
            "modelUsed": model_used,
        })

    # Temperature Prediction (always show)
    temp_severity = "critical" if temp > 40 else "warning" if temp > 30 else "normal"
    predictions.append({
        "sector":         sector,
        "gasType":        "Temperature",
        "severity":       temp_severity,
        "currentLevel":   round(temp, 2),
        "predictedLevel": round(pred_temp, 2),
        "timeToReach":    15 if temp_severity == "critical" else 25 if temp_severity == "warning" else 35,
        "recommendation": (
            "EVACUATE IMMEDIATELY. Temperature critically high."
            if temp_severity == "critical"
            else "Check cooling systems. Reduce worker exposure."
            if temp_severity == "warning"
            else "Temperature normal. Continue monitoring."
        ),
        "modelUsed": model_used,
    })

    return JsonResponse({
        "predictions": predictions,
        "riskLevel":   risk,
        "modelUsed":   model_used,
        "timestamp":   datetime.now().isoformat(),
    })


@login_required
@require_http_methods(["GET"])
def get_historical_data(request):
    history = serial_manager.get_history()

    if not history:
        history = _demo_history(hours=24)

    return JsonResponse({
        "historicalData": history,
        "count":          len(history),
        "timestamp":      datetime.now().isoformat(),
    })


@login_required
@require_http_methods(["GET"])
def serial_status(request):
    connected = (
        serial_manager.serial_conn is not None
        and serial_manager.serial_conn.is_open
    )
    return JsonResponse({
        "port":           serial_manager.SERIAL_PORT,
        "connected":      connected,
        "history_points": len(serial_manager.get_history()),
        "latest":         serial_manager.get_latest(),
    })