import struct
import unittest
from unittest.mock import patch

import dash_funcs
from dashboard import HubClient, decode, find_byte_array


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


if __name__ == "__main__":
    unittest.main()
