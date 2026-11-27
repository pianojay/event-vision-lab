import math
import hashlib
import json
from pathlib import Path
import tempfile
import struct
import unittest
from recorded_input import simulate_frames, compare_events, load_sequence


def f32(x):
    return struct.unpack("<f",struct.pack("<f",x))[0]


def frame(t, values, reset=False, on=0.25, off=0.25):
    params=[0.0]*28
    params[4],params[5]=f32(on),f32(off)
    return t,reset,tuple(f32(x) for x in values),params


class RecordedReferenceTests(unittest.TestCase):
    def reset_archive(self, directory, include_reset):
        times = [(0, True), (500, False)]
        if include_reset:
            times.append((500, True))
        times.append((1000, False))
        payload = struct.pack("<f", 1)
        entries = []
        for index, (time_ns, reset) in enumerate(times):
            entries.append({"time_ns": time_ns, "reset": reset, "file": "intensity.f32",
                            "offset_bytes": index * 4, "length_bytes": 4,
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "parameters": frame(time_ns, [1], reset)[3]})
        manifest = {"schema": "event-lab-pipeline-v1", "effective_config": {
            "profile_name": "gpu-ideal-log-linear-v1", "sensor": "ideal", "trajectory": "log-linear",
            "width": 1, "height": 1, "intensity_floor": 1e-6, "duration_ns": 1000,
            "reset_times_ns": [500]}, "optical_input": {"frames": entries}}
        path = Path(directory) / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        path.with_name("intensity.f32").write_bytes(payload * len(times))
        return path

    def test_requested_reset_must_be_present_in_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_sequence(self.reset_archive(directory, False))

    def test_requested_reset_finishes_interval_before_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            _, frames = load_sequence(self.reset_archive(directory, True))
            self.assertEqual([(f[0], f[1]) for f in frames],
                             [(0, True), (500, False), (500, True), (1000, False)])

    def test_stage_optical_parameters_preserve_sensor_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.reset_archive(directory, True)
            baseline = load_sequence(path)[1]
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for entry in manifest["optical_input"]["frames"]:
                entry["parameters"] += [0.125] * 48
            path.write_text(json.dumps(manifest), encoding="utf-8")
            expanded = load_sequence(path)[1]
            self.assertTrue(all(len(frame[3]) == 76 for frame in expanded))
            self.assertEqual(simulate_frames(baseline, 1), simulate_frames(expanded, 1))
            manifest["optical_input"]["frames"][0]["parameters"].append(0)
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_sequence(path)

    def test_all_crossings_from_actual_rounded_values(self):
        frames=[frame(0,[1],True),frame(1000,[math.exp(1.1)])]
        events=simulate_frames(frames,1)
        self.assertEqual([e[3] for e in events],[1]*4)
        self.assertEqual([e[2] for e in events],[227,455,682,909])

    def test_reference_really_uses_float_archive(self):
        # This value rounds below the mathematical threshold endpoint.
        value=f32(math.exp(0.5))
        events=simulate_frames([frame(0,[1],True),frame(1_000_000,[value],on=0.5)],1)
        self.assertEqual(events,[])  # Rounded input has not reached the exact threshold.

    def test_reset_preserves_finished_endpoint(self):
        frames=[frame(0,[1],True),frame(1000,[math.exp(1.1)]),frame(1000,[math.exp(1.1)],True),frame(2000,[math.exp(1.1)])]
        self.assertEqual(len(simulate_frames(frames,1)),4)

    def test_pre_floor_zero_silent_and_finite(self):
        self.assertEqual(simulate_frames([frame(0,[0],True),frame(1000,[0])],1),[])

    def test_asymmetric_thresholds_and_signs(self):
        events=simulate_frames([frame(0,[1],True),frame(1000,[math.exp(1.1)],off=0.5),frame(2000,[1],off=0.5)],1)
        self.assertEqual([e[3] for e in events],[1]*4+[-1]*2)

    def test_large_clock_origin_local_offsets(self):
        origin=9_000_000_000_000_000
        events=simulate_frames([frame(origin,[1],True),frame(origin+1000,[math.exp(1.1)])],1)
        self.assertEqual([e[2]-origin for e in events],[227,455,682,909])

    def test_spatial_order_before_quantization(self):
        events=simulate_frames([frame(0,[1,1],True),frame(1,[math.exp(0.26),math.exp(0.51)])],2)
        self.assertEqual([e[0] for e in events],[1,0,1])

    def test_exact_return_after_nine_levels(self):
        initial=f32(math.exp(-3.95))
        events=simulate_frames([frame(0,[initial],True,on=0.2,off=0.2),frame(1000,[math.exp(-2.10)],on=0.2,off=0.2),frame(2000,[initial],on=0.2,off=0.2)],1)
        self.assertEqual([e[3] for e in events],[1]*9+[-1]*9)

    def test_lower_threshold_discards_old_residual_without_retroactive_crossing(self):
        frames = [frame(0, [1], True, on=0.2, off=0.2),
                  frame(1000, [math.exp(0.15)], on=0.2, off=0.2),
                  frame(2000, [math.exp(0.16)], on=0.1, off=0.1)]
        self.assertEqual(simulate_frames(frames, 1), [])
        frames.append(frame(3000, [math.exp(0.37)], on=0.1, off=0.1))
        events = simulate_frames(frames, 1)
        self.assertEqual([e[3] for e in events], [1, 1])
        self.assertTrue(all(2000 < e[2] <= 3000 for e in events))

    def test_raise_threshold_reanchors_at_previous_sample(self):
        frames = [frame(0, [1], True, on=0.2),
                  frame(1000, [math.exp(0.15)], on=0.2),
                  frame(2000, [math.exp(0.36)], on=0.3)]
        self.assertEqual(simulate_frames(frames, 1), [])
        frames.append(frame(3000, [math.exp(0.47)], on=0.3))
        events = simulate_frames(frames, 1)
        self.assertEqual(len(events), 1)
        self.assertGreater(events[0][2], 2000)

    def test_off_only_threshold_edit_reanchors_both_polarities(self):
        frames = [frame(0, [1], True, on=0.2, off=0.2),
                  frame(1000, [math.exp(-0.15)], on=0.2, off=0.2),
                  frame(2000, [math.exp(-0.16)], on=0.2, off=0.1)]
        self.assertEqual(simulate_frames(frames, 1), [])
        frames.append(frame(3000, [math.exp(-0.37)], on=0.2, off=0.1))
        events = simulate_frames(frames, 1)
        self.assertEqual([e[3] for e in events], [-1, -1])
        self.assertTrue(all(2000 < e[2] <= 3000 for e in events))

    def test_edit_at_exact_interval_start_preserves_owned_endpoint(self):
        frames = [frame(0, [1], True), frame(1000, [2]), frame(2000, [2], on=0.1)]
        for prior in frames[:2]:
            prior[3][4] = math.log(2)
        self.assertEqual(simulate_frames(frames, 1), [(0, 0, 1000, 1)])

    def test_guard_aborts(self):
        with self.assertRaises(OverflowError):
            simulate_frames([frame(0,[1],True),frame(1000,[math.exp(1.1)])],1,limit=3)

    def test_comparison_separates_missing_sign_and_time(self):
        report=compare_events([(0,0,10,1),(0,0,20,-1)],[(0,0,13,1),(0,0,21,1)],2)
        self.assertEqual((report['missing'],report['extra'],report['timestamp_outside_gate']),(1,1,1))
        self.assertFalse(report['passed'])

if __name__=='__main__':
    unittest.main()
