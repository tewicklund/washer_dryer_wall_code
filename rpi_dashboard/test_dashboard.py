import queue
import sys
import struct
import unittest
from unittest.mock import Mock, patch

import dash_funcs
from dashboard import HubClient, Poller, setup_button, decode, find_byte_array


class DecoderTests(unittest.TestCase):
    def test_nested_hub_response(self):
        self.assertEqual(find_byte_array({"iolink": {"value": [0, 123, 9]}}), [0, 123, 9])

    def test_hex_response(self):
        self.assertEqual(find_byte_array({"value": "00 7B"}), [0, 123])

    def test_signed_temperature(self):
        self.assertEqual(decode({"value": [0xFF, 0x85]}, {"type":"bytes", "format":"int16_be", "scale":0.1}), -12.3)

    def test_float_at_offset(self):
        payload = {"value": [0] * 8 + [0x40, 0x20, 0x00, 0x00]}
        self.assertEqual(decode(payload, {"type":"bytes", "format":"float32_be", "offset":8}), 2.5)

    def test_json_path(self):
        self.assertEqual(decode({"iolink":{"value": 42}}, {"type":"json", "path":"iolink.value", "scale":0.1}), 4.2)

    def test_water_totalizers_read_volume_in_liters(self):
        payload = [0] * 4 + list(struct.pack(">f", 123.456)) + list(struct.pack(">f", 2.5)) + [0] * 3
        for getter, alias in (
            (dash_funcs.get_cold_usage_value, dash_funcs.COLD_FLOW_SENSOR_ALIAS),
            (dash_funcs.get_hot_usage_value, dash_funcs.HOT_FLOW_SENSOR_ALIAS),
        ):
            with self.subTest(alias=alias), patch.object(dash_funcs, "_get_byte_array", return_value=payload) as read:
                self.assertEqual(getter(), 123.456)
                read.assert_called_once_with(dash_funcs._process_url(alias))

    def test_water_totalizer_rejects_incomplete_data(self):
        with patch.object(dash_funcs, "_get_byte_array", return_value=[0] * 14), patch("builtins.print"):
            self.assertEqual(dash_funcs.get_cold_usage_value(), "UNKNOWN")

    def test_ambient_celsius_conversion_and_humidity_offset(self):
        dash_funcs.AMBIENT_TEMP_MODE_CACHE.clear()
        responses = [[0, 245, 0, 1, 239, 0], [0]]
        with patch.object(dash_funcs, "_get_byte_array", side_effect=responses):
            self.assertEqual(dash_funcs._get_ambient_temp_rh("testport"), "76.1 : 49.5")

    def test_two_ambient_cards_share_one_function_call(self):
        config = {"hub": {"base_url": "http://test", "timeout_seconds": 1}}
        client = HubClient(config)
        temp = {"value_function":"get_temp_rh_near_value", "component":0, "shared_cache_seconds":2}
        humidity = {"value_function":"get_temp_rh_near_value", "component":1, "shared_cache_seconds":2}
        with patch.object(dash_funcs, "get_temp_rh_near_value", return_value="76.1 : 49.5") as getter:
            self.assertEqual(client.read(temp), 76.1)
            self.assertEqual(client.read(humidity), 49.5)
            getter.assert_called_once()


class ButtonPollingTests(unittest.TestCase):
    def test_idle_then_one_scan_per_request_and_fresh_cache(self):
        client = Mock()
        client.function_cache = {"old": (0, 123)}
        client.read.side_effect = [10, RuntimeError("offline"), 20, 30]
        output = queue.Queue()
        poller = Poller(client, [{"id": "a"}, {"id": "b"}], output)
        poller.start()
        try:
            with self.assertRaises(queue.Empty):
                output.get(timeout=0.05)
            client.read.assert_not_called()
            poller.request_read()
            self.assertEqual(output.get(timeout=1).value, 10)
            self.assertEqual(output.get(timeout=1).error, "offline")
            self.assertEqual(client.function_cache, {})
            with self.assertRaises(queue.Empty):
                output.get(timeout=0.05)
            client.function_cache["old"] = (0, 123)
            poller.request_read()
            self.assertEqual(output.get(timeout=1).value, 20)
            self.assertEqual(output.get(timeout=1).value, 30)
            self.assertEqual(client.function_cache, {})
        finally:
            poller.stop()
            poller.join(timeout=1)
        self.assertFalse(poller.is_alive())

    def test_presses_queued_during_scan_are_preserved(self):
        client = Mock()
        output = queue.Queue()
        poller = Poller(client, [{"id": "a"}], output)
        def read(sensor):
            if client.read.call_count == 1:
                poller.request_read()
            return 42
        client.read.side_effect = read
        poller.request_read()
        poller.start()
        try:
            self.assertEqual(output.get(timeout=1).value, 42)
            self.assertEqual(output.get(timeout=1).value, 42)
            with self.assertRaises(queue.Empty):
                output.get(timeout=0.05)
        finally:
            poller.stop()
            poller.join(timeout=1)

    def test_gpio_is_active_high_debounced_and_callback_only_requests(self):
        gpiozero = Mock()
        callback = Mock()
        with patch.dict(sys.modules, {"gpiozero": gpiozero}):
            button = setup_button({}, callback)
        gpiozero.Button.assert_called_once_with(17, pull_up=False, bounce_time=0.1)
        callback.assert_not_called()
        button.when_pressed()
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
