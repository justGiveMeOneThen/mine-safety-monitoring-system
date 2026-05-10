import json
import threading
import serial
import serial.tools.list_ports
from datetime import datetime, timedelta
from collections import deque, defaultdict
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import SensorReading, Sector, Prediction, Alert

# ── Prediction save cooldown ───────────────────────────────────
# Saves only when risk level changes OR every 5 minutes
_last_prediction_save = defaultdict(lambda: {'time': None, 'risk': None})
PREDICTION_SAVE_COOLDOWN = 300  # seconds

# ── ML predictor ───────────────────────────────────────────────
try:
    from .ml_predictor import predictor
    ML_AVAILABLE = True
except Exception as e:
    print(f"ML predictor not available: {e}")
    ML_AVAILABLE = False

# ── Alert system ───────────────────────────────────────────────
try:
    from .alerts import alert_system
    ALERTS_AVAILABLE = True
except Exception as e:
    print(f"Alert system not available: {e}")
    ALERTS_AVAILABLE = False


# ============================================================
# DATABASE HELPER
# ============================================================

def _save_to_database(reading_dict):
    """Save sensor reading to PostgreSQL database."""
    try:
        sector, created = Sector.objects.get_or_create(
            name=reading_dict["sector"],
            defaults={"description": "Auto-created from sensor data"}
        )
        if created:
            print(f"✅ Created new sector: {sector.name}")

        SensorReading.objects.create(
            sector=sector,
            carbon_monoxide=reading_dict["carbon_monoxide"],
            temperature=reading_dict["temperature"],
        )

        # Keep only last 7 days
        cutoff = timezone.now() - timedelta(days=7)
        deleted_count, _ = SensorReading.objects.filter(timestamp__lt=cutoff).delete()
        if deleted_count > 0:
            print(f"🗑️ Cleaned {deleted_count} old readings")

    except Exception as e:
        print(f"❌ Database save error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# SERIAL READER — Runs in background thread
# ============================================================

class SerialDataManager:
    SERIAL_PORT = "COM9"
    BAUD_RATE   = 115200
    TIMEOUT     = 3
    MAX_HISTORY = 17280  # 24h at 5s intervals

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

            _save_to_database(reading)
            _check_and_alert(reading)

        except (json.JSONDecodeError, ValueError):
            pass


# Singleton — auto-start on import
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
            # MSHA thresholds: CO warning >35, critical >100
            if co > 35:
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

            # MSHA thresholds: Temp warning >26, critical >35
            if temp > 26:
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
    reading      = serial_manager.get_latest()
    is_connected = (
        serial_manager.serial_conn is not None
        and serial_manager.serial_conn.is_open
    )

    if not is_connected or reading is None:
        sectors = [
            {
                "sector":          f"Sector {i}",
                "carbonMonoxide":  0,
                "temperature":     0,
                "timestamp":       datetime.now().isoformat(),
                "isActive":        False,
            }
            for i in range(1, 7)
        ]
        return JsonResponse({
            "sensors":       sectors,
            "timestamp":     datetime.now().isoformat(),
            "system_online": False,
        })

    sectors = []
    for i in range(1, 7):
        if i == 1:
            sectors.append({
                "sector":         reading["sector"],
                "carbonMonoxide": reading["carbon_monoxide"],
                "temperature":    reading["temperature"],
                "timestamp":      reading["timestamp"],
                "isActive":       True,
            })
        else:
            sectors.append({
                "sector":         f"Sector {i}",
                "carbonMonoxide": 0,
                "temperature":    0,
                "timestamp":      datetime.now().isoformat(),
                "isActive":       False,
            })

    return JsonResponse({
        "sensors":       sectors,
        "timestamp":     datetime.now().isoformat(),
        "system_online": True,
    })


@login_required
@require_http_methods(["GET"])
def get_predictions(request):
    is_connected = (
        serial_manager.serial_conn is not None
        and serial_manager.serial_conn.is_open
    )
    reading = serial_manager.get_latest()

    # ── Offline response — includes mlMeta: None so frontend doesn't crash ──
    if not is_connected or reading is None:
        return JsonResponse({
            "predictions":   [],
            "riskLevel":     "offline",
            "modelUsed":     "N/A",
            "mlMeta":        None,          # ← critical: prevents JS crash
            "timestamp":     datetime.now().isoformat(),
            "system_online": False,
        })

    co          = reading["carbon_monoxide"]
    temp        = reading["temperature"]
    sector_name = reading["sector"]

    # ── Run ML prediction ──────────────────────────────────────
    if ML_AVAILABLE:
        try:
            result = predictor.predict_risk(co, temp)
        except Exception as e:
            print(f"⚠️ Prediction error: {e}")
            result = {
                'risk_level':    'normal',
                'confidence':    None,
                'prob_normal':   None,
                'prob_warning':  None,
                'prob_critical': None,
                'ci_lower':      None,
                'ci_upper':      None,
                'predicted_co':  co * 1.15,
                'predicted_temp': temp * 1.08,
                'model_used':    'Rule-based (Fallback)',
            }
    else:
        risk = (
            'critical' if (co > 100 or temp > 35)
            else 'warning' if (co > 35 or temp > 26)
            else 'normal'
        )
        result = {
            'risk_level':    risk,
            'confidence':    None,
            'prob_normal':   None,
            'prob_warning':  None,
            'prob_critical': None,
            'ci_lower':      None,
            'ci_upper':      None,
            'predicted_co':  co * 1.15,
            'predicted_temp': temp * 1.08,
            'model_used':    'Rule-based (Fallback)',
        }

    risk       = result['risk_level']
    pred_co    = result['predicted_co']
    pred_temp  = result['predicted_temp']
    model_used = result['model_used']

    # ── Shared ML metadata ─────────────────────────────────────
    ml_meta = {
        "modelUsed":    model_used,
        "confidence":   result.get('confidence'),
        "ciLower":      result.get('ci_lower'),
        "ciUpper":      result.get('ci_upper'),
        "probNormal":   result.get('prob_normal'),
        "probWarning":  result.get('prob_warning'),
        "probCritical": result.get('prob_critical'),
    }

    # ── Build predictions list ─────────────────────────────────
    predictions = []

    # CO — MSHA thresholds
    co_severity = 'critical' if co > 100 else 'warning' if co > 35 else 'normal'
    co_rec = (
        "EVACUATE IMMEDIATELY. CO levels dangerously high."
        if co_severity == 'critical'
        else "Increase ventilation. Alert workers. Monitor closely."
        if co_severity == 'warning'
        else "CO levels normal. Continue monitoring."
    )
    predictions.append({
        "sector":         sector_name,
        "gasType":        "Carbon Monoxide",
        "severity":       co_severity,
        "currentLevel":   round(co, 2),
        "predictedLevel": round(pred_co, 2),
        "timeToReach":    10 if co_severity == 'critical' else 20 if co_severity == 'warning' else 30,
        "recommendation": co_rec,
        **ml_meta,
    })

    # Temperature — MSHA thresholds
    temp_severity = 'critical' if temp > 35 else 'warning' if temp > 26 else 'normal'
    temp_rec = (
        "EVACUATE IMMEDIATELY. Temperature critically high."
        if temp_severity == 'critical'
        else "Check cooling systems. Reduce worker exposure."
        if temp_severity == 'warning'
        else "Temperature normal. Continue monitoring."
    )
    predictions.append({
        "sector":         sector_name,
        "gasType":        "Temperature",
        "severity":       temp_severity,
        "currentLevel":   round(temp, 2),
        "predictedLevel": round(pred_temp, 2),
        "timeToReach":    15 if temp_severity == 'critical' else 25 if temp_severity == 'warning' else 35,
        "recommendation": temp_rec,
        **ml_meta,
    })

    # ── Save to Prediction model with cooldown ─────────────────
    try:
        sector_obj, _ = Sector.objects.get_or_create(
            name=sector_name,
            defaults={"description": "Auto-created"}
        )

        now   = datetime.now()
        state = _last_prediction_save[sector_name]
        time_since_last = (
            (now - state['time']).total_seconds()
            if state['time'] else None
        )

        risk_changed    = state['risk'] != risk
        cooldown_passed = (
            time_since_last is None
            or time_since_last >= PREDICTION_SAVE_COOLDOWN
        )

        if risk_changed or cooldown_passed:
            for pred in predictions:
                Prediction.objects.create(
                    sector=sector_obj,
                    prediction_type=pred["gasType"],
                    current_level=pred["currentLevel"],
                    predicted_level=pred["predictedLevel"],
                    time_to_reach=pred["timeToReach"],
                    severity=pred["severity"],
                    recommendation=pred["recommendation"],
                    model_used=model_used,
                )
            _last_prediction_save[sector_name] = {'time': now, 'risk': risk}
            reason = "risk changed" if risk_changed else "cooldown passed"
            print(f"💾 Prediction saved ({reason}) — risk: {risk}")

    except Exception as e:
        print(f"⚠️ Could not save prediction to DB: {e}")

    return JsonResponse({
        "predictions":   predictions,
        "riskLevel":     risk,
        "modelUsed":     model_used,
        "mlMeta":        ml_meta,
        "timestamp":     datetime.now().isoformat(),
        "system_online": True,
    })


@login_required
@require_http_methods(["GET"])
def get_historical_data(request):
    hours = min(int(request.GET.get('hours', 24)), 168)
    cutoff = timezone.now() - timedelta(hours=hours)

    readings = (
        SensorReading.objects
        .filter(timestamp__gte=cutoff)
        .order_by('timestamp')
        .values('timestamp', 'carbon_monoxide', 'temperature', 'sector__name')
    )

    history_raw = list(readings)
    total       = len(history_raw)

    # Downsample to max 500 points for chart performance
    MAX_POINTS = 500
    if total > MAX_POINTS:
        step        = total // MAX_POINTS
        history_raw = history_raw[::step]

    history = [
        {
            "timestamp":      r['timestamp'].isoformat(),
            "carbonMonoxide": round(r['carbon_monoxide'], 2),
            "temperature":    round(r['temperature'], 2),
            "sector":         r['sector__name'],
        }
        for r in history_raw
    ]

    last_reading = SensorReading.objects.order_by('-timestamp').first()
    last_seen    = last_reading.timestamp.isoformat() if last_reading else None

    from django.db.models import Max, Min, Avg
    stats = SensorReading.objects.filter(timestamp__gte=cutoff).aggregate(
        max_co=Max('carbon_monoxide'),
        min_co=Min('carbon_monoxide'),
        avg_co=Avg('carbon_monoxide'),
        max_temp=Max('temperature'),
        min_temp=Min('temperature'),
        avg_temp=Avg('temperature'),
    )

    return JsonResponse({
        "historicalData": history,
        "count":          len(history),
        "totalRaw":       total,
        "hours":          hours,
        "lastSeen":       last_seen,
        "timestamp":      timezone.now().isoformat(),
        "stats": {
            "maxCO":   round(stats['max_co']   or 0, 2),
            "minCO":   round(stats['min_co']   or 0, 2),
            "avgCO":   round(stats['avg_co']   or 0, 2),
            "maxTemp": round(stats['max_temp'] or 0, 2),
            "minTemp": round(stats['min_temp'] or 0, 2),
            "avgTemp": round(stats['avg_temp'] or 0, 2),
        },
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