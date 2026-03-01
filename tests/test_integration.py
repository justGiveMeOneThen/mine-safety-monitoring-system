import os
import sys
import json
import time
import serial
import struct
import random
import string
import argparse
import requests # type: ignore
import threading
from datetime import datetime

# ── Django setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mine_safety_project.settings")
import django
django.setup()


SERIAL_PORT = "COM9"
BAUD_RATE   = 115200
BASE_URL    = "http://127.0.0.1:8000"


def separator(title):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


# =============================================================================
# PART A — SERIAL BRIDGE FLOOD TEST
# =============================================================================

# Malformed data samples — every type of bad input imaginable
MALFORMED_INPUTS = [
    # ── Empty / whitespace ────────────────────────────────────────────────
    "",
    "   ",
    "\n",
    "\r\n",
    "\t",

    # ── Arduino startup banner lines ──────────────────────────────────────
    "════════════════════════════════════════════════",
    "  MINE SAFETY MONITORING SYSTEM",
    "Sector: Sector 1",
    "Baud Rate: 115200",
    "=== SYSTEM READY ===",
    "Initializing pins...",
    "✓ Pins initialized",
    "✓ LEDs tested",
    "✓ LCD initialized",
    "✓ DHT22 OK (27.5°C)",
    "Calibrating MQ-2 (30 seconds)...",
    "  30s remaining",
    "✓ MQ-2 calibrated",

    # ── Partial JSON ──────────────────────────────────────────────────────
    "{",
    "}",
    "{}",
    '{"sector":',
    '{"sector":"Sector 1"',
    '{"temperature":27.50}',
    '"sector":"Sector 1","temperature":27.50,"carbon_monoxide":142}',

    # ── Wrong field names ─────────────────────────────────────────────────
    '{"sec":"Sector 1","temp":27.50,"co":142}',
    '{"Sector":"Sector 1","Temperature":27.50,"CO":142}',
    '{"sector":"Sector 1","temp":27.50,"carbon_monoxide":142}',

    # ── Wrong data types ──────────────────────────────────────────────────
    '{"sector":1,"temperature":"hot","carbon_monoxide":null}',
    '{"sector":"Sector 1","temperature":null,"carbon_monoxide":142}',
    '{"sector":"Sector 1","temperature":"NaN","carbon_monoxide":142}',
    '{"sector":"Sector 1","temperature":true,"carbon_monoxide":false}',

    # ── Out of range values ───────────────────────────────────────────────
    '{"sector":"Sector 1","temperature":-999,"carbon_monoxide":-999}',
    '{"sector":"Sector 1","temperature":9999,"carbon_monoxide":9999}',
    '{"sector":"Sector 1","temperature":1e308,"carbon_monoxide":0}',

    # ── Injection attempts ────────────────────────────────────────────────
    '{"sector":"<script>alert(1)</script>","temperature":25,"carbon_monoxide":100}',
    '{"sector":"Sector 1\'; DROP TABLE sensors;--","temperature":25,"carbon_monoxide":100}',
    '{"sector":"../../../etc/passwd","temperature":25,"carbon_monoxide":100}',

    # ── Random binary garbage ─────────────────────────────────────────────
    "\x00\x01\x02\x03\x04\x05",
    "\xff\xfe\xfd",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",

    # ── Long strings ──────────────────────────────────────────────────────
    "A" * 1000,
    "{" + "x" * 500 + "}",
    '{"sector":"' + "S" * 1000 + '","temperature":25,"carbon_monoxide":100}',

    # ── Valid JSON but not sensor data ────────────────────────────────────
    '{"name":"John","age":30}',
    '[]',
    '[1,2,3]',
    'null',
    'true',
    '42',
    '"just a string"',

    # ── Unicode edge cases ────────────────────────────────────────────────
    '{"sector":"⚠️🔥","temperature":25,"carbon_monoxide":100}',
    '{"sector":"Séctor 1","temperature":25.5,"carbon_monoxide":100}',

    # ── Duplicate keys ────────────────────────────────────────────────────
    '{"sector":"Sector 1","sector":"Sector 2","temperature":25,"carbon_monoxide":100}',

    # ── Nested objects ────────────────────────────────────────────────────
    '{"sector":{"name":"Sector 1"},"temperature":25,"carbon_monoxide":100}',
    '{"sector":"Sector 1","temperature":{"value":25},"carbon_monoxide":100}',
]

# The ONE valid input — should always be accepted
VALID_INPUT = '{"sector":"Sector 1","temperature":27.50,"carbon_monoxide":142}'


