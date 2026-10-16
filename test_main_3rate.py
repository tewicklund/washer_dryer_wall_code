"""Hardware-free checks for logger completion and Windows Ctrl+C handling."""

import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ShutdownTests(unittest.TestCase):
    def run_logger(self, interrupt):
        # Run in a child so a regression cannot hang this test runner or send
        # KeyboardInterrupt into the runner itself. No instrument is contacted.
        code = """
import _thread
import sys
import threading
from unittest.mock import Mock, patch

sys.path.insert(0, sys.argv[1])
import main_3rate as logger

interrupt = sys.argv[2] == 'True'
closed = Mock()
reset_calls = []
acquisition_resets = []
def reset(alias):
    reset_calls.append(alias)
    return 'success'
def acquire_power():
    acquisition_resets.append(list(reset_calls))
    return ['100']
timer = threading.Timer(0.4, _thread.interrupt_main) if interrupt else None
with patch('builtins.input', side_effect=['shutdown_test', '3600' if interrupt else '0.3']), \\
     patch.object(logger, 'make_query', return_value=(b'READ?\\n', ['Power'])), \\
     patch.object(logger, 'get_water_headers', return_value=['Water']), \\
     patch.object(logger, 'get_water_values', return_value=['1']), \\
     patch.object(logger, 'get_ambient_values', return_value=['20', '21', '40', '41']), \\
     patch.object(logger.iol, 'reset_picomag_totalizer', side_effect=reset), \\
     patch.object(logger, 'power_reader', return_value=(acquire_power, closed)):
    try:
        if timer:
            timer.start()
        logger.main()
    finally:
        if timer:
            timer.cancel()
            timer.join()
closed.assert_called_once_with()
expected_resets = [logger.iol.HOT_FLOW_SENSOR_ALIAS, logger.iol.COLD_FLOW_SENSOR_ALIAS]
assert reset_calls == expected_resets
assert acquisition_resets and all(calls == expected_resets for calls in acquisition_resets)
assert not any(t.name in ('xitron', 'water', 'ambient') for t in threading.enumerate())
print('Workers stopped and power connection closed.')
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, '-c', code,
                 os.path.dirname(os.path.abspath(__file__)), str(interrupt)],
                cwd=directory, capture_output=True, text=True, timeout=8,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('All CSV files closed.', result.stdout)
            self.assertIn('Workers stopped and power connection closed.', result.stdout)
            self.assertEqual('Stopping early...' in result.stdout, interrupt)
            files = list(Path(directory).glob('*.csv'))
            self.assertEqual(len(files), 3)
            for path in files:
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    rows = list(csv.reader(handle))
                self.assertGreaterEqual(len(rows), 2)
                self.assertEqual(rows[0][1:3], ['epoch_timestamp_ms', 'elapsed_ms'])
                self.assertEqual(rows[1][2], '0')
                self.assertTrue(all(len(row) == len(rows[0]) for row in rows))

    def test_ctrl_c_stops_long_test_and_closes_logs(self):
        self.run_logger(interrupt=True)

    def test_duration_still_stops_test_and_closes_logs(self):
        self.run_logger(interrupt=False)


if __name__ == '__main__':
    unittest.main()
