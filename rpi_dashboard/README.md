# IO-Link Live Dashboard

A standalone, resizable display for the washer-test IO-Link instruments. It reads sensors only when a button is pressed, in a background thread, never logs data, and keeps running when a sensor is missing or a request times out.

The dashboard starts fullscreen with a light, high-contrast theme. Press `Esc` to leave fullscreen and `F11` to toggle it back on or off. Set `window.fullscreen` to `false` in `config.json` if you do not want fullscreen at startup.

## Raspberry Pi setup

Use Raspberry Pi OS with a desktop (64-bit recommended):

```bash
sudo apt update
sudo apt install python3 python3-tk python3-gpiozero
cd rpi_dashboard
python3 dashboard.py --demo
```

Demo mode verifies the layout without a hub or GPIO hardware. Click **Read sensors** to generate one set of simulated readings. Close it, edit `config.json`, then run live:

```bash
python3 dashboard.py
```

No Python packages from pip are required.

## Button wiring

- Use **BCM GPIO17, physical header pin 11** as the input.
- Connect a normally-open momentary button between **3.3 V (physical pin 1)** and **GPIO17 (physical pin 11)**. Never connect 5 V to the GPIO input.
- The code enables an internal pull-down, so the input is low when released and high when pressed. If using an externally driven signal, use 3.3 V logic and a shared ground (for example, physical pin 6).
- `button.gpio_pin` uses BCM numbering. `button.debounce_seconds` defaults to 0.1 seconds to suppress contact bounce.
- Live mode requires GPIO access and fails with an error if the button cannot be initialized. Demo mode skips GPIO setup. Closing the dashboard releases the pin.

The active-high wiring and callbacks use [GPIO Zero's Button API](https://gpiozero.readthedocs.io/en/stable/api_input.html#button).

## Configure before the first live run

1. Change `hub.base_url` to the hub's actual IP address.
2. Confirm the one-based aliases `master1port1` through `master1port8` in `dash_funcs.py`. They follow the supplied function file: temperature, pressure, flow, then ambient.
3. The value functions and decoders now come directly from `dash_funcs.py`. The ambient getter reads parameter 66, converts Celsius to Fahrenheit when needed, and extracts humidity from bytes 3-4.

The configured endpoint is the hub manual's standard JSON Integration endpoint:

`GET /iolink/v1/devices/{deviceAlias}/processdata/value?format=byteArray`

## Sensor functions

Each card names a getter from `dash_funcs.py` using `value_function`. The two cards for each ambient sensor share one combined getter result, so temperature and humidity do not cause duplicate hub requests.

The cold and hot water totalizer cards show accumulated volume in liters, following `io_link_funcs.py`: Picomag bytes 4-7 contain a big-endian float in liters. Values display three decimal places.

## Behavior

- No sensor requests run at startup or on a timer. Press the physical button or click **Read sensors** for one full scan.
- Holding the physical button does not repeat scans. Additional presses during a scan queue additional scans, processed in order.
- Each scan clears the shared reading cache so a new press gets fresh data. Legacy `poll_seconds` settings are ignored.
- Water readings become stale after 25 seconds; ambient readings become stale after 180 seconds.
- Requests are serialized because the hub manual states that its web server processes one connection at a time.
- A failed read leaves the last good value on screen and marks the card unavailable.
- A yellow status dot means the last good value has become stale; red means the latest attempt failed.
- Resize or maximize the window normally. The cards expand to use the available space.

## Optional desktop launcher

After testing, edit `io-link-dashboard.desktop` so both paths point to this folder, then copy it to the Pi desktop and mark it executable:

```bash
chmod +x io-link-dashboard.desktop
```