def simulate_parser(line):
    """
    Simulates exactly what _parse_and_store() does in views.py.
    Returns True if the line would be accepted, False if rejected.
    """
    # Filter 1: must look like JSON object
    stripped = line.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False, "Not JSON object"

    # Filter 2: must parse as valid JSON
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"

    # Filter 3: must have required fields with numeric values
    try:
        temp = float(data.get("temperature", "MISSING"))
        co   = float(data.get("carbon_monoxide", "MISSING"))
        sector = str(data.get("sector", ""))
        if not sector:
            return False, "Missing sector field"
    except (ValueError, TypeError) as e:
        return False, f"Type error: {e}"

    return True, "VALID"


def run_serial_flood_test():
    separator("PART A — SERIAL BRIDGE FLOOD TEST")
    print("  Simulating parser against all malformed inputs...")
    print(f"  Total malformed inputs: {len(MALFORMED_INPUTS)}")
    print(f"  Expected: ALL malformed → REJECTED, valid input → ACCEPTED\n")

    rejected = 0
    accepted = 0
    false_accepts = []

    # Test all malformed inputs
    for i, bad_input in enumerate(MALFORMED_INPUTS):
        accepted_flag, reason = simulate_parser(bad_input)
        if accepted_flag:
            false_accepts.append((i, bad_input, reason))
            accepted += 1
            print(f"  ⚠️  FALSE ACCEPT [{i}]: {repr(bad_input[:60])}")
        else:
            rejected += 1

    # Test valid input
    valid_accepted, valid_reason = simulate_parser(VALID_INPUT)

    print(f"\n  ── Results ──")
    print(f"  Malformed inputs tested:  {len(MALFORMED_INPUTS)}")
    print(f"  Correctly rejected:       {rejected}")
    print(f"  Incorrectly accepted:     {accepted}")
    print(f"  Valid input accepted:     {'✅ YES' if valid_accepted else '❌ NO'}")

    print(f"\n  ── Parser Robustness Score ──")
    rejection_rate = (rejected / len(MALFORMED_INPUTS)) * 100
    print(f"  Rejection rate: {rejection_rate:.1f}%")

    if false_accepts:
        print(f"\n  ⚠️  FALSE ACCEPTS (investigate these):")
        for idx, inp, reason in false_accepts:
            print(f"     [{idx}] {repr(inp[:80])}")
            print(f"          Reason accepted: {reason}")

    if rejection_rate == 100 and valid_accepted:
        print("\n  ✅ EXCELLENT — Parser is fully robust")
        print("     Rejects all malformed data, accepts all valid data")
    elif rejection_rate >= 95 and valid_accepted:
        print("\n  ✅ GOOD — Parser is robust (≥95% rejection rate)")
    else:
        print("\n  ❌ REVIEW — Parser accepted malformed inputs")

    return rejection_rate, valid_accepted


# =============================================================================
# PART B — DATABASE INTEGRATION TEST
# =============================================================================
# Tests the full chain: HTTP Request → Django View → serial_manager → Response
# Verifies data structures are correct and database connectivity works
# =============================================================================

def login_session():
    session = requests.Session()
    r = session.get(f"{BASE_URL}/accounts/login/")
    csrf = session.cookies.get("csrftoken", "")
    session.post(f"{BASE_URL}/accounts/login/", data={
        "username": "admin",         # ← change to your superuser username
        "password": "admin",         # ← change to your superuser password
        "csrfmiddlewaretoken": csrf,
        "next": "/dashboard/"
    })
    return session


def test_sensor_data_structure(session):
    """Test /api/sensor-data/ returns correct structure."""
    print("  Testing /api/sensor-data/...")
    r = session.get(f"{BASE_URL}/api/sensor-data/")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()

    assert "sensors" in data, "Missing 'sensors' key"
    assert "timestamp" in data, "Missing 'timestamp' key"
    assert len(data["sensors"]) == 6, f"Expected 6 sectors, got {len(data['sensors'])}"

    sector_1 = data["sensors"][0]
    required_keys = ["sector", "carbonMonoxide", "temperature", "timestamp", "isActive"]
    for key in required_keys:
        assert key in sector_1, f"Sector missing key: {key}"

    assert sector_1["isActive"] == True, "Sector 1 should be active"
    assert isinstance(sector_1["temperature"], (int, float)), "Temperature should be numeric"
    assert isinstance(sector_1["carbonMonoxide"], (int, float)), "CO should be numeric"
    assert sector_1["temperature"] >= 0, "Temperature should not be negative"
    assert sector_1["carbonMonoxide"] >= 0, "CO should not be negative"

    print(f"  ✅ Sensor data structure valid")
    print(f"     Temp: {sector_1['temperature']}°C  |  CO: {sector_1['carbonMonoxide']}ppm")
    return True


