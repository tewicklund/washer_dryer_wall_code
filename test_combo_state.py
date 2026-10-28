import os
import unittest
from unittest.mock import Mock, patch

import requests

import combo_state as combo
import main_3rate as logger


def status(job, operating="running", cycle="allInOne"):
    return {"components": {"main": {
        "samsungce.washerOperatingState": {
            "washerJobState": {"value": job},
            "operatingState": {"value": operating},
        },
        "samsungce.washerCycle": {"cycleType": {"value": cycle}},
    }}}


class ComboTests(unittest.TestCase):
    def test_cycle_phases(self):
        cases = [
            ("wash", "running", "allInOne", "WASH"),
            ("rinse", "paused", "allInOne", "WASH"),
            ("spin", "running", "allInOne", "WASH"),
            ("drying", "running", "allInOne", "DRY"),
            ("aIDrying", "running", "allInOne", "DRY"),
            ("cooling", "running", "allInOne", "DRY"),
            ("finished", "running", "dryingOnly", "IDLE"),
            ("none", "ready", "dryingOnly", "IDLE"),
            ("weightSensing", "running", "dryingOnly", "DRY"),
            ("weightSensing", "running", "allInOne", "WASH"),
            ("unexpected", "running", "allInOne", "UNKNOWN"),
        ]
        for job, operating, cycle, expected in cases:
            with self.subTest(job=job, operating=operating, cycle=cycle):
                self.assertEqual(combo.classify_combo_state(status(job, operating, cycle)), expected)
        self.assertEqual(combo.classify_combo_state({}), "UNKNOWN")
        self.assertEqual(combo.classify_combo_state({"components": {"main": {
            "washerOperatingState": {"machineState": {"value": "run"},
                                     "washerJobState": {"value": "drying"}}
        }}}), "DRY")

    @patch.dict(os.environ, {"SMARTTHINGS_TOKEN": "test-token", "SMARTTHINGS_DEVICE_ID": "test-device"})
    @patch("combo_state.requests.get")
    def test_fresh_request_and_failure_preserves_ambient(self, get):
        get.return_value = Mock(json=Mock(return_value=status("wash")))
        readings = dict(near_temp=20, far_temp=21, near_hum=40, far_hum=41)
        with patch.object(logger.iol, "get_all_ambient_data", return_value=readings):
            self.assertEqual(logger.get_ambient_values(), [20, 21, 40, 41, "WASH"])
            self.assertEqual(logger.get_ambient_values()[-1], "WASH")
            self.assertEqual(get.call_count, 2)
            get.assert_called_with(
                "https://api.smartthings.com/v1/devices/test-device/status",
                headers={"Authorization": "Bearer test-token"}, timeout=(3.05, 10))
            get.side_effect = requests.Timeout()
            self.assertEqual(logger.get_ambient_values(), [20, 21, 40, 41, "UNKNOWN"])

    def test_sensor_failure_still_fetches_state(self):
        with patch.object(logger.iol, "get_all_ambient_data", side_effect=RuntimeError("offline")), \
                patch.object(logger, "get_combo_state", return_value="DRY") as get:
            self.assertEqual(logger.get_ambient_values(), ["UNKNOWN"] * 4 + ["DRY"])
            get.assert_called_once_with()
        self.assertEqual(logger.POLL_PERIODS["ambient"], 120)
        self.assertEqual(logger.AMBIENT_HEADERS[-1], "combo_state")

    @patch.dict(os.environ, {}, clear=True)
    @patch("combo_state.requests.get")
    def test_missing_token_does_not_contact_api(self, get):
        self.assertEqual(combo.get_combo_state(), "UNKNOWN")
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
