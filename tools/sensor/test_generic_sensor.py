import math
import statistics
import unittest

from generic_sensor import ActivityProfile, GenericSensor
from readout import ReadoutEvent, ReadoutProfile, ReadoutQueue
from reference_sensor import ReferenceSensor, SensorProfile


class GenericTests(unittest.TestCase):
    def test_disabled_activity_preserves_existing_oracle(self):
        profile = SensorProfile(on_threshold=.1, off_threshold=.15, threshold_sigma=.01,
                                bandwidth_white_hz=100, refractory_s=.002, seed=0)
        old = ReferenceSensor(2, 1, profile)
        new = GenericSensor(2, 1, profile)
        for model in (old, new):
            model.reset(0, [1, .1])
        for t, frame in ((.01, [2, .2]), (.02, [.5, .05]), (.03, [1, 1])):
            a, b = old.advance(t, frame), new.advance(t, frame)
            self.assertEqual([(e.x, e.y, e.t_s, e.p, e.emitted) for e in a.candidates],
                             [(e.x, e.y, e.t_s, e.p, e.emitted) for e in b.candidates])

    def test_leak_units_and_partition(self):
        profile = ActivityProfile(leak_log_per_s=.4)
        whole = GenericSensor(1, 1, activity=profile)
        split = GenericSensor(1, 1, activity=profile)
        for sensor in (whole, split):
            sensor.reset(0, [1])
        a = whole.advance(2, [1]).events
        b = tuple(e for i in range(1, 201) for e in split.advance(i/100, [1]).events)
        self.assertEqual(a, b)
        self.assertEqual([e.t_s for e in a], [.5, 1, 1.5, 2])
        self.assertTrue(all(e.p == 1 and e.origin == "leak" for e in a))
        self.assertEqual(whole.optical.states[0].reference_log, 0)

    def test_poisson_partition_seed_reset_and_independence(self):
        activity = ActivityProfile(temporal_on_hz=30, temporal_off_hz=15, seed=0)
        a = GenericSensor(2, 1, activity=activity)
        b = GenericSensor(2, 1, activity=activity)
        c = GenericSensor(2, 1, activity=ActivityProfile(temporal_on_hz=30, seed=0))
        for sensor in (a, b, c):
            sensor.reset(0, [1, 1])
        whole = a.advance(1, [1, 1]).events
        split = tuple(e for i in range(1, 101) for e in b.advance(i/100, [1, 1]).events)
        self.assertEqual(whole, split)
        self.assertEqual([e for e in whole if e.p == 1], list(c.advance(1, [1, 1]).events))
        a.reset(0, [1, 1])
        self.assertEqual(whole, a.advance(1, [1, 1]).events)

    def test_poisson_moments_and_polarities(self):
        n, rate = 1024, 8
        sensor = GenericSensor(n, 1, activity=ActivityProfile(temporal_on_hz=rate,
                                                            temporal_off_hz=rate, seed=17))
        sensor.reset(0, [1]*n)
        events = sensor.advance(1, [1]*n).events
        for polarity in (-1, 1):
            counts = [0]*n
            for event in events:
                if event.p == polarity:
                    counts[event.x] += 1
            self.assertLess(abs(statistics.mean(counts)-rate), 5*math.sqrt(rate/n))
            self.assertLess(abs(statistics.variance(counts)-rate), 2)

    def test_common_gate_does_not_double_count(self):
        sensor = GenericSensor(1, 1, SensorProfile(refractory_s=.3),
                               ActivityProfile(leak_log_per_s=1, temporal_on_hz=20,
                                               temporal_off_hz=20))
        sensor.reset(0, [1])
        events = sensor.advance(1, [2]).events
        self.assertTrue(all(b.t_s-a.t_s >= .3 for a, b in zip(events, events[1:])))
        c = sensor.counters
        self.assertEqual(c["sensor_candidates"], sum(c[f"{k}_candidates"]
                                                     for k in ("optical", "leak", "temporal")))
        self.assertEqual(c["sensor_candidates"], c["pixel_emitted"]+c["refractory_suppressed"])

    def test_capacity_failure_is_atomic_including_rng(self):
        sensor = GenericSensor(1, 1, activity=ActivityProfile(temporal_on_hz=100),
                               max_candidates_per_step=2)
        sensor.reset(0, [1])
        with self.assertRaises(OverflowError):
            sensor.advance(1, [1])
        self.assertEqual(sensor.time_s, 0)
        self.assertEqual(sensor.counters["sensor_candidates"], 0)
        control = GenericSensor(1, 1, activity=sensor.activity, max_candidates_per_step=2)
        control.reset(0, [1])
        self.assertEqual(sensor.advance(.001, [1]), control.advance(.001, [1]))

    def test_invalid_profiles(self):
        for args in ({"temporal_on_hz": -1}, {"leak_log_per_s": math.inf}, {"seed": True}):
            with self.assertRaises(ValueError):
                ActivityProfile(**args)


class ReadoutTests(unittest.TestCase):
    def test_dense_burst_capacity_latency_and_original_time(self):
        queue = ReadoutQueue(ReadoutProfile(capacity_events=2, service_ns=10, latency_ns=5))
        result = queue.advance([ReadoutEvent(x, 0, 0, 1) for x in range(5)], 100)
        self.assertEqual([d.delivered_ns for d in result], [15, 25])
        self.assertEqual([d.event.t_ns for d in result], [0, 0])
        self.assertEqual(queue.snapshot()["readout_dropped"], 3)
        self.assertEqual(queue.snapshot()["readout_pending"], 0)

    def test_backlog_and_partition_invariance(self):
        events = [ReadoutEvent(i, 0, t, 1) for i, t in enumerate((0, 0, 15, 15, 40))]
        a, b = (ReadoutQueue(ReadoutProfile(2, 10, 5)) for _ in range(2))
        whole = a.advance(events, 100)
        split = b.advance(events[:2], 10) + b.advance(events[2:4], 20)
        self.assertEqual(b.snapshot()["readout_pending"], 2)
        split += b.advance(events[4:], 100)
        self.assertEqual(whole, split)
        self.assertEqual(a.snapshot(), b.snapshot())
        self.assertEqual(a.snapshot()["readout_input"], 5)
        self.assertEqual(a.snapshot()["readout_delivered"]+a.snapshot()["readout_dropped"], 5)

    def test_equal_completion_precedes_arrival(self):
        queue = ReadoutQueue(ReadoutProfile(1, 10))
        deliveries = queue.advance([ReadoutEvent(0, 0, 0, 1), ReadoutEvent(0, 0, 10, -1)], 20)
        self.assertEqual([d.delivered_ns for d in deliveries], [10, 20])

    def test_zero_capacity_and_zero_cost(self):
        events = [ReadoutEvent(0, 0, 0, 1)]*3
        drop = ReadoutQueue(ReadoutProfile(0, 0))
        self.assertFalse(drop.advance(events, 0))
        self.assertEqual(drop.snapshot()["readout_dropped"], 3)
        bypass = ReadoutQueue(ReadoutProfile(1, 0))
        self.assertEqual(len(bypass.advance(events, 0)), 3)

    def test_invalid_batch_does_not_partially_submit(self):
        queue = ReadoutQueue()
        with self.assertRaises(ValueError):
            queue.advance([ReadoutEvent(0, 0, 5, 1), ReadoutEvent(0, 0, 4, 1)], 10)
        self.assertEqual(queue.snapshot()["readout_input"], 0)
        with self.assertRaises(ValueError):
            ReadoutProfile(service_ns=.1)


if __name__ == "__main__":
    unittest.main()
