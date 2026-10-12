import time
import struct
import json
import socket
import requests
import urllib.request
from datetime import datetime

# constants for io-link hub
HUB_URL = "http://192.168.99.162"
HUB_USERNAME="washer_test_user"
HUB_PASSWORD="washer_test_password"
COLD_TEMP_ALIAS = "master1port1"
HOT_TEMP_ALIAS = "master1port2"
COLD_PRESSURE_ALIAS = "master1port3"
HOT_PRESSURE_ALIAS = "master1port4"
COLD_FLOW_SENSOR_ALIAS = "master1port5"
HOT_FLOW_SENSOR_ALIAS = "master1port6"
NEAR_AMBIENT_ALIAS = "master1port7"
FAR_AMBIENT_ALIAS = "master1port8"
NEAR_FAR_AMBIENT_ALIASES = [NEAR_AMBIENT_ALIAS,FAR_AMBIENT_ALIAS]



# timestamp helper functions
def ordinal_suffix(day: int) -> str:
    """Return a day number with its English ordinal suffix."""
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"{day}{suffix}"

def make_timestamp(sample_number: int) -> dict:
    """Generate identifiers and timestamps for one logged sample."""
    now = datetime.now()
    epoch_ms = int(now.timestamp() * 1000)

    readable_time = (
        f"{now.strftime('%B')} "
        f"{ordinal_suffix(now.day)} "
        f"{now.year} at "
        f"{now.strftime('%H:%M:%S')}"
    )

    return {
        "sample_num": sample_number,
        "epoch_timestamp_ms": epoch_ms,
        "human_timestamp": readable_time,
    }

# general function for getting bytes from iolink hub
def _get_byte_array(url: str) -> list[int]:
    """GET an IO-Link value and return its byte array."""
    with urllib.request.urlopen(url, timeout=0.5) as response:
        data = json.load(response)

    if not isinstance(data, dict):
        raise TypeError(f"Expected a dictionary, got {data!r}")

    # Process-data responses are wrapped inside "iolink".
    payload = data.get("iolink", data)

    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected response structure: {data!r}")

    # Some responses include a validity flag; parameter reads may not.
    if payload.get("valid") is False:
        raise RuntimeError(f"IO-Link value is marked invalid: {data!r}")

    value = payload.get("value")

    if value is None:
        raise KeyError(f"No 'value' field in hub response: {data!r}")

    if not isinstance(value, list):
        raise TypeError(
            f"Expected 'value' to be a list, got {type(value).__name__}: {value!r}"
        )

    return value

# get water temperature functions
def _get_tm311_unit(sensor_alias: str) -> str:
    """
    Read and return the TM311's configured engineering unit.

    TM311 parameter index 5121 (0x1401):
      32 = °C
      33 = °F
      35 = K
    """
    url = (
        f"{HUB_URL}/iolink/v1/devices/{sensor_alias}"
        "/parameters/5121/value/?format=byteArray"
    )

    units = {
        32: "°C",
        33: "°F",
        35: "K",
    }

    try:
        unit_bytes = _get_byte_array(url)

        if len(unit_bytes) != 1:
            raise ValueError(
                f"Expected 1 TM311 unit byte, got {len(unit_bytes)}."
            )

        unit_number = unit_bytes[0]

        return units.get(unit_number, f"unknown unit ({unit_number})")

    except Exception as exc:
        print(f"Failed to read TM311 unit from {sensor_alias}: {exc}")
        return "offline"

def _get_tm311_temperature(sensor_alias: str):
    """
    Return the current TM311 temperature in its configured engineering unit.

    The first two process-data bytes are a signed, big-endian 16-bit
    temperature value with a scale factor of 0.1. The numeric value already
    follows the unit selected in TM311 parameter 5121.
    """
    url = (
        f"{HUB_URL}/iolink/v1/devices/{sensor_alias}"
        "/processdata/getdata/value?format=byteArray"
    )

    try:
        process_data = _get_byte_array(url)

        if len(process_data) != 4:
            raise ValueError(
                f"Expected 4 TM311 process-data bytes, got {len(process_data)}."
            )

        raw_temperature = struct.unpack(">h", bytes(process_data[0:2]))[0]

        # Special TM311 process-data values.
        if raw_temperature == 32764:
            raise RuntimeError("TM311 reports no measurement data.")
        if raw_temperature == -32760:
            raise RuntimeError("TM311 temperature is below its measuring range.")
        if raw_temperature == 32760:
            raise RuntimeError("TM311 temperature is above its measuring range.")

        return str(round(raw_temperature / 10.0, 1))

    except Exception as exc:
        print(f"Failed to read TM311 temperature from {sensor_alias}: {exc}")
        return "UNKNOWN"

def get_cold_temp_value():
    return _get_tm311_temperature(COLD_TEMP_ALIAS)

def get_cold_temp_unit():
    return _get_tm311_unit(COLD_TEMP_ALIAS)

def get_hot_temp_value():
    return _get_tm311_temperature(HOT_TEMP_ALIAS)

def get_hot_temp_unit():
    return _get_tm311_unit(HOT_TEMP_ALIAS)



