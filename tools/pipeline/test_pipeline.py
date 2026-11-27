import csv
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pipeline import Config, Event, load_config, optical_frame, read_capture, run, simulate, write_capture


def edge(**kwargs):
    values = dict(width=1, height=1, duration_ns=10_000_000, sample_period_ns=10_000_000,
                  edge_start_px=1.0, edge_speed_px_s=-100.0,
                  sensor_parameters={"on_threshold": .5, "off_threshold": .5})
    values.update(kwargs)
    return Config(**values)


class PipelineTests(unittest.TestCase):
    def test_exact_area_edge_and_log_interpolation_have_distinct_times(self):
        expected = math.expm1(.5)*.01
        exact = simulate(edge(trajectory="exact"))[3]
        coarse = simulate(edge())[3]
        midpoint = simulate(edge(sample_period_ns=5_000_000))[3]
        self.assertEqual([len(v) for v in (exact, coarse, midpoint)], [1, 1, 1])
        self.assertAlmostEqual(exact[0].t, expected, places=14)
        self.assertAlmostEqual(coarse[0].t, .005/math.log(2), places=14)
        self.assertAlmostEqual(midpoint[0].t, .005 + .005*(.5-math.log(1.5))/math.log(4/3), places=14)
        self.assertLess(abs(midpoint[0].t-expected), abs(coarse[0].t-expected))

    def test_left_hold_never_uses_future_endpoint(self):
        self.assertEqual(simulate(edge(trajectory="held"))[3], [])
        events = simulate(edge(trajectory="held", sample_period_ns=1_000_000))[3]
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].t, .007)
        self.assertGreater(events[0].t, math.expm1(.5)*.01)

    def test_narrow_pulse_is_missed_then_recovered_by_known_boundaries(self):
        config = edge(scene="pulse", sensor_parameters={"on_threshold": .2, "off_threshold": .2})
        coarse = simulate(config)
        resolved = simulate(replace(config, sampling="known-boundaries"))
        self.assertEqual(len(coarse[3]), 0)
        self.assertEqual(len(coarse[4]), 6)
        self.assertEqual([e.p for e in resolved[3]], [1, 1, 1, -1, -1, -1])
        self.assertEqual(len(resolved[4]), 6)

    def test_exact_area_prevents_midpoint_edge_aliasing(self):
        config = edge(sample_period_ns=500_000, spatial="midpoint", samples_per_axis=1,
                      sensor_parameters={"on_threshold": .2, "off_threshold": .2})
        sampled = simulate(config)
        exact = simulate(replace(config, spatial="exact-area", trajectory="exact"))
        self.assertEqual(len(sampled[3]), len(exact[3]))
        self.assertGreater(max(abs(a.t-b.t) for a,b in zip(sampled[3], exact[3])), .002)

    def test_in_run_reset_preserves_prior_events_but_initializes_new_reference(self):
        for trajectory in ("exact", "log-linear", "held"):
            config = edge(trajectory=trajectory, sample_period_ns=1_000_000,
                          sensor_parameters={"on_threshold": .2, "off_threshold": .2})
            normal = simulate(config)[3]
            reset = simulate(replace(config, reset_times_ns=(5_000_000,)))
            self.assertEqual([e for e in normal if e.t < .005], [e for e in reset[3] if e.t < .005])
            self.assertEqual(reset[5][1]["kind"], "in-run-reset")
            self.assertEqual(len(reset[3]), 2 if trajectory == "held" else 3)
            self.assertNotEqual(normal, reset[3])

    def test_positive_hdr_pulse_preserves_endpoints(self):
        config=edge(scene="pulse",duration_ns=10,sample_period_ns=10,
                    pulse_knots=((0,1e16),(10,1.0)))
        self.assertEqual(optical_frame(config,0),[1e16])
        self.assertEqual(optical_frame(config,10),[1.0])
        self.assertGreater(optical_frame(config,9)[0],0)
        self.assertTrue(simulate(config)[3])

    def test_long_duration_reset_exact_endpoint_serializes(self):
        duration=1266081212287
        reset=900221322849
        config=edge(scene="pulse",trajectory="exact",duration_ns=duration,sample_period_ns=duration,
                    reset_times_ns=(reset,),pulse_knots=((0,1),(reset,1),(duration,math.exp(.2))),
                    sensor_parameters={"on_threshold":.2,"off_threshold":.2})
        with tempfile.TemporaryDirectory() as tmp:
            result=run(config,Path(tmp)/"run")
            self.assertEqual(result["stages"]["capture_stored"],1)
            self.assertEqual((Path(tmp)/"run/events.csv").read_text().splitlines()[1].split(",")[2],str(duration))

    def test_new_stream_reproducible_seed_and_no_state_carry(self):
        config = edge(trajectory="held", sensor="generic-nonideal", sample_period_ns=100_000)
        first = simulate(config)
        second = simulate(replace(config, stream_id="independent", epoch_ns=10**18))
        self.assertEqual(first[2:5], second[2:5])
        self.assertNotEqual(first[5][0]["stream_id"], second[5][0]["stream_id"])

    def test_nonideal_and_capture_loss_are_separate(self):
        config = edge(trajectory="held", sensor="generic-nonideal", sample_period_ns=100_000,
                      sensor_parameters={"on_threshold": .1, "off_threshold": .1,
                                         "threshold_sigma": 0, "refractory_s": .003}, capture_capacity=1)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = run(config, Path(tmp)/"run")
            stages = manifest["stages"]
            self.assertGreater(stages["refractory_suppressed"], 0)
            self.assertGreater(stages["capture_overflow"], 0)
            self.assertEqual(stages["sensor_candidates"], stages["pixel_emitted"]+stages["refractory_suppressed"])
            self.assertEqual(stages["pixel_emitted"], stages["capture_stored"]+stages["capture_overflow"])
            self.assertEqual(stages["readout"], "not modeled")
            self.assertFalse(stages["complete_relative_to_pixel_emissions"])

    def test_roundtrip_large_epoch_quantization_and_stable_ties(self):
        config = edge(epoch_ns=10**18, width=2)
        events = [Event(.0000000006, -1, 1), Event(.0000000007, 1, 0), Event(.00123456789, 1)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"events.csv"
            meta = write_capture(path, events, config, "pixel-emitted")
            loaded = read_capture(path, meta)
            self.assertEqual([(e.x,e.p) for e in loaded], [(e.x,e.p) for e in events])
            for a,b in zip(events,loaded):
                self.assertLessEqual(abs(a.t-b.t), .50001e-9)
            lines = path.read_text().splitlines()
            self.assertEqual(lines[1].split(",")[2], "1000000000000000001")

    def test_empty_capacity_is_valid_but_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(edge(capture_capacity=0), Path(tmp)/"run")
            self.assertEqual(result["stages"]["capture_stored"], 0)
            self.assertEqual(result["stages"]["capture_overflow"], 1)
            self.assertEqual(result["comparison"]["stored_vs_ideal_truth"]["missing"], 1)

    def test_effective_config_roundtrip_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"first"
            first = run(edge(epoch_ns=10**18), output)
            restored = load_config(output/"config.json")
            self.assertEqual(restored.effective(), edge(epoch_ns=10**18).effective())
            command = [sys.executable,"-B",str(Path(__file__).with_name("pipeline.py")),
                       "--config",str(output/"config.json"),"--output",str(Path(tmp)/"second")]
            proc = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual((output/"events.csv").read_bytes(), (Path(tmp)/"second/events.csv").read_bytes())
            self.assertEqual(first["captures"]["events"]["stage"], "pixel-emitted")
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode, 0)

    def test_invalid_config_and_unsupported_combinations_fail(self):
        cases = [dict(width=0),dict(width=True),dict(dark=0),dict(bright=float("nan")),
                 dict(sensor="generic-nonideal",trajectory="exact"),dict(spatial="midpoint",trajectory="exact"),
                 dict(sensor_parameters={"refractory_s":.01}),dict(epoch_ns=2**63-1),
                 dict(reset_times_ns=(5,5)),dict(sample_period_ns=0),dict(schema="future"),
                 dict(scene="pulse",duration_ns=5_000_000)]
        for values in cases:
            with self.subTest(values=values), self.assertRaises((ValueError,TypeError)):
                edge(**values)
        with self.assertRaises(TypeError):
            edge(sensor_parameters={"misspelled":1})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"config.json"
            for data in ([], None, 1, "bad"):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError): load_config(path)

    def test_capture_rejects_bad_coordinates_order_polarity_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"events.csv"
            config = edge(epoch_ns=10**18)
            meta = write_capture(path,[Event(.001,1),Event(.002,-1)],config,"pixel-emitted")
            original = path.read_text()
            for row in ("1,0,1000000000001000000,1,0", "0,0,999999999999999999,1,0",
                        "0,0,1000000000001000000,0,0", "0,0,1000000000001000000,1,5",
                        "0,0,1000000000003000000,1,0"):
                lines=original.splitlines(); lines[1]=row
                path.write_text("\n".join(lines)+"\n")
                changed=dict(meta,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                with self.assertRaises(ValueError): read_capture(path,changed)
            path.write_text(original)
            meta["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): read_capture(path,dict(meta,overflow_count=99))
            with self.assertRaises(ValueError): read_capture(path,dict(meta,stage="display"))
            with self.assertRaises(ValueError): read_capture(path,dict(meta,sha256="bad"))
            invalid_metadata = [dict(meta,epoch_ns=.9),dict(meta,epoch_ns=0),dict(meta,epoch_ns="+0"),
                                dict(meta,complete_relative_to_stage_input=1),dict(meta,stream_id=""),
                                dict(meta,stream_id=None),dict(meta,polarity={"on":-1,"off":1}),
                                dict(meta,polarity={"on":True,"off":-1}),[],None,{}]
            for invalid in invalid_metadata:
                with self.subTest(metadata=invalid), self.assertRaises(ValueError):
                    read_capture(path,invalid)

    def test_resource_limit_aborts_without_successful_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"run"
            with self.assertRaises(OverflowError):
                run(edge(trajectory="exact",candidate_limit_per_step=1,
                         sensor_parameters={"on_threshold":.1,"off_threshold":.1}),output)
            self.assertFalse(output.exists())
            for trajectory in ("exact","log-linear","held"):
                with self.assertRaises(OverflowError):
                    run(edge(trajectory=trajectory,candidate_limit_per_step=1,
                        sensor_parameters={"on_threshold":2e-12,"off_threshold":2e-12,
                                           "minimum_threshold":1e-12}),output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