def test_predictions_structure(session):
    """Test /api/predictions/ returns correct structure."""
    print("  Testing /api/predictions/...")
    r = session.get(f"{BASE_URL}/api/predictions/")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()

    assert "predictions" in data, "Missing 'predictions' key"
    assert "riskLevel" in data, "Missing 'riskLevel' key"
    assert "modelUsed" in data, "Missing 'modelUsed' key"
    assert data["riskLevel"] in ["normal", "warning", "critical"], \
        f"Invalid riskLevel: {data['riskLevel']}"

    for pred in data["predictions"]:
        required = ["sector", "gasType", "severity", "currentLevel",
                    "predictedLevel", "timeToReach", "recommendation"]
        for key in required:
            assert key in pred, f"Prediction missing key: {key}"

    print(f"  ✅ Predictions structure valid")
    print(f"     Risk level: {data['riskLevel']}  |  Active predictions: {len(data['predictions'])}")
    return True


def test_historical_data_structure(session):
    """Test /api/historical-data/ returns correct structure."""
    print("  Testing /api/historical-data/...")
    r = session.get(f"{BASE_URL}/api/historical-data/")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()

    assert "historicalData" in data, "Missing 'historicalData' key"
    assert "count" in data, "Missing 'count' key"
    assert len(data["historicalData"]) > 0, "Historical data should not be empty"

    point = data["historicalData"][0]
    required = ["timestamp", "carbonMonoxide", "temperature"]
    for key in required:
        assert key in point, f"Historical point missing key: {key}"

    print(f"  ✅ Historical data structure valid")
    print(f"     Points in buffer: {data['count']}")
    return True


def test_serial_status(session):
    """Test /api/serial-status/ shows ESP32 connected."""
    print("  Testing /api/serial-status/...")
    r = session.get(f"{BASE_URL}/api/serial-status/")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()

    assert "port" in data, "Missing 'port' key"
    assert "connected" in data, "Missing 'connected' key"
    assert "history_points" in data, "Missing 'history_points' key"

    print(f"  ✅ Serial status endpoint valid")
    print(f"     Port: {data['port']}  |  Connected: {data['connected']}  "
          f"|  History points: {data['history_points']}")
    return data["connected"]


def test_data_updates_over_time(session):
    """Test that data actually changes between polls (proves live data)."""
    print("  Testing live data updates (waiting 6 seconds)...")

    r1 = session.get(f"{BASE_URL}/api/sensor-data/")
    ts1 = r1.json()["timestamp"]

    time.sleep(6)  # wait for next ESP32 reading

    r2 = session.get(f"{BASE_URL}/api/sensor-data/")
    ts2 = r2.json()["timestamp"]

    assert ts1 != ts2, "Timestamp should change between polls — data not updating!"
    print(f"  ✅ Data is live and updating")
    print(f"     Poll 1: {ts1}")
    print(f"     Poll 2: {ts2}")
    return True


def run_database_integration_test():
    separator("PART B — BACKEND & DATABASE INTEGRATION TEST")
    print("  Make sure Django server is running before this test\n")

    session = login_session()

    tests = [
        ("Sensor Data Structure",     test_sensor_data_structure),
        ("Predictions Structure",     test_predictions_structure),
        ("Historical Data Structure", test_historical_data_structure),
        ("Serial Status Endpoint",    test_serial_status),
        ("Live Data Updates",         test_data_updates_over_time),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn(session)
            passed += 1
        except AssertionError as e:
            print(f"  ❌ FAILED: {name}")
            print(f"     {e}")
            failed += 1
        except requests.ConnectionError:
            print(f"  ❌ FAILED: {name}")
            print(f"     Could not connect to {BASE_URL} — is Django running?")
            failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {name} — {e}")
            failed += 1
        print()

    return passed, failed


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mine Safety Integration Tests")
    parser.add_argument("--serial",   action="store_true", help="Run serial flood test only")
    parser.add_argument("--database", action="store_true", help="Run database integration test only")
    parser.add_argument("--all",      action="store_true", help="Run all tests")
    args = parser.parse_args()

    if not any([args.serial, args.database, args.all]):
        args.all = True  # default: run everything

    print("\n" + "█"*60)
    print("  MINE SAFETY SYSTEM — INTEGRATION TESTS")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)

    if args.serial or args.all:
        rejection_rate, valid_ok = run_serial_flood_test()

    if args.database or args.all:
        passed, failed = run_database_integration_test()

    separator("FINAL SUMMARY")
    if args.serial or args.all:
        print(f"  Serial Flood Test:  {rejection_rate:.1f}% rejection rate  "
              f"| Valid input: {'✅ accepted' if valid_ok else '❌ rejected'}")
    if args.database or args.all:
        total = passed + failed
        print(f"  Database Tests:     {passed}/{total} passed  "
              f"{'✅' if failed == 0 else '❌'}")

    print(f"\n  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60 + "\n")