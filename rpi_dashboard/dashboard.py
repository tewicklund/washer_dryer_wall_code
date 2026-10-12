#!/usr/bin/env python3
"""Standalone, dependency-free IO-Link graphical dashboard."""

from __future__ import annotations

import argparse
import base64
import json
import queue
import random
import struct
import threading
import time
import tkinter as tk
import dash_funcs
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parent
COLORS = {
    "background": "#edf2f7", "panel": "#ffffff", "panel_alt": "#dbe4ed",
    "text": "#17212b", "muted": "#51606f", "good": "#16865e",
    "warn": "#a16207", "bad": "#c6283d", "cold": "#0067b1", "hot": "#c2410c",
    "border": "#c4ced8", "button_active": "#c9d5e0",
}


def nested_value(data: Any, path: str) -> Any:
    value = data
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def find_byte_array(data: Any) -> list[int]:
    """Accept common IO-Link JSON Integration byte-array response shapes."""
    if isinstance(data, list) and all(isinstance(x, int) and 0 <= x <= 255 for x in data):
        return data
    if isinstance(data, str):
        cleaned = data.replace("0x", "").replace(" ", "").replace(":", "")
        if cleaned and len(cleaned) % 2 == 0:
            return list(bytes.fromhex(cleaned))
    if isinstance(data, dict):
        for key in ("value", "byteArray", "data", "iolink"):
            if key in data:
                try:
                    return find_byte_array(data[key])
                except (ValueError, TypeError, KeyError):
                    pass
        for value in data.values():
            try:
                return find_byte_array(value)
            except (ValueError, TypeError, KeyError):
                pass
    raise ValueError("No byte array found in hub response")


def decode(payload: Any, decoder: dict[str, Any]) -> float:
    kind = decoder.get("type", "bytes")
    if kind == "json":
        raw = float(nested_value(payload, decoder["path"]))
    else:
        values = bytes(find_byte_array(payload))
        offset = int(decoder.get("offset", 0))
        formats = {
            "int16_be": ">h", "uint16_be": ">H", "int16_le": "<h", "uint16_le": "<H",
            "int32_be": ">i", "uint32_be": ">I", "float32_be": ">f", "float32_le": "<f",
        }
        fmt = formats[decoder["format"]]
        size = struct.calcsize(fmt)
        if len(values) < offset + size:
            raise ValueError(f"Need {offset + size} bytes; received {len(values)}")
        raw = float(struct.unpack(fmt, values[offset:offset + size])[0])
    return raw * float(decoder.get("scale", 1.0)) + float(decoder.get("add", 0.0))


@dataclass
class Reading:
    sensor_id: str
    value: float | None
    timestamp: float
    error: str | None = None


class HubClient:
    def __init__(self, config: dict[str, Any], demo: bool = False):
        self.config = config
        self.demo = demo
        self.function_cache: dict[str, tuple[float, Any]] = {}
        hub = config["hub"]
        dash_funcs.configure(hub["base_url"], float(hub.get("timeout_seconds", 1.5)))

    def read(self, sensor: dict[str, Any]) -> float:
        if self.demo:
            center = float(sensor.get("demo_value", 50))
            return center + random.uniform(-0.035, 0.035) * max(abs(center), 1)
        function_name = sensor["value_function"]
        now = time.monotonic()
        cached = self.function_cache.get(function_name)
        cache_seconds = float(sensor.get("shared_cache_seconds", 0))
        if cached and now - cached[0] <= cache_seconds:
            result = cached[1]
        else:
            result = getattr(dash_funcs, function_name)()
            self.function_cache[function_name] = (now, result)
        if result == "UNKNOWN":
            raise RuntimeError("sensor read failed")
        component = sensor.get("component")
        if component is not None:
            parts = [part.strip() for part in str(result).split(":")]
            if len(parts) != 2:
                raise ValueError(f"Expected 'temperature : humidity', got {result!r}")
            result = parts[int(component)]
        return float(result)


