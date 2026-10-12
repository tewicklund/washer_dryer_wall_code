"""Independent 4 Hz Xitron, 0.2 Hz water, and 5-minute ambient CSV logger.

Place this file alongside io_link_funcs.py and ch1_q_string.txt.
The Xitron must return one newline-terminated, comma-separated response per READ? query.
"""

import csv
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import io_link_funcs as iol

XITRON_IP = "192.168.99.245"
XITRON_PORT = 10733
XITRON_TIMEOUT = 1.0
NUM_HARMONICS = 15
POLL_PERIODS = {"power": 0.25, "water": 5.0, "ambient": 300.0}

WATER_NAMES = ["Cold Temp.", "Hot Temp.", "Cold Pres.", "Hot Pres.", "Cold Usage", "Hot Usage"]
AMBIENT_HEADERS = [
    "Near Ambi Temp. (°C)", "Far Ambi Temp. (°C)",
    "Near Ambi RH (% R.H.)", "Far Ambi RH (% R.H.)",
]


def timestamp(sample_num):
    # One clock reading determines both timestamp representations.
    return iol.make_timestamp(sample_num)


def make_query():
    base = Path(__file__).with_name("ch1_q_string.txt").read_text(encoding="utf-8").strip()
    if not base.startswith("READ?"):
        raise ValueError("ch1_q_string.txt should start with READ?")
    extra = "".join(f",V:CH1:H{n},A:CH1:H{n}" for n in range(1, NUM_HARMONICS + 1))
    query = base + extra + "\n"
    # Original column layout: READ?,<field>,<field>...
    fields = next(csv.reader([query.rstrip("\r\n")]))
    if fields[0] != "READ?":
        raise ValueError("Expected READ? as the first query token")
    return query.encode("ascii"), fields[1:]


def read_line(sock, buffer):
    """Read exactly one newline-delimited TCP response (preserving excess bytes)."""
    while b"\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Xitron closed its TCP connection")
        buffer.extend(chunk)
        if len(buffer) > 1024 * 1024:
            raise ValueError("Xitron response exceeds 1 MiB without newline")
    line, _, remaining = buffer.partition(b"\n")
    buffer[:] = remaining
    return line.rstrip(b"\r").decode("utf-8")


def write_log(path, headers, stop_event, interval, acquire, start_deadline):
    """Run one logger at an absolute monotonic cadence; skip missed slots."""
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["sample_num", "epoch_timestamp_ms", "human_timestamp", *headers])
        file.flush()
        sample = 0
        deadline = start_deadline
        while not stop_event.is_set():
            if stop_event.wait(max(0.0, deadline - time.monotonic())):
                break
            if stop_event.is_set():
                break
            stamp = timestamp(sample)
            try:
                readings = acquire()
                if len(readings) != len(headers):
                    raise ValueError(f"Expected {len(headers)} values, got {len(readings)}")
            except Exception as exc:
                print(f"[{path.stem}] sample {sample} failed: {exc}", flush=True)
                readings = ["UNKNOWN"] * len(headers)
            writer.writerow([
                stamp["sample_num"], stamp["epoch_timestamp_ms"],
                stamp["human_timestamp"], *readings,
            ])
            file.flush()
            sample += 1
            deadline += interval
            now = time.monotonic()
            if now > deadline:
                missed = int((now - deadline) // interval) + 1
                deadline += missed * interval
                print(f"[{path.stem}] skipped {missed} overdue sample slot(s)", flush=True)


def power_reader(query_bytes, ncols):
    """Return a callable maintaining its own Xitron connection and receive buffer."""
    connection = None
    rx_buffer = bytearray()

    def acquire():
        nonlocal connection
        try:
            if connection is None:
                connection = socket.create_connection((XITRON_IP, XITRON_PORT), timeout=XITRON_TIMEOUT)
                connection.settimeout(XITRON_TIMEOUT)
                rx_buffer.clear()
            connection.sendall(query_bytes)
            reply = read_line(connection, rx_buffer)
            values = next(csv.reader([reply]))
            if len(values) != ncols:
                raise ValueError(f"Xitron returned {len(values)} columns; expected {ncols}: {reply[:200]!r}")
            return values
        except Exception:
            # After a timeout, a late reply could be confused with the next query.
            # Discard the connection and its receive buffer before trying again.
            if connection is not None:
                connection.close()
            connection = None
            rx_buffer.clear()
            raise

    def close():
        nonlocal connection
        if connection is not None:
            connection.close()
            connection = None

    return acquire, close


def get_water_values():
    functions = (
        iol.get_cold_temp_value, iol.get_hot_temp_value,
        iol.get_cold_pres_value, iol.get_hot_pres_value,
        iol.get_cold_usage_value, iol.get_hot_usage_value,
    )
    # Functions independently turn device timeouts into 'UNKNOWN'.
    return [fn() for fn in functions]


def get_water_headers():
    unit_functions = (
        iol.get_cold_temp_unit, iol.get_hot_temp_unit,
        iol.get_cold_pres_unit, iol.get_hot_pres_unit,
        iol.get_cold_usage_unit, iol.get_hot_usage_unit,
    )
    # Unit queries happen once, before acquisition starts, rather than at 0.2 Hz.
    units = [fn() for fn in unit_functions]
    return [f"{name} ({unit if unit != 'offline' else '???'})"
            for name, unit in zip(WATER_NAMES, units)]


def get_ambient_values():
    values = iol.get_all_ambient_data()
    return [values[key] for key in ("near_temp", "far_temp", "near_hum", "far_hum")]


def main():
    name = input("Enter name for test: ").strip() or "test"
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    duration = float(input("Enter test duration in seconds: "))
    if duration <= 0:
        raise ValueError("Test duration must be positive")

    query, power_fields = make_query()
    # Finish possible IO-Link unit HTTP requests before starting the 4 Hz worker.
    water_headers = get_water_headers()
    suffix = str(int(time.time() * 1000))
    root = Path.cwd()
    paths = {kind: root / f"{name}_{kind}_{suffix}.csv" for kind in POLL_PERIODS}
    stop_event = threading.Event()
    power_acquire, power_close = power_reader(query, len(power_fields))
    start_at = time.monotonic() + 0.05
    threads = [
        threading.Thread(target=write_log, name="xitron", args=(
            paths["power"], power_fields, stop_event, POLL_PERIODS["power"],
            power_acquire, start_at), daemon=False),
        threading.Thread(target=write_log, name="water", args=(
            paths["water"], water_headers, stop_event, POLL_PERIODS["water"],
            get_water_values, start_at), daemon=False),
        threading.Thread(target=write_log, name="ambient", args=(
            paths["ambient"], AMBIENT_HEADERS, stop_event, POLL_PERIODS["ambient"],
            get_ambient_values, start_at), daemon=False),
    ]
    print("Writing:\n" + "\n".join(str(p) for p in paths.values()), flush=True)
    try:
        for thread in threads:
            thread.start()
        # Stop after duration without joining workers into the fast acquisition loop.
        stop_event.wait(max(0.0, start_at + duration - time.monotonic()))
    except KeyboardInterrupt:
        print("\nStopping early...", flush=True)
    finally:
        stop_event.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join()
        power_close()
        print("All CSV files closed.", flush=True)


if __name__ == "__main__":
    main()
