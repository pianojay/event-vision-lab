import json
from pathlib import Path
import struct
import sys
import unittest

from generic_sensor import ActivityProfile
from held_frame_adapter import simulate_frames
from readout import ReadoutProfile
from reference_sensor import SensorProfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from pipeline import Config, optical_frame


class AdapterTests(unittest.TestCase):
    def test_actual_cpu_optical_frames_with_noise_readout_and_capture(self):
        config = Config(width=4, height=2, duration_ns=20_000_000, sample_period_ns=5_000_000,
                        edge_start_px=4, edge_speed_px_s=-200)
        times = config.sample_times()
        # The archived FP32 values, not unrounded optical truth, are the input.
        frames = [list(struct.unpack('<8f', struct.pack('<8f', *optical_frame(config, t)))) for t in times]
        report = simulate_frames(4, 2, times, frames, activity=ActivityProfile(temporal_on_hz=100),
                                 readout=ReadoutProfile(2, 1_000_000, 1_000_000),
                                 capture_capacity=1, source_loss_count=3)
        c = report["counters"]
        self.assertGreater(c["optical_candidates"], 0)
        self.assertGreater(c["temporal_candidates"], 0)
        self.assertGreater(c["readout_dropped"], 0)
        self.assertEqual(c["pixel_emitted"], c["readout_input"])
        self.assertEqual(c["readout_input"], c["readout_delivered"]+c["readout_dropped"])
        self.assertEqual(c["readout_pending"], 0)
        self.assertEqual(report["input"]["source_loss_count"], 3)
        self.assertGreater(report["pixel_capture"]["capture_overflow_count"], 0)
        self.assertGreater(report["readout_capture"]["capture_overflow_count"], 0)
        self.assertEqual(report["effective"]["sensor"]["activity"]["temporal_off_hz"], 0)
        self.assertEqual(report["effective"]["sensor"]["pixel"]["refractory_s"], 0)
        self.assertEqual(report, json.loads(json.dumps(report)))

    def test_left_hold_final_frame_and_readout_time(self):
        report = simulate_frames(1, 1, [0, 10, 20], [[1], [2], [1000]],
                                 readout=ReadoutProfile(10, 10, 5))
        self.assertEqual(report["counters"]["optical_candidates"], 3)
        self.assertEqual([row[2] for row in report["pixel_capture"]["rows"]], [10, 10, 10])
        self.assertEqual(report["readout_capture"]["delivered_ns"], [25, 35, 45])
        self.assertEqual([row[2] for row in report["readout_capture"]["rows"]], [10, 10, 10])

    def test_undrained_queue_is_pending_not_loss(self):
        report = simulate_frames(1, 1, [0, 10, 20], [[1], [2], [2]],
                                 readout=ReadoutProfile(10, 100), drain_readout=False)
        self.assertEqual(report["counters"]["readout_pending"], 3)
        self.assertEqual(report["counters"]["readout_dropped"], 0)
        self.assertEqual(report["readout_capture"]["input_count"], 0)

    def test_invalid_input_rejected(self):
        for times, frames in (([1, 2], [[1], [1]]), ([0, 1], [[1], [0]]),
                              ([0, 1], [[1], [1, 2]]), ([0, 1, 1], [[1]]*3)):
            with self.assertRaises(ValueError):
                simulate_frames(1, 1, times, frames)


if __name__ == '__main__':
    unittest.main()