class Poller(threading.Thread):
    def __init__(self, client: HubClient, sensors: list[dict[str, Any]], output: queue.Queue):
        super().__init__(daemon=True, name="io-link-poller")
        self.client, self.sensors, self.output = client, sensors, output
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.next_due = {s["id"]: 0.0 for s in sensors}

    def run(self) -> None:
        while not self.stop_event.is_set():
            if self.paused.is_set():
                self.stop_event.wait(0.1)
                continue
            now = time.monotonic()
            due = [s for s in self.sensors if self.next_due[s["id"]] <= now]
            if not due:
                wait = min(self.next_due.values()) - now
                self.stop_event.wait(max(0.02, min(wait, 0.25)))
                continue
            sensor = min(due, key=lambda s: self.next_due[s["id"]])
            started = time.time()
            try:
                value = self.client.read(sensor)
                reading = Reading(sensor["id"], value, started)
            except Exception as exc:  # A dead sensor must not stop the dashboard.
                reading = Reading(sensor["id"], None, started, str(exc))
            self.output.put(reading)
            self.next_due[sensor["id"]] = time.monotonic() + float(sensor.get("poll_seconds", 1.0))

    def stop(self) -> None:
        self.stop_event.set()


class SensorCard(tk.Frame):
    def __init__(self, parent: tk.Widget, sensor: dict[str, Any]):
        super().__init__(parent, bg=COLORS["panel"], highlightthickness=1,
                         highlightbackground=COLORS["border"], padx=18, pady=14)
        self.sensor = sensor
        self.last_success = 0.0
        self.columnconfigure(0, weight=1)
        self.name = tk.Label(self, text=sensor["name"].upper(), anchor="w",
                             bg=COLORS["panel"], fg=COLORS["muted"], font=("TkDefaultFont", 14, "bold"))
        self.name.grid(row=0, column=0, sticky="ew")
        self.dot = tk.Label(self, text="●", bg=COLORS["panel"], fg=COLORS["warn"], font=("TkDefaultFont", 16))
        self.dot.grid(row=0, column=1, sticky="e")
        self.value = tk.Label(self, text="--", anchor="w", bg=COLORS["panel"], fg=sensor.get("color", COLORS["text"]),
                              font=("TkDefaultFont", 39, "bold"))
        self.value.grid(row=1, column=0, sticky="w", pady=(9, 5))
        self.unit = tk.Label(self, text=sensor.get("unit", ""), anchor="w", bg=COLORS["panel"],
                             fg=COLORS["muted"], font=("TkDefaultFont", 20))
        self.unit.grid(row=1, column=1, sticky="sw", padx=(8, 0), pady=(0, 10))
        self.status = tk.Label(self, text="Waiting for first reading", anchor="w", bg=COLORS["panel"],
                               fg=COLORS["muted"], font=("TkDefaultFont", 12))
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew")

    def update_reading(self, reading: Reading) -> None:
        if reading.error:
            self.dot.config(fg=COLORS["bad"])
            self.status.config(text=f"Unavailable: {reading.error}", fg=COLORS["bad"])
            return
        self.last_success = reading.timestamp
        decimals = int(self.sensor.get("decimals", 1))
        self.value.config(text=f"{reading.value:.{decimals}f}")
        self.dot.config(fg=COLORS["good"])
        self.status.config(text=f"Updated {time.strftime('%I:%M:%S %p', time.localtime(reading.timestamp)).lstrip('0')}",
                           fg=COLORS["muted"])

    def refresh_age(self) -> None:
        if self.last_success and time.time() - self.last_success > float(self.sensor.get("stale_seconds", 8)):
            self.dot.config(fg=COLORS["warn"])
            self.status.config(text=f"Stale - last update {int(time.time() - self.last_success)} s ago", fg=COLORS["warn"])


