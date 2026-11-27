"""Cross-track CPU probes with explicit adapters; not a shared runtime API."""
import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for track in ('timing', 'sensor', 'rendering'):
    sys.path.insert(0, str(ROOT / 'tools' / track))

from timing_reference import Event, SampledPixel, read_events, write_events
from reference_sensor import ReferenceSensor, SensorProfile
from optical_fixture import Fixture, render, write_sequence


class CompatibilityTests(unittest.TestCase):
    def test_rendered_artifact_to_both_models(self):
        fixture = Fixture(width=3, height=2, edge_x_px=1.1,
                          edge_speed_px_s=30, sample_times_ns=(0, 10_000_000))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'frames'
            manifest = write_sequence(fixture, folder, exact_edge=True)
            frames = []
            for entry in manifest['frames']:
                payload = (folder / entry['file']).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
                frames.append(struct.unpack('<6f', payload))
            sensor = ReferenceSensor(3, 2)
            sensor.reset(0, frames[0])
            held = sensor.advance(.01, frames[1])
            endpoint_events = []
            for index in range(6):
                pixel = SampledPixel()
                pixel.feed(0, math.log(frames[0][index]))
                endpoint_events.extend(Event(e.t, e.p, index % 3, index // 3)
                                       for e in pixel.feed(.01, math.log(frames[1][index])))
            self.assertEqual([(e.x, e.y, e.p) for e in held.events],
                             [(e.x, e.y, e.p) for e in endpoint_events])
            self.assertEqual(len(held.events), 2)
            # Deliberately different trajectories: a hold/jump versus a log ramp.
            self.assertTrue(all(e.t_s == 0 for e in held.events))
            self.assertTrue(all(0 < e.t <= .01 for e in endpoint_events))

    def test_static_sphere_silent_in_both_models(self):
        fixture = Fixture(scene='sphere', width=4, height=3)
        frame = render(fixture, 0)
        self.assertEqual(frame, render(fixture, 10_000_000))
        sensor = ReferenceSensor(4, 3)
        sensor.reset(0, frame)
        self.assertEqual(sensor.advance(.01, frame).events, ())
        for intensity in frame:
            pixel = SampledPixel()
            pixel.feed(0, math.log(intensity))
            self.assertEqual(pixel.feed(.01, math.log(intensity)), [])

    def test_sensor_events_to_timing_capture_preserves_stage_and_epoch(self):
        sensor = ReferenceSensor(2, 1, SensorProfile(
            on_threshold=.1, off_threshold=.1, bandwidth_white_hz=100,
            refractory_s=.002))
        sensor.reset(0, [1, 1])
        result = sensor.advance(.02, [math.exp(.65)] * 2)
        delivered = [Event(e.t_s, e.p, e.x, e.y) for e in result.events]
        self.assertGreater(len(result.candidates), len(delivered))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.csv'
            epoch = 10**18
            metadata = write_events(path, delivered, capacity=len(delivered)-1, epoch_ns=epoch)
            loaded = read_events(path, epoch_ns=epoch)
            self.assertEqual(metadata['candidate_events'], len(delivered))
            self.assertEqual(metadata['overflow_events'], 1)
            self.assertFalse(metadata['complete'])
            self.assertEqual(len(loaded), len(delivered)-1)
            for expected, actual in zip(delivered, loaded):
                self.assertEqual((expected.x, expected.y, expected.p),
                                 (actual.x, actual.y, actual.p))
                self.assertLessEqual(abs(expected.t-actual.t), .50001e-9)
        # Capture's "candidate" count means input records, not sensor candidates.
        self.assertEqual(sensor.candidate_total,
                         sensor.emitted_total + sensor.refractory_suppressed_total)

    def test_held_input_adapter_converges_to_log_ramp(self):
        duration = .01
        expected_times = [duration * level / .65 for level in (.2, .4, .6)]
        errors = []
        for steps in (100, 200):
            sensor = ReferenceSensor(1, 1)
            sensor.reset(0, [1])
            events = []
            dt = duration / steps
            for i in range(steps):
                events.extend(sensor.advance((i+1)*dt, [math.exp(.65*i/steps)]).events)
            self.assertEqual(len(events), 3)
            error = max(abs(e.t_s-t) for e, t in zip(events, expected_times))
            self.assertLessEqual(error, dt + 1e-14)
            errors.append(error)
        self.assertLess(errors[1], errors[0])

    def test_zero_intensity_requires_explicit_policy(self):
        fixture = Fixture(width=1, height=1, dark=0, bright=0)
        frame = render(fixture, 0)
        self.assertEqual(frame, [0])
        with self.assertRaises(ValueError):
            ReferenceSensor(1, 1).reset(0, frame)
        with self.assertRaises(ValueError):
            math.log(frame[0])
        sensor = ReferenceSensor(1, 1, SensorProfile(dark_offset=.01))
        sensor.reset(0, frame)
        self.assertEqual(sensor.advance(.01, frame).events, ())


if __name__ == '__main__':
    unittest.main(verbosity=2)