# get water pressure functions
def _get_ptouch_pressure_kpa(sensor_alias: str):
    """
    Return pressure in kPa from an MP Sensor P.Touch transmitter.

    The four-byte cyclic input begins with a signed, big-endian
    16-bit pressure value in kPa.
    """
    url = (
        f"{HUB_URL}/iolink/v1/devices/{sensor_alias}"
        "/processdata/getdata/value?format=byteArray"
    )

    try:
        process_data = _get_byte_array(url)

        if len(process_data) != 4:
            raise ValueError(
                f"Expected 4 P.Touch process-data bytes, got {len(process_data)}."
            )

        raw_pressure_kpa = struct.unpack(">h", bytes(process_data[0:2]))[0]

        # Special process-data values defined by the P.Touch IO-Link interface.
        if raw_pressure_kpa == 32760:
            raise RuntimeError("P.Touch pressure is above the process-data range.")
        if raw_pressure_kpa == 32764:
            raise RuntimeError("P.Touch reports no measurement data.")

        return str(raw_pressure_kpa)

    except Exception as exc:
        print(f"Failed to read P.Touch pressure from {sensor_alias}: {exc}")
        return "UNKNOWN"

def _get_ptouch_pressure_unit(sensor_alias: str) -> str:
    return "kPa"
    

def get_cold_pres_value():
    return _get_ptouch_pressure_kpa(COLD_PRESSURE_ALIAS)

def get_cold_pres_unit():
    return _get_ptouch_pressure_unit(COLD_PRESSURE_ALIAS)

def get_hot_pres_value():
    return _get_ptouch_pressure_kpa(HOT_PRESSURE_ALIAS)

def get_hot_pres_unit():
    return _get_ptouch_pressure_unit(HOT_PRESSURE_ALIAS)



# Get accumulated water volume in US gallons
def _get_picomag_totalizer(sensor_alias: str):
    """
    Return the Picomag's accumulated volume in US gallons.

    The 15-byte cyclic process data contains the totalizer
    in bytes 4-7 as a big-endian IEEE-754 float in liters.
    """
    url = (
        f"{HUB_URL}/iolink/v1/devices/{sensor_alias}"
        "/processdata/getdata/value?format=byteArray"
    )

    try:
        process_data = _get_byte_array(url)

        if len(process_data) != 15:
            raise ValueError(
                f"Expected 15 Picomag process-data bytes, "
                f"got {len(process_data)}."
            )

        totalizer_liters = struct.unpack(
            ">f", bytes(process_data[4:8])
        )[0]

        return str(round(totalizer_liters, 3))

    except Exception as exc:
        print(f"Failed to read Picomag totalizer from {sensor_alias}: {exc}")
        return "UNKNOWN"



# Reset accumulated water volume to zero
def reset_picomag_totalizer(sensor_alias: str):
    """
    Reset the Picomag's internal flow totalizer.

    ISDU index: 362 (0x016A)
    Data type: uint16
    Reset command: 1
    """
    url = (
        f"{HUB_URL}/iolink/v1/devices/{sensor_alias}"
        "/parameters/362/value"
    )

    try:
        response = requests.post(
            url,
            json={"value": [0, 1]},
            timeout=5
        )

        response.raise_for_status()

        return "success"

    except Exception as exc:
        print(f"Failed to reset Picomag totalizer "
              f"on {sensor_alias}: {exc}")
        return "failure"

def reset_hot_usage():
    print(f'hot totalizer reset attempt: {reset_picomag_totalizer(HOT_FLOW_SENSOR_ALIAS)}')

def reset_cold_usage():
    print(f'cold totalizer reset attempt: {reset_picomag_totalizer(COLD_FLOW_SENSOR_ALIAS)}')

def _get_picomag_totalizer_unit(sensor_alias: str) -> str:
    return ("L")

def get_cold_usage_value():
    return _get_picomag_totalizer(COLD_FLOW_SENSOR_ALIAS)

def get_cold_usage_unit():
    return _get_picomag_totalizer_unit(COLD_FLOW_SENSOR_ALIAS)

def get_hot_usage_value():
    return _get_picomag_totalizer(HOT_FLOW_SENSOR_ALIAS)

def get_hot_usage_unit():
    return _get_picomag_totalizer_unit(HOT_FLOW_SENSOR_ALIAS)



def _get_ambient_temp_rh():
    """
    Get both near and far temperature and humidity.
    Values are cached to allow a slower polling rate.
    """

    output_list = []
    alias_num = 0

    for alias in NEAR_FAR_AMBIENT_ALIASES:
        ambient_url = f"{HUB_URL}/iolink/v1/devices/{alias}/processdata/getdata/value?format=byteArray"

        try:
            process_data = _get_byte_array(ambient_url)

            if len(process_data) != 6:
                raise ValueError(
                    f"Expected 6 CSS 014 process-data bytes, "
                    f"got {len(process_data)}"
                )


            raw_temperature = struct.unpack(
                ">h", bytes(process_data[0:2])
            )[0]

            raw_humidity = struct.unpack(
                ">h", bytes(process_data[3:5])
            )[0]

            temperature = raw_temperature / 10.0
            humidity = raw_humidity / 10.0
            output_list.extend([str(temperature), str(humidity)])

            
        except Exception as exc:
            print(f"Failed to read ambient temperature/RH from {alias}: {exc}")
            output_list.extend(["UNKNOWN", "UNKNOWN"])

        alias_num += 1

    return output_list


def get_ambient_log_string():
    pass

def get_all_ambient_data():
    input_list=_get_ambient_temp_rh()
    ambient_info_dict={'near_temp':input_list[0],'near_temp_unit':'°C','near_hum':input_list[1],"near_hum_unit":'% R.H.','far_temp':input_list[2],'far_temp_unit':'°C','far_hum':input_list[3],"far_hum_unit":'% R.H.'}

    return ambient_info_dict
