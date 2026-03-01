import time
import json
import serial
import requests # type: ignore
import statistics
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
SERIAL_PORT   = "COM9"
BAUD_RATE     = 115200
BASE_URL      = "http://127.0.0.1:8000"
NUM_SAMPLES   = 20       # number of readings to average
SESSION_COOKIE = None    # filled automatically after login

# ── Helpers ───────────────────────────────────────────────────────────────────

def login():
    """Log into Django and return an authenticated session."""
    session = requests.Session()
    # Get CSRF token
    r = session.get(f"{BASE_URL}/accounts/login/")
    csrf = session.cookies.get("csrftoken", "")
    session.post(f"{BASE_URL}/accounts/login/", data={
        "username":     "admin",      # ← change to your superuser username
        "password":     "admin",      # ← change to your superuser password
        "csrfmiddlewaretoken": csrf,
        "next": "/dashboard/"
    })
    return session


def separator(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


def result(label, value_ms, unit="ms"):
    if unit == "ms":
        print(f"  {label:<40} {value_ms:.2f} ms  ({value_ms/1000:.4f} s)")
    else:
        print(f"  {label:<40} {value_ms:.4f} s  ({value_ms*1000:.2f} ms)")


# ── TEST 1: Hardware Processing Latency ───────────────────────────────────────
# Measures: time from when ESP32 starts sending to when Python receives full line
# This captures USB transmission + OS buffering + PySerial decode

def test_hardware_processing_latency():
    separator("1. HARDWARE PROCESSING LATENCY")
    print("  Connecting to ESP32 on", SERIAL_PORT, "...")

    timings = []
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5)
        print(f"  Collecting {NUM_SAMPLES} samples...\n")

        collected = 0
        while collected < NUM_SAMPLES:
            t_start = time.perf_counter()
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            t_end = time.perf_counter()

            if line.startswith("{") and line.endswith("}"):
                elapsed_ms = (t_end - t_start) * 1000
                timings.append(elapsed_ms)
                collected += 1
                print(f"  Sample {collected:02d}: {elapsed_ms:.2f} ms  → {line[:50]}")

        ser.close()

        print(f"\n  ── Results ──")
        result("Minimum latency",   min(timings))
        result("Maximum latency",   max(timings))
        result("Average latency",   statistics.mean(timings))
        result("Median latency",    statistics.median(timings))
        result("Std deviation",     statistics.stdev(timings))

        return statistics.mean(timings)

    except serial.SerialException as e:
        print(f"  ❌ Could not open {SERIAL_PORT}: {e}")
        print("  Make sure ESP32 is plugged in and Django server is NOT running")
        return None


# ── TEST 2: Transmission & Ingestion Latency ──────────────────────────────────
# Measures: time from HTTP request leaving Python to full JSON response received
# This captures: network stack + Django routing + serial_manager.get_latest()
# + JSON serialisation + HTTP response

def test_transmission_ingestion_latency(session):
    separator("2. TRANSMISSION & INGESTION LATENCY")
    print(f"  Hitting /api/sensor-data/ {NUM_SAMPLES} times...\n")

    sensor_timings = []
    prediction_timings = []
    historical_timings = []

    for i in range(NUM_SAMPLES):
        # Sensor data endpoint
        t0 = time.perf_counter()
        r = session.get(f"{BASE_URL}/api/sensor-data/")
        t1 = time.perf_counter()
        if r.status_code == 200:
            sensor_timings.append((t1 - t0) * 1000)

        # Predictions endpoint
        t0 = time.perf_counter()
        r = session.get(f"{BASE_URL}/api/predictions/")
        t1 = time.perf_counter()
        if r.status_code == 200:
            prediction_timings.append((t1 - t0) * 1000)

        # Historical data endpoint
        t0 = time.perf_counter()
        r = session.get(f"{BASE_URL}/api/historical-data/")
        t1 = time.perf_counter()
        if r.status_code == 200:
            historical_timings.append((t1 - t0) * 1000)

        print(f"  Sample {i+1:02d}: sensor={sensor_timings[-1]:.1f}ms  "
              f"predictions={prediction_timings[-1]:.1f}ms  "
              f"historical={historical_timings[-1]:.1f}ms")

        time.sleep(0.2)

    print(f"\n  ── /api/sensor-data/ ──")
    result("Average response time", statistics.mean(sensor_timings))
    result("Min response time",     min(sensor_timings))
    result("Max response time",     max(sensor_timings))

    print(f"\n  ── /api/predictions/ ──")
    result("Average response time", statistics.mean(prediction_timings))
    result("Min response time",     min(prediction_timings))
    result("Max response time",     max(prediction_timings))

    print(f"\n  ── /api/historical-data/ ──")
    result("Average response time", statistics.mean(historical_timings))
    result("Min response time",     min(historical_timings))
    result("Max response time",     max(historical_timings))

    return statistics.mean(sensor_timings)


