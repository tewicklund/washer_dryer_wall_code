"""Sensor getters adapted from the user-supplied dash_funcs.py.

Only read operations used by the dashboard are included. Getter names and
decoding behavior match the supplied module.
"""

import json
import struct
import urllib.request


HUB_URL = "http://192.168.99.162"
COLD_TEMP_ALIAS = "master1port1"
HOT_TEMP_ALIAS = "master1port2"
COLD_PRESSURE_ALIAS = "master1port3"
HOT_PRESSURE_ALIAS = "master1port4"
COLD_FLOW_SENSOR_ALIAS = "master1port5"
HOT_FLOW_SENSOR_ALIAS = "master1port6"
NEAR_AMBIENT_ALIAS = "master1port7"
FAR_AMBIENT_ALIAS = "master1port8"

AMBIENT_TEMP_MODE_CACHE = {}
AMBIENT_ONLINE_CACHE = {}


def configure(hub_url: str, timeout_seconds: float = 1.0) -> None:
    """Allow the standalone dashboard config to override connection settings."""
    global HUB_URL, REQUEST_TIMEOUT
    HUB_URL = hub_url.rstrip("/")
    REQUEST_TIMEOUT = timeout_seconds
    AMBIENT_TEMP_MODE_CACHE.clear()
    AMBIENT_ONLINE_CACHE.clear()


REQUEST_TIMEOUT = 1.0


def _get_byte_array(url: str) -> list[int]:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise TypeError(f"Expected a dictionary, got {data!r}")
    payload = data.get("iolink", data)
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected response structure: {data!r}")
    if payload.get("valid") is False:
        raise RuntimeError(f"IO-Link value is marked invalid: {data!r}")
    value = payload.get("value")
    if value is None:
        raise KeyError(f"No 'value' field in hub response: {data!r}")
    if not isinstance(value, list):
        raise TypeError(f"Expected 'value' to be a list, got {type(value).__name__}: {value!r}")
    return value


def _process_url(alias: str) -> str:
    return f"{HUB_URL}/iolink/v1/devices/{alias}/processdata/getdata/value?format=byteArray"


def _get_tm311_temperature(sensor_alias: str):
    try:
        data = _get_byte_array(_process_url(sensor_alias))
        if len(data) != 4:
            raise ValueError(f"Expected 4 TM311 process-data bytes, got {len(data)}.")
        raw = struct.unpack(">h", bytes(data[0:2]))[0]
        if raw == 32764: raise RuntimeError("TM311 reports no measurement data.")
        if raw == -32760: raise RuntimeError("TM311 temperature is below its measuring range.")
        if raw == 32760: raise RuntimeError("TM311 temperature is above its measuring range.")
        return round(raw / 10.0, 1)
    except Exception as exc:
        print(f"Failed to read TM311 temperature from {sensor_alias}: {exc}")
        return "UNKNOWN"


def get_cold_temp_value(): return _get_tm311_temperature(COLD_TEMP_ALIAS)
def get_hot_temp_value(): return _get_tm311_temperature(HOT_TEMP_ALIAS)


def _get_ptouch_pressure_psig(sensor_alias: str):
    try:
        data = _get_byte_array(_process_url(sensor_alias))
        if len(data) != 4:
            raise ValueError(f"Expected 4 P.Touch process-data bytes, got {len(data)}.")
        raw_kpa = struct.unpack(">h", bytes(data[0:2]))[0]
        if raw_kpa == 32760: raise RuntimeError("P.Touch pressure is above the process-data range.")
        if raw_kpa == 32764: raise RuntimeError("P.Touch reports no measurement data.")
        return round(raw_kpa * 0.145, 2)
    except Exception as exc:
        print(f"Failed to read P.Touch pressure from {sensor_alias}: {exc}")
        return "UNKNOWN"


def get_cold_pres_value(): return _get_ptouch_pressure_psig(COLD_PRESSURE_ALIAS)
def get_hot_pres_value(): return _get_ptouch_pressure_psig(HOT_PRESSURE_ALIAS)


def _get_picomag_totalizer(sensor_alias: str):
    """Return accumulated volume in liters from Picomag process-data bytes 4-7."""
    try:
        data = _get_byte_array(_process_url(sensor_alias))
        if len(data) != 15:
            raise ValueError(f"Expected 15 Picomag process-data bytes, got {len(data)}.")
        return round(struct.unpack(">f", bytes(data[4:8]))[0], 3)
    except Exception as exc:
        print(f"Failed to read Picomag totalizer from {sensor_alias}: {exc}")
        return "UNKNOWN"


def get_cold_usage_value(): return _get_picomag_totalizer(COLD_FLOW_SENSOR_ALIAS)
def get_hot_usage_value(): return _get_picomag_totalizer(HOT_FLOW_SENSOR_ALIAS)


def _get_ambient_temp_mode(sensor_alias: str) -> int:
    if sensor_alias in AMBIENT_TEMP_MODE_CACHE:
        return AMBIENT_TEMP_MODE_CACHE[sensor_alias]
    url = f"{HUB_URL}/iolink/v1/devices/{sensor_alias}/parameters/66/value/?format=byteArray"
    mode_bytes = _get_byte_array(url)
    if len(mode_bytes) != 1:
        raise ValueError(f"Expected 1 temperature-mode byte, got {len(mode_bytes)}.")
    mode = mode_bytes[0]
    if mode not in (0, 1):
        raise ValueError(f"Unknown CSS 014 temperature mode: {mode}")
    AMBIENT_TEMP_MODE_CACHE[sensor_alias] = mode
    return mode


def _get_ambient_temp_rh(sensor_alias: str) -> str:
    try:
        data = _get_byte_array(_process_url(sensor_alias))
        if len(data) != 6:
            raise ValueError(f"Expected 6 CSS 014 process-data bytes, got {len(data)}.")
        temperature = struct.unpack(">h", bytes(data[0:2]))[0] / 10.0
        humidity = struct.unpack(">h", bytes(data[3:5]))[0] / 10.0
        if _get_ambient_temp_mode(sensor_alias) == 0:
            temperature = temperature * 9.0 / 5.0 + 32.0
        AMBIENT_ONLINE_CACHE[sensor_alias] = True
        return f"{temperature:.1f} : {humidity:.1f}"
    except Exception as exc:
        AMBIENT_ONLINE_CACHE[sensor_alias] = False
        print(f"Failed to read ambient temperature/RH from {sensor_alias}: {exc}")
        return "UNKNOWN"


def get_temp_rh_near_value(): return _get_ambient_temp_rh(NEAR_AMBIENT_ALIAS)
def get_temp_rh_far_value(): return _get_ambient_temp_rh(FAR_AMBIENT_ALIAS)
