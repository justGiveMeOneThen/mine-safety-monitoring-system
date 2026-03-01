# =============================================================================
# FILE 3: tests/test_unit_risk.py
# PURPOSE: Automated unit tests for risk calculation logic
# WHERE TO PUT IT: tests/ folder (same folder as the other test files)
# HOW TO RUN: python -m pytest tests/test_unit_risk.py -v
#             OR: python tests/test_unit_risk.py
# WHAT TO EXPECT: Each test prints PASSED or FAILED with details
#                 All 20 tests should pass
# =============================================================================

import os
import sys
import unittest

# ── Setup path so we can import Django modules ────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mine_safety_project.settings")

import django
django.setup()

from monitoring.ml_predictor import RiskPredictor


class TestRiskCalculationLogic(unittest.TestCase):
    """
    Unit tests for the RiskPredictor class.
    Tests both ML model predictions and the fallback rule-based logic.
    Focuses on boundary conditions and edge cases.
    """

    def setUp(self):
        """Create a fresh predictor for each test."""
        self.predictor = RiskPredictor()

    # ── Fallback Logic Tests ──────────────────────────────────────────────────
    # These test the _fallback_prediction method directly
    # so results are deterministic regardless of ML model

    def test_fallback_safe_low_co_low_temp(self):
        """Clean air, normal temperature → SAFE"""
        result = self.predictor._fallback_prediction(co_level=10, temperature=22)
        self.assertEqual(result['risk_level'], 'normal',
            "Low CO (10ppm) and low temp (22°C) should be SAFE")

    def test_fallback_safe_boundary_co(self):
        """CO exactly at safe boundary (30ppm) → SAFE"""
        result = self.predictor._fallback_prediction(co_level=30, temperature=25)
        self.assertEqual(result['risk_level'], 'normal',
            "CO at exactly 30ppm should still be SAFE")

    def test_fallback_safe_boundary_temp(self):
        """Temperature exactly at safe boundary (30°C) → SAFE"""
        result = self.predictor._fallback_prediction(co_level=15, temperature=30)
        self.assertEqual(result['risk_level'], 'normal',
            "Temp at exactly 30°C should still be SAFE")

    def test_fallback_warning_co_elevated(self):
        """CO just above warning threshold → WARNING"""
        result = self.predictor._fallback_prediction(co_level=31, temperature=25)
        self.assertEqual(result['risk_level'], 'warning',
            "CO at 31ppm should trigger WARNING")

    def test_fallback_warning_temp_elevated(self):
        """Temperature just above warning threshold → WARNING"""
        result = self.predictor._fallback_prediction(co_level=15, temperature=31)
        self.assertEqual(result['risk_level'], 'warning',
            "Temp at 31°C should trigger WARNING")

    def test_fallback_warning_both_elevated(self):
        """Both CO and temp in warning range → WARNING"""
        result = self.predictor._fallback_prediction(co_level=40, temperature=33)
        self.assertEqual(result['risk_level'], 'warning',
            "Both CO=40 and temp=33°C should be WARNING")

    def test_fallback_critical_high_co(self):
        """CO above critical threshold → CRITICAL"""
        result = self.predictor._fallback_prediction(co_level=51, temperature=25)
        self.assertEqual(result['risk_level'], 'critical',
            "CO at 51ppm should trigger CRITICAL")

    def test_fallback_critical_high_temp(self):
        """Temperature above critical threshold → CRITICAL"""
        result = self.predictor._fallback_prediction(co_level=15, temperature=36)
        self.assertEqual(result['risk_level'], 'critical',
            "Temp at 36°C should trigger CRITICAL")

    def test_fallback_critical_both_extreme(self):
        """Both CO and temp at extreme levels → CRITICAL"""
        result = self.predictor._fallback_prediction(co_level=150, temperature=50)
        self.assertEqual(result['risk_level'], 'critical',
            "Extreme CO=150 and temp=50°C should be CRITICAL")

    def test_fallback_predicted_co_increases(self):
        """Predicted future CO should be higher than current"""
        result = self.predictor._fallback_prediction(co_level=40, temperature=25)
        self.assertGreater(result['predicted_co'], 40,
            "Predicted CO should be greater than current CO")

    def test_fallback_predicted_temp_increases(self):
        """Predicted future temperature should be higher than current"""
        result = self.predictor._fallback_prediction(co_level=20, temperature=28)
        self.assertGreater(result['predicted_temp'], 28,
            "Predicted temperature should be greater than current temperature")

    def test_fallback_no_negative_predictions(self):
        """Predicted values should never be negative"""
        result = self.predictor._fallback_prediction(co_level=0, temperature=0)
        self.assertGreaterEqual(result['predicted_co'], 0,
            "Predicted CO should never be negative")
        self.assertGreaterEqual(result['predicted_temp'], 0,
            "Predicted temperature should never be negative")

    def test_fallback_raw_prediction_matches_risk(self):
        """raw_prediction integer should match risk_level string"""
        safe_result = self.predictor._fallback_prediction(10, 22)
        self.assertEqual(safe_result['raw_prediction'], 0, "SAFE should map to 0")

        warning_result = self.predictor._fallback_prediction(35, 25)
        self.assertEqual(warning_result['raw_prediction'], 1, "WARNING should map to 1")

        critical_result = self.predictor._fallback_prediction(60, 25)
        self.assertEqual(critical_result['raw_prediction'], 2, "CRITICAL should map to 2")

    # ── Rolling History Tests ─────────────────────────────────────────────────

    def test_history_accumulates(self):
        """History deque should grow with each prediction"""
        self.predictor.predict_risk(20, 25)
        self.predictor.predict_risk(22, 26)
        self.assertEqual(len(self.predictor.temp_history), 2,
            "History should contain 2 readings after 2 predictions")

    def test_history_max_length(self):
        """History should not exceed maxlen=5"""
        for i in range(10):
            self.predictor.predict_risk(20 + i, 25 + i)
        self.assertLessEqual(len(self.predictor.temp_history), 5,
            "History deque should never exceed maxlen of 5")

    def test_reset_clears_history(self):
        """reset_history() should empty both deques"""
        self.predictor.predict_risk(20, 25)
        self.predictor.reset_history()
        self.assertEqual(len(self.predictor.temp_history), 0,
            "temp_history should be empty after reset")
        self.assertEqual(len(self.predictor.gas_history), 0,
            "gas_history should be empty after reset")

    # ── predict_risk Integration Tests ───────────────────────────────────────

    def test_predict_risk_returns_required_keys(self):
        """predict_risk must always return all required keys"""
        result = self.predictor.predict_risk(25, 27)
        required_keys = ['predicted_co', 'predicted_temp', 'risk_level',
                         'model_used', 'raw_prediction']
        for key in required_keys:
            self.assertIn(key, result,
                f"predict_risk result missing required key: '{key}'")

    def test_predict_risk_valid_risk_level(self):
        """risk_level must always be one of the three valid values"""
        valid_levels = {'normal', 'warning', 'critical'}
        for co, temp in [(10, 22), (35, 31), (60, 37)]:
            result = self.predictor.predict_risk(co, temp)
            self.assertIn(result['risk_level'], valid_levels,
                f"risk_level '{result['risk_level']}' is not valid for CO={co}, temp={temp}")

    def test_predict_risk_model_used_string(self):
        """model_used should always be a non-empty string"""
        result = self.predictor.predict_risk(20, 25)
        self.assertIsInstance(result['model_used'], str,
            "model_used should be a string")
        self.assertGreater(len(result['model_used']), 0,
            "model_used should not be empty")


# ── Run directly ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "█"*60)
    print("  MINE SAFETY SYSTEM — UNIT TESTS")
    print("  Testing: RiskPredictor logic and boundary conditions")
    print("█"*60 + "\n")

    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromTestCase(TestRiskCalculationLogic)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "█"*60)
    if result.wasSuccessful():
        print(f"  ✅ ALL {result.testsRun} TESTS PASSED")
    else:
        print(f"  ❌ {len(result.failures)} FAILED, {len(result.errors)} ERRORS")
        print(f"  ✅ {result.testsRun - len(result.failures) - len(result.errors)} passed")
    print("█"*60 + "\n")