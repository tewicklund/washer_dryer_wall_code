# Washer/dryer wall logger

Run `python main_3rate.py` with the instruments connected. Power is sampled at
4 Hz, water every 5 seconds, and ambient every 120 seconds (first sample at
test start).

Set `SMARTTHINGS_TOKEN` in the logger's environment using the same token setup
as the Samsung conditioning project. The token needs access to read the combo
device status. `SMARTTHINGS_DEVICE_ID` optionally overrides the default Samsung
combo device ID copied from that project. No dependency on that project's files
is required; deploy `combo_state.py` alongside `main_3rate.py` and `io_link_funcs.py`.
The code uses the existing `requests` dependency.

Each ambient CSV row ends with `combo_state`, fetched from SmartThings once per
sample. Values are `IDLE`, `WASH`, or `DRY`. Rinse/spin count as wash, and drying,
cooldown, and waiting to dry count as dry. Paused cycles retain their phase when
reported. Completed cycles count as idle even if the completion screen remains.
Unknown phases, missing credentials, and API failures produce `UNKNOWN`; ambient
sensor readings are still saved. Status requests are read-only and have bounded
connection/read timeouts with no retries, so a failed request is tried again on
the next sample. For an all-in-one cycle, an ambiguous phase is `UNKNOWN`.

Run hardware-free checks with `python -m unittest test_combo_state test_main_3rate -v`.
The separate `test_io_link_funcs.py` script contacts real instruments.
