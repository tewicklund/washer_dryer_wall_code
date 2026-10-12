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

    epoch_ms = time.time_ns() // 1_000_000

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