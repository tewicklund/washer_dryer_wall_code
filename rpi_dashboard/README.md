# IO-Link Live Dashboard

A standalone, resizable display for the washer-test IO-Link instruments. It polls in a background thread, never logs data, and keeps running when a sensor is missing or a request times out.

The dashboard starts fullscreen with a light, high-contrast theme. Press `Esc` to leave fullscreen and `F11` to toggle it back on or off. Set `window.fullscreen` to `false` in `config.json` if you do not want fullscreen at startup.

## Raspberry Pi setup

Use Raspberry Pi OS with a desktop (64-bit recommended):

```bash
sudo apt update
sudo apt install python3 python3-tk
cd io_link_dashboard
python3 dashboard.py --demo
```

Demo mode verifies the layout without a hub. Close it, edit `config.json`, then run live:

```bash
python3 dashboard.py
```

No Python packages from pip are required.

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

- Water temperature, totalizer, and pressure sensors default to a 5-second interval.
- Ambient temperature and humidity values default to a 60-second interval.
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