class Dashboard(tk.Tk):
    def __init__(self, config: dict[str, Any], demo: bool):
        super().__init__()
        self.config_data = config
        self.title(config.get("window", {}).get("title", "Washer Test - Live Conditions"))
        self.geometry(config.get("window", {}).get("geometry", "1050x650"))
        self.minsize(660, 440)
        self.fullscreen = bool(config.get("window", {}).get("fullscreen", True))
        self.attributes("-fullscreen", self.fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)
        self.bind("<F11>", self.toggle_fullscreen)
        self.configure(bg=COLORS["background"],cursor="none")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.readings: queue.Queue[Reading] = queue.Queue()
        self.cards: dict[str, SensorCard] = {}

        header = tk.Frame(self, bg=COLORS["background"], padx=22, pady=17)
        header.pack(fill="x")
        tk.Label(header, text=config.get("window", {}).get("heading", "LIVE TEST CONDITIONS"), bg=COLORS["background"],
                 fg=COLORS["text"], font=("TkDefaultFont", 24, "bold")).pack(side="left")
        self.pause_button = tk.Button(header, text="Pause", command=self.toggle_pause, bg=COLORS["panel_alt"],
                                      fg=COLORS["text"], activebackground=COLORS["button_active"],
                                      activeforeground=COLORS["text"], font=("TkDefaultFont", 13, "bold"),
                                      relief="flat", padx=20, pady=8)
        self.pause_button.pack(side="right")
        self.mode_label = tk.Label(header, text="DEMO" if demo else "LIVE", bg=COLORS["background"],
                                   fg=COLORS["warn"] if demo else COLORS["good"], font=("TkDefaultFont", 13, "bold"))
        self.mode_label.pack(side="right", padx=18)

        self.grid_frame = tk.Frame(self, bg=COLORS["background"], padx=20, pady=4)
        self.grid_frame.pack(fill="both", expand=True)
        for index, sensor in enumerate(config["sensors"]):
            card = SensorCard(self.grid_frame, sensor)
            self.cards[sensor["id"]] = card
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
        rows = (len(config["sensors"]) + 1) // 2
        for row in range(rows): self.grid_frame.rowconfigure(row, weight=1, uniform="rows")
        for col in range(2): self.grid_frame.columnconfigure(col, weight=1, uniform="cols")

        self.poller = Poller(HubClient(config, demo), config["sensors"], self.readings)
        self.poller.start()
        self.after(100, self.process_readings)
        self.after(1000, self.refresh_ages)

    def process_readings(self) -> None:
        try:
            while True:
                reading = self.readings.get_nowait()
                self.cards[reading.sensor_id].update_reading(reading)
        except queue.Empty:
            pass
        self.after(100, self.process_readings)

    def refresh_ages(self) -> None:
        for card in self.cards.values(): card.refresh_age()
        self.after(1000, self.refresh_ages)

    def toggle_pause(self) -> None:
        if self.poller.paused.is_set():
            self.poller.paused.clear(); self.pause_button.config(text="Pause")
        else:
            self.poller.paused.set(); self.pause_button.config(text="Resume")

    def exit_fullscreen(self, _event=None) -> None:
        self.fullscreen = False
        self.attributes("-fullscreen", False)

    def toggle_fullscreen(self, _event=None) -> None:
        self.fullscreen = not self.fullscreen
        self.attributes("-fullscreen", self.fullscreen)

    def close(self) -> None:
        self.poller.stop()
        self.destroy()


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {"hub", "sensors"}
    if not required <= config.keys() or not config["sensors"]:
        raise ValueError("Configuration requires 'hub' and a non-empty 'sensors' list")
    ids = [s["id"] for s in config["sensors"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Every sensor id must be unique")
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Resizable IO-Link sensor dashboard")
    parser.add_argument("--config", type=Path, default=APP_DIR / "config.json")
    parser.add_argument("--demo", action="store_true", help="show simulated readings without a hub")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        Dashboard(config, args.demo).mainloop()
    except Exception as exc:
        try: messagebox.showerror("IO-Link Dashboard", str(exc))
        except tk.TclError: print(f"IO-Link Dashboard: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