# ── TEST 3: Dashboard Refresh Rate ────────────────────────────────────────────
# Measures: actual observed refresh cycle time
# (how long a complete poll cycle takes including both API calls)

def test_dashboard_refresh_rate(session):
    separator("3. DASHBOARD REFRESH RATE")
    print(f"  Simulating {NUM_SAMPLES} dashboard poll cycles...\n")

    cycle_timings = []

    for i in range(NUM_SAMPLES):
        t_start = time.perf_counter()

        # Dashboard makes 2 calls per cycle
        session.get(f"{BASE_URL}/api/sensor-data/")
        session.get(f"{BASE_URL}/api/predictions/")

        t_end = time.perf_counter()
        cycle_ms = (t_end - t_start) * 1000
        cycle_timings.append(cycle_ms)

        print(f"  Cycle {i+1:02d}: {cycle_ms:.2f} ms total")
        time.sleep(0.1)

    avg = statistics.mean(cycle_timings)
    configured_interval = 5000  # 5 seconds as set in dashboard.html

    print(f"\n  ── Results ──")
    result("Average cycle time",          avg)
    result("Configured refresh interval", configured_interval)
    result("Overhead per cycle",          configured_interval - avg)
    print(f"\n  Effective refresh rate:  {1000/avg:.1f} polls/second (theoretical max)")
    print(f"  Configured refresh rate: 1 poll every 5 seconds (0.2 polls/second)")

    return avg


# ── TEST 4: Maximum End-to-End Latency ────────────────────────────────────────
# Measures: worst-case total time from sensor reading to dashboard update
# = Hardware processing + Ingestion + JS poll interval

def test_maximum_latency(hw_latency_ms, ingestion_ms, refresh_interval_ms=5000):
    separator("4. MAXIMUM END-TO-END LATENCY")

    if hw_latency_ms is None:
        hw_latency_ms = 50  # estimate if serial test was skipped
        print("  ⚠️  Using estimated hardware latency (50ms) — run with ESP32 connected for real value")

    # Worst case: sensor data arrives just AFTER a dashboard poll
    # So it has to wait the full 5s interval before being shown
    max_latency_ms = hw_latency_ms + ingestion_ms + refresh_interval_ms

    print(f"\n  ── Breakdown ──")
    result("Hardware processing",          hw_latency_ms)
    result("API ingestion (avg)",          ingestion_ms)
    result("Max poll wait (refresh rate)", refresh_interval_ms)
    print(f"  {'─'*55}")
    result("MAXIMUM END-TO-END LATENCY",  max_latency_ms)

    print(f"\n  ── Interpretation ──")
    if max_latency_ms < 6000:
        print("  ✅ EXCELLENT — Under 6 seconds total latency")
    elif max_latency_ms < 10000:
        print("  ✅ GOOD — Under 10 seconds, acceptable for safety monitoring")
    else:
        print("  ⚠️  REVIEW — Consider reducing refresh interval")

    return max_latency_ms


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "█"*60)
    print("  MINE SAFETY SYSTEM — LATENCY EVALUATION")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)

    print("\n⚠️  IMPORTANT: Make sure Django server is running in another terminal")
    print("   Run: python manage.py runserver")
    print("   Then run this script in a separate terminal\n")

    # Test 1 — requires ESP32 plugged in, Django NOT running (COM9 must be free)
    # Comment out if you want to test with Django running
    hw_ms = test_hardware_processing_latency()

    # Tests 2-4 — requires Django server running
    session = login()
    ingestion_ms = test_transmission_ingestion_latency(session)
    refresh_ms   = test_dashboard_refresh_rate(session)
    max_ms       = test_maximum_latency(hw_ms, ingestion_ms)

    separator("FINAL SUMMARY")
    print(f"  Hardware Processing:      {hw_ms:.2f} ms" if hw_ms else "  Hardware Processing:      skipped")
    print(f"  Transmission/Ingestion:   {ingestion_ms:.2f} ms")
    print(f"  Dashboard Refresh Cycle:  {refresh_ms:.2f} ms")
    print(f"  Maximum E2E Latency:      {max_ms:.2f} ms  ({max_ms/1000:.2f} s)")
    print(f"\n  Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60 + "\n")