"""Read-only SmartThings status for the Samsung laundry combo."""

import os

import requests


# Same unit as samsung_clothes_conditioning/condition_load.py.
DEFAULT_DEVICE_ID = "0655c7b5-c5db-0a46-1db1-f71000b430eb"
API_BASE = "https://api.smartthings.com/v1"


def classify_combo_state(status):
    main = status.get("components", {}).get("main", {})

    def value(capability, attribute):
        raw = main.get(capability, {}).get(attribute, {}).get("value")
        return str(raw).strip().lower() if raw is not None else ""

    # Prefer the Samsung-specific phase; standard capability is the fallback.
    job = (value("samsungce.washerOperatingState", "washerJobState")
           or value("washerOperatingState", "washerJobState"))
    operating = (value("samsungce.washerOperatingState", "operatingState")
                 or value("washerOperatingState", "machineState"))
    cycle = value("samsungce.washerCycle", "cycleType")
    if job in {"finished", "finish"}:
        return "IDLE"
    if operating in {"ready", "stop", "stopped", "idle"}:
        return "IDLE"
    if job in {"drying", "aidrying", "cooling", "airwash", "wrinkleprevent",
               "waitingtodry", "cleaningcondenser"}:
        return "DRY"
    if job in {"prewash", "wash", "rinse", "spin", "aiwash", "airinse", "aispin",
               "removingsuds", "drumcleaning", "dispensercleaning"}:
        return "WASH"
    # Sensing/startup/paused states need the selected cycle to identify the phase.
    if operating in {"run", "running", "pause", "paused"}:
        if cycle == "dryingonly":
            return "DRY"
        if cycle == "washingonly":
            return "WASH"
        if cycle == "allinone" and job in {"weightsensing", "soillevelsensing", "laundrysensing"}:
            return "WASH"
    return "UNKNOWN"


def get_combo_state():
    """Fetch fresh status per sample; never replace a failed read with IDLE."""
    token = os.environ.get("SMARTTHINGS_TOKEN")
    if not token:
        print("[combo_state] SMARTTHINGS_TOKEN is not set", flush=True)
        return "UNKNOWN"
    device_id = os.environ.get("SMARTTHINGS_DEVICE_ID", DEFAULT_DEVICE_ID)
    try:
        response = requests.get(
            f"{API_BASE}/devices/{device_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=(3.05, 10),
        )
        response.raise_for_status()
        state = classify_combo_state(response.json())
        if state == "UNKNOWN":
            print("[combo_state] Unrecognized or missing device state", flush=True)
        return state
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        # Avoid printing response bodies or credentials into the instrument log.
        print("[combo_state] SmartThings status request failed", flush=True)
        return "UNKNOWN"
