import math
from pathlib import Path
import tempfile
import unittest

from timing_reference import (Event, PiecewiseLogSignal, SampledPixel, SineLogSignal,
                              compare, continuous_events, read_events, sampled_events,
                              uniform_times, write_events)
from benchmark import clock_report, midpoint_times, schedule


class TimingTests(unittest.TestCase):
    def assertTimes(self, events, times, polarities):
        self.assertEqual([e.p for e in events], polarities)
        self.assertEqual(len(events), len(times))
        for event, t in zip(events, times):
            self.assertAlmostEqual(event.t, t, places=11)

    def test_ramp_crossings_hand_solution(self):
        signal = PiecewiseLogSignal([(0, 0), (1, 0.625)])
        expected = [0.4, 0.8]
        self.assertTimes(continuous_events(signal, 0.25, 0.25), expected, [1, 1])
        self.assertTimes(sampled_events(signal, [0, 1], 0.25, 0.25), expected, [1, 1])

    def test_residual_and_reversal(self):
        pixel = SampledPixel(0.25, 0.25)
        self.assertEqual(pixel.feed(0, 0), [])
        self.assertEqual(len(pixel.feed(1, 0.625)), 2)
        self.assertAlmostEqual(pixel.reference, 0.5)
        self.assertTimes(pixel.feed(2, 0.875), [1.5], [1])
        self.assertTimes(pixel.feed(3, 0), [2 + 0.375 / 0.875, 2 + 0.625 / 0.875, 3], [-1] * 3)

    def test_asymmetric_thresholds(self):
        signal = PiecewiseLogSignal([(0, 0), (1, 0.55), (2, 0)])
        self.assertTimes(continuous_events(signal, 0.2, 0.3),
                         [0.2 / 0.55, 0.4 / 0.55, 1 + 0.45 / 0.55], [1, 1, -1])

    def test_static_and_reset_no_flash(self):
        pixel = SampledPixel()
        self.assertEqual(pixel.feed(0, 3), [])
        self.assertEqual(pixel.feed(1, 3), [])
        self.assertEqual(pixel.feed(2, -4, reset=True), [])
        self.assertEqual(pixel.feed(3, -4), [])

    def test_boundary_owned_once(self):
        signal = PiecewiseLogSignal([(0, 0), (1, 0.4), (2, 0.4), (3, 0)])
        for events in (continuous_events(signal), sampled_events(signal, [0, 1, 2, 3])):
            self.assertTimes(events, [0.5, 1, 2.5, 3], [1, 1, -1, -1])

    def test_batching_same_sample_sequence(self):
        signal = PiecewiseLogSignal([(0, 0), (1, 0.625), (2, 0.875), (3, 0)])
        pixel = SampledPixel(0.25, 0.25)
        grouped = []
        for batch in ([0, 1], [2], [3]):
            grouped.extend(e for t in batch for e in pixel.feed(t, signal(t)))
        self.assertEqual(grouped, sampled_events(signal, [0, 1, 2, 3], 0.25, 0.25))

    def test_hidden_pulse_and_known_boundaries(self):
        signal = PiecewiseLogSignal([(0, 0), (0.001, 0), (0.0015, 0.7), (0.002, 0), (0.025, 0)])
        oracle = continuous_events(signal)
        self.assertEqual(len(oracle), 6)
        self.assertEqual(sampled_events(signal, uniform_times(0.025, 120)), [])
        known = sampled_events(signal, schedule(signal, 120, "known-boundaries")[0])
        self.assertEqual(compare(oracle, known, 1e-10)["matched"], 6)
        # Midpoint-based refinement also cannot discover this hidden excursion.
        midpoint, _ = midpoint_times(signal, uniform_times(0.025, 120))
        self.assertEqual(sampled_events(signal, midpoint), [])

    def test_sine_first_crossing_closed_form(self):
        signal = SineLogSignal(0.25, 1, amplitude=0.7)
        oracle = continuous_events(signal)
        expected = [math.asin(v / 0.7) / math.tau for v in (0.2, 0.4, 0.6)]
        self.assertTimes(oracle, expected, [1, 1, 1])

    def test_sine_timestep_convergence(self):
        signal = SineLogSignal(0.1, 5, phase=0.13)
        reference = continuous_events(signal)
        errors = [compare(reference, sampled_events(signal, uniform_times(0.1, hz)), 0.01)
                  for hz in (120, 240, 480, 960)]
        self.assertTrue(all(e["missing"] == e["extra"] == 0 for e in errors))
        self.assertLess(errors[-1]["abs_error_max_s"], errors[0]["abs_error_max_s"] / 10)

    def test_threshold_touch_at_extremum_is_included(self):
        signal = SineLogSignal(1.0, 1, amplitude=0.2)
        # Equality triggers: a threshold touch at a turning point is an event.
        self.assertTimes(continuous_events(signal), [0.25, 0.5, 0.75, 1.0], [1, -1, -1, 1])
        sparse = sampled_events(signal, uniform_times(1, 10))
        self.assertLess(len(sparse), 4)  # Sampling misses both exact extrema.

    def test_pulse_oracle_hand_solution_all_crossings(self):
        signal = PiecewiseLogSignal([(0, 0), (1, 0.7), (2, 0)])
        expected = [0.2 / 0.7, 0.4 / 0.7, 0.6 / 0.7,
                    1 + 0.3 / 0.7, 1 + 0.5 / 0.7, 2]
        self.assertTimes(continuous_events(signal), expected, [1, 1, 1, -1, -1, -1])

    def test_gate_counts_missing_extra_and_polarity(self):
        ref = [Event(0.1, 1), Event(0.2, -1), Event(0.3, 1)]
        obs = [Event(0.1001, 1), Event(0.2, 1), Event(0.4, 1)]
        result = compare(ref, obs, 0.001)
        self.assertEqual((result["matched"], result["missing"], result["extra"]), (1, 2, 2))
        self.assertIsNone(compare(ref, [], 0.001)["abs_error_p95_s"])
        self.assertEqual(compare([Event(0.1, 1, 1)], [Event(0.1, 1, 2)], 0)["matched"], 0)

    def test_capture_roundtrip_ties_epoch_and_overflow(self):
        source = [Event(0.001, 1, 1, 2), Event(0.001, -1, 0, 0), Event(0.0020000004, 1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            epoch = 10**18
            complete = write_events(path, iter(source), capacity=3, epoch_ns=epoch)
            self.assertTrue(complete["complete"])
            recovered = read_events(path, epoch_ns=epoch)
            self.assertEqual([(e.x, e.y, e.p) for e in recovered], [(e.x, e.y, e.p) for e in source])
            self.assertTrue(all(abs(a.t - b.t) <= 0.5e-9 for a, b in zip(recovered, source)))
            incomplete = write_events(path, iter(source), capacity=1)
            self.assertEqual((incomplete["stored_events"], incomplete["overflow_events"]), (1, 2))
            self.assertFalse(incomplete["complete"])
            self.assertEqual(read_events(path), source[:1])
            self.assertEqual(write_events(path, source, capacity=0)["overflow_events"], 3)
            self.assertEqual(read_events(path), [])

    def test_malformed_and_unordered_capture_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            with self.assertRaises(ValueError):
                write_events(path, [Event(1, 1), Event(0, 1)], capacity=2)
            path.write_text("x,y,t_ns,p,sequence\n0,0,1,1,4\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_events(path)

    def test_invalid_input(self):
        for threshold in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                SampledPixel(threshold)
        pixel = SampledPixel()
        pixel.feed(0, 0)
        for t, value in ((0, 0), (-1, 0), (1, float("nan"))):
            with self.assertRaises(ValueError):
                pixel.feed(t, value)
        with self.assertRaises(ValueError):
            SampledPixel().feed(0, 1e20)
        with self.assertRaises(ValueError):
            continuous_events(PiecewiseLogSignal([(0, 1e20), (1, 1e20 + 1e6)]))

    def test_long_epoch_float32_collapse(self):
        self.assertEqual(clock_report()[-1]["fp32_next_120hz_interval_s"], 0)


if __name__ == "__main__":
    unittest.main()
