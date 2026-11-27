"""Analytical and statistical checks of the isolated CPU pixel model."""

from dataclasses import replace
import math
import statistics
import unittest

from reference_sensor import ReferenceSensor, SensorProfile


class ReferenceSensorTests(unittest.TestCase):
    def test_ideal_initialization_and_constant_input_are_silent(self):
        sensor = ReferenceSensor(2, 1)
        sensor.reset(0, [0.1, 1])
        self.assertEqual(sensor.advance(1, [0.1, 1]).events, ())
        self.assertEqual(sensor.candidate_total, 0)

    def test_ideal_multiple_crossings_residual_and_reversal(self):
        sensor = ReferenceSensor(1, 1, SensorProfile(on_threshold=.25, off_threshold=.25))
        sensor.reset(0, [1])
        first = sensor.advance(1, [math.exp(.625)])
        self.assertEqual([event.p for event in first.events], [1, 1])
        self.assertEqual([event.t_s for event in first.events], [0, 0])
        self.assertAlmostEqual(sensor.states[0].reference_log, .5)
        self.assertEqual(len(sensor.advance(2, [math.exp(.875)]).events), 1)
        self.assertEqual([event.p for event in sensor.advance(3, [1]).events], [-1] * 3)

    def test_asymmetric_polarity_thresholds(self):
        sensor = ReferenceSensor(1, 1, SensorProfile(on_threshold=.2, off_threshold=.3))
        sensor.reset(0, [1])
        self.assertEqual(len(sensor.advance(1, [math.exp(.55)]).events), 2)
        self.assertEqual(len(sensor.advance(2, [1]).events), 1)

    def test_roundoff_at_threshold_does_not_lose_a_crossing(self):
        sensor = ReferenceSensor(1, 1)
        sensor.reset(0, [1])
        self.assertEqual(len(sensor.advance(1, [math.exp(.6)]).events), 3)
        self.assertEqual(len(sensor.advance(2, [1]).events), 3)
        sensor.reset(0, [1])
        self.assertEqual(len(sensor.advance(1, [math.exp(.2 - 1e-10)]).events), 0)

    def test_ideal_fractional_contrast_is_scale_invariant(self):
        counts = []
        for scale in (1e-9, .1, 1, 1000):
            sensor = ReferenceSensor(1, 1)
            sensor.reset(0, [scale])
            counts.append(len(sensor.advance(1, [scale * math.exp(.7)]).events))
        self.assertEqual(counts, [3] * 4)

    def test_seed_zero_is_reproducible_and_seed_changes_instance(self):
        profile = SensorProfile(threshold_sigma=.03, seed=0)
        a = ReferenceSensor(8, 8, profile)
        b = ReferenceSensor(8, 8, profile)
        c = ReferenceSensor(8, 8, replace(profile, seed=1))
        self.assertEqual(a.thresholds, b.thresholds)
        self.assertNotEqual(a.thresholds, c.thresholds)

    def test_mismatch_is_persistent_across_steps_and_reset(self):
        sensor = ReferenceSensor(8, 8, SensorProfile(threshold_sigma=.03))
        thresholds = sensor.thresholds
        sensor.reset(0, [1] * 64)
        first = sensor.advance(1, [math.exp(.7)] * 64)
        sensor.advance(2, [1] * 64)
        sensor.reset(0, [1] * 64)
        self.assertEqual(sensor.thresholds, thresholds)
        self.assertEqual(sensor.advance(1, [math.exp(.7)] * 64), first)

    def test_mismatch_moments_and_polarity_independence(self):
        # 8192 draws per polarity: tolerances exceed six standard errors.
        sensor = ReferenceSensor(128, 64, SensorProfile(threshold_sigma=.03, seed=17))
        on, off = zip(*sensor.thresholds)
        for values in (on, off):
            self.assertLess(abs(statistics.mean(values) - .2), .002)
            self.assertLess(abs(statistics.stdev(values) - .03), .002)
        self.assertLess(abs(statistics.correlation(on, off)), .07)

    def test_threshold_floor_is_explicit(self):
        sensor = ReferenceSensor(32, 32, SensorProfile(threshold_sigma=.5))
        self.assertTrue(all(min(pair) >= .01 for pair in sensor.thresholds))
        self.assertTrue(any(.01 in pair for pair in sensor.thresholds))

    def test_rc_step_response_crosses_half_height_at_tau_log_two(self):
        profile = SensorProfile(on_threshold=.25, bandwidth_white_hz=100)
        sensor = ReferenceSensor(1, 1, profile)
        sensor.reset(0, [1])
        result = sensor.advance(.1, [math.exp(.5)])
        self.assertEqual(len(result.events), 1)  # second level is the unreachable asymptote
        tau = 1 / (2 * math.pi * 100)
        self.assertAlmostEqual(result.events[0].t_s, tau * math.log(2), places=12)

    def test_rc_crossing_times_satisfy_forward_response_for_both_polarities(self):
        for polarity in (1, -1):
            sensor = ReferenceSensor(1, 1, SensorProfile(
                on_threshold=.25, off_threshold=.25, bandwidth_white_hz=100,
                minimum_bandwidth_fraction=1))
            sensor.reset(0, [1])
            result = sensor.advance(.1, [math.exp(polarity)])
            self.assertEqual(len(result.events), 3)
            for index, event in enumerate(result.events, 1):
                response = polarity * (1 - math.exp(-2 * math.pi * 100 * event.t_s))
                self.assertAlmostEqual(response, polarity * index * .25, places=12)
                self.assertEqual(event.p, polarity)

    def test_dark_input_has_longer_equal_contrast_latency(self):
        latencies = []
        for initial in (1, .01):
            sensor = ReferenceSensor(1, 1, SensorProfile(bandwidth_white_hz=100))
            sensor.reset(0, [initial])
            latencies.append(sensor.advance(.1, [initial * math.exp(.5)]).events[0].t_s)
        self.assertGreater(latencies[1], 8 * latencies[0])

    def test_hold_subdivision_does_not_change_rc_events(self):
        profile = SensorProfile(on_threshold=.13, bandwidth_white_hz=37, refractory_s=.001)
        whole = ReferenceSensor(1, 1, profile)
        split = ReferenceSensor(1, 1, profile)
        whole.reset(0, [1])
        split.reset(0, [1])
        expected = whole.advance(.02, [math.exp(.9)])
        actual = []
        for index in range(1, 201):
            actual.extend(split.advance(index * .0001, [math.exp(.9)]).candidates)
        self.assertEqual(len(actual), len(expected.candidates))
        for a, b in zip(actual, expected.candidates):
            self.assertEqual(a.emitted, b.emitted)
            self.assertAlmostEqual(a.t_s, b.t_s, places=12)

    def test_refractory_consumes_reference_without_deferred_burst(self):
        sensor = ReferenceSensor(1, 1, SensorProfile(refractory_s=.01))
        sensor.reset(0, [1])
        burst = sensor.advance(.001, [math.exp(.7)])
        self.assertEqual(len(burst.candidates), 3)
        self.assertEqual(len(burst.events), 1)
        self.assertEqual(burst.refractory_suppressed, 2)
        self.assertEqual(sensor.advance(.1, [math.exp(.7)]).events, ())
        self.assertAlmostEqual(sensor.states[0].reference_log, .6)

    def test_refractory_applies_to_last_emission_across_both_polarities(self):
        sensor = ReferenceSensor(1, 1, SensorProfile(refractory_s=.01))
        sensor.reset(0, [1])
        sensor.advance(.001, [math.exp(.7)])
        off = sensor.advance(.002, [1])
        self.assertEqual(len(off.events), 0)
        self.assertTrue(all(event.p == -1 for event in off.candidates))
        sensor.advance(.02, [1])
        self.assertEqual(len(sensor.advance(.03, [math.exp(.7)]).events), 1)

    def test_reset_clears_dynamics_counters_and_refractory(self):
        sensor = ReferenceSensor(1, 1, SensorProfile(refractory_s=1))
        sensor.reset(0, [1])
        sensor.advance(.01, [math.exp(.7)])
        sensor.reset(0, [1])
        self.assertEqual((sensor.candidate_total, sensor.emitted_total,
                          sensor.refractory_suppressed_total), (0, 0, 0))
        self.assertEqual(len(sensor.advance(.01, [math.exp(.7)]).events), 1)

    def test_dark_offset_reduces_weak_signal_fractional_contrast(self):
        profile = SensorProfile(dark_offset=.1)
        sensor = ReferenceSensor(1, 1, profile)
        sensor.reset(0, [.001])
        self.assertEqual(sensor.advance(1, [.002]).events, ())
        sensor.reset(0, [0])  # finite dark offset supports zero optical intensity
        self.assertEqual(sensor.advance(1, [0]).events, ())

    def test_event_order_and_coordinates(self):
        sensor = ReferenceSensor(2, 2, SensorProfile(bandwidth_white_hz=100))
        sensor.reset(0, [1] * 4)
        result = sensor.advance(.1, [math.exp(.7)] * 4)
        keys = [(event.t_s, event.y, event.x, event.p) for event in result.events]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual({(event.x, event.y) for event in result.events},
                         {(0, 0), (1, 0), (0, 1), (1, 1)})

    def test_capacity_failure_is_atomic_and_not_silent_loss(self):
        sensor = ReferenceSensor(2, 1, max_candidates_per_step=4)
        sensor.reset(0, [1, 1])
        states = sensor.states
        with self.assertRaises(OverflowError):
            sensor.advance(1, [math.exp(.7)] * 2)
        self.assertEqual(sensor.time_s, 0)
        self.assertEqual(sensor.states, states)
        self.assertEqual(sensor.candidate_total, 0)
        self.assertEqual(len(sensor.advance(1, [math.exp(.3)] * 2).events), 2)

    def test_invalid_input_and_time_do_not_mutate_state(self):
        sensor = ReferenceSensor(1, 1)
        with self.assertRaises(ValueError):
            sensor.advance(1, [1])
        sensor.reset(0, [1])
        for time, values in ((0, [1]), (-1, [1]), (math.inf, [1]),
                             (1, [0]), (1, [-1]), (1, [math.nan]), (1, [])):
            with self.assertRaises(ValueError):
                sensor.advance(time, values)
            self.assertEqual(sensor.time_s, 0)
            self.assertEqual(sensor.candidate_total, 0)

    def test_invalid_profile_and_dimensions_are_rejected(self):
        for kwargs in ({"on_threshold": 0}, {"threshold_sigma": -1},
                       {"bandwidth_white_hz": math.nan}, {"minimum_bandwidth_fraction": 0},
                       {"white_intensity": 0}, {"refractory_s": -1}):
            with self.assertRaises(ValueError):
                SensorProfile(**kwargs)
        for width, height in ((0, 1), (1, -1), (1.5, 1)):
            with self.assertRaises(ValueError):
                ReferenceSensor(width, height)


if __name__ == "__main__":
    unittest.main()
