import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from output_bounds import OutputAccumulator, analyze_bounds, linear_rgb, maximum_window
from observations import compare_pair, event_features, evaluate
from runtime_report import assess, REQUIRED_COUNTERS
from run_hidden import memory_trend


class OutputBoundsTests(unittest.TestCase):
    def test_static_bright_output_passes(self):
        rgb = np.full((300, 400, 3), 255, dtype=np.uint8)
        report = analyze_bounds(rgb, rgb)
        self.assertEqual(report["union_capable_pixels"], 0)
        self.assertEqual(report["verdict"], "sufficient-bound-pass")

    def test_full_white_flash_is_inconclusive(self):
        low = np.zeros((300, 400, 3), dtype=np.uint8)
        report = analyze_bounds(low, low + 255)
        self.assertEqual(report["maximum_hot_area"]["fraction"], 1)
        self.assertEqual(report["verdict"], "inconclusive")

    def test_opposing_full_field_transitions_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            accumulator = OutputAccumulator(directory, 1)
            for frame in range(13):
                rgb = np.full((256, 341, 3), 255 if frame % 2 else 0, dtype=np.uint8)
                accumulator.consume({"width":341,"height":256,"draw_frame":frame,"wall_s":frame/12},rgb.tobytes())
            report = accumulator.finish(True)
            self.assertEqual(report["general_capable_pixels"], 341*256)
            self.assertEqual(report["verdict"], "inconclusive")

    def test_slow_fade_accumulates_despite_small_adjacent_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            accumulator = OutputAccumulator(directory, 1)
            for frame in range(256):
                rgb = np.full((256, 341, 3), frame, dtype=np.uint8)
                accumulator.consume({"width":341,"height":256,"draw_frame":frame,"wall_s":frame/255},rgb.tobytes())
            self.assertLess(float(linear_rgb([255])[0] - linear_rgb([254])[0]), 0.1)
            report = accumulator.finish(True)
            self.assertEqual(report["verdict"], "inconclusive")
            self.assertEqual(report["frames"], 256)
            self.assertTrue((Path(directory) / "rgb-bounds.npz").is_file())
            self.assertEqual((Path(directory) / "first.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_restricted_gray_output_passes(self):
        low = np.zeros((256, 341, 3), dtype=np.uint8)
        high = low + 20
        report = analyze_bounds(low, high, np.zeros((256,341), dtype=bool))
        self.assertEqual(report["red_capable_pixels"], 0)
        self.assertEqual(report["verdict"], "sufficient-bound-pass")

    def test_unobserved_channel_combinations_remain_conservative(self):
        low = np.zeros((256, 341, 3), dtype=np.uint8)
        self.assertEqual(analyze_bounds(low, low+20)["verdict"], "inconclusive")

    def test_low_luminance_red_change_is_not_ignored(self):
        low = np.zeros((256, 341, 3), dtype=np.uint8)
        high = low.copy()
        high[:, :, 0] = 50
        report = analyze_bounds(low, high)
        self.assertEqual(report["general_capable_pixels"], 0)
        self.assertEqual(report["red_capable_pixels"], 341*256)

    def test_small_flashing_area_passes_area_bound(self):
        low = np.zeros((300, 400, 3), dtype=np.uint8)
        high = low.copy()
        high[75:175, 100:200] = 255
        report = analyze_bounds(low, high)
        self.assertEqual(report["maximum_hot_area"]["pixels"], 10000)
        self.assertEqual(report["verdict"], "sufficient-bound-pass")

    def test_window_maximum_finds_interior_hot_area(self):
        mask = np.zeros((600, 800), dtype=bool)
        mask[200:456, 310:651] = True
        self.assertEqual(maximum_window(mask)["pixels"], 341*256)

    def test_missing_frame_prevents_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            accumulator = OutputAccumulator(directory, 1)
            rgb = np.zeros((2, 2, 3), dtype=np.uint8)
            for frame in (1, 3):
                accumulator.consume({"width":2,"height":2,"draw_frame":frame,"wall_s":frame/3},rgb.tobytes())
            self.assertEqual(accumulator.finish(True)["verdict"], "inconclusive-incomplete-capture")

    def test_invalid_bounds_rejected(self):
        with self.assertRaises(ValueError):
            analyze_bounds(np.ones((2, 2, 3), dtype=np.uint8), np.zeros((2, 2, 3), dtype=np.uint8))


class ObservationTests(unittest.TestCase):
    def test_truth_changes_only_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for side, rows in (("control", "0,0,0,1,0\n"), ("treatment", "0,0,0,1,0\n1,0,10,-1,1\n")):
                path = base / side
                path.mkdir()
                payload = ("x,y,t_ns,p,sequence\n" + rows).encode()
                (path / "events.csv").write_bytes(payload)
                meta = {"stage":"pixel-emitted","complete_relative_to_stage_input":True,"file":"events.csv",
                        "epoch_ns":"0","width":2,"height":2,"stored_count":len(rows.splitlines()),
                        "sha256":hashlib.sha256(payload).hexdigest()}
                (path / "manifest.json").write_text(json.dumps({"captures":{"events":meta}}),encoding="utf-8")
            pair = {"station":"example","control":"control/manifest.json","treatment":"treatment/manifest.json",
                    "roi":[0,0,2,2],"start_ns":0,"end_ns":100,"relative_count_threshold":0.05,
                    "score_truth":{"count_response_difference":True}}
            first = evaluate({"pairs":[pair]},base)["results"][0]
            pair["score_truth"]["count_response_difference"] = False
            second = evaluate({"pairs":[pair]},base)["results"][0]
            self.assertEqual(first["prediction"],second["prediction"])
            self.assertTrue(first["score"]["matches"])
            self.assertFalse(second["score"]["matches"])

    def test_roi_polarity_and_motion_come_from_events(self):
        events = [[1, 2, 0, 1], [3, 4, 100, -1], [50, 50, 50, 1]]
        result = event_features(events, [0, 0, 10, 10], 0, 100)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["on"], 1)
        self.assertEqual(result["centroid_displacement_xy"], [2, 2])
        self.assertEqual(sum(result["temporal_counts"]), 2)

    def test_identical_pair_has_no_count_difference(self):
        feature = event_features([[1, 2, 0, 1]], [0, 0, 10, 10], 0, 100)
        self.assertFalse(compare_pair(feature, feature, 0.05)["predicted_count_response_difference"])

    def test_absence_cannot_provide_centroid(self):
        result = event_features([], [0, 0, 10, 10], 0, 100)
        self.assertIsNone(result["centroid_xy"])


class RuntimeEvidenceTests(unittest.TestCase):
    def test_complete_fixture_can_pass_and_battery_cannot(self):
        state = {key:0 for key in REQUIRED_COUNTERS}
        state.update(effective={"strobe_enabled":True},inference_cursor_ns=None)
        runtime = {"success":True,"stream_finalization":{"finalized":True},"measured_wall_seconds":600,
                   "initial_layout":{"valid":True},"final_layout":{"valid":True},
                   "event_count":100,"sample_batches":2,"sample_service":{"count":2},"final_snapshot":state,
                   "actions":[{"requested":{"strobe_enabled":True}},{"key":"V","latency_usec":1000},
                              {"key":"R","latency_usec":1000}]}
        launcher = {"exit_code":0,"ac_power_all_samples":True,
                    "process_image":{"matches_resolved_engine":True}}
        telemetry = [{"wall_s":200,"events":0,"snapshot":state},{"wall_s":400,"events":100,"snapshot":state}]
        self.assertEqual(assess(runtime,launcher,telemetry)["verdict"],"evidence-complete-for-recorded-profile")
        del launcher["process_image"]
        report = assess(runtime,launcher,telemetry)
        self.assertEqual(report["verdict"],"incomplete")
        self.assertIn("owned process image was not verified against the resolved engine", report["missing"])
        launcher["process_image"] = {"matches_resolved_engine":True}
        runtime["final_layout"]["valid"] = False
        report = assess(runtime,launcher,telemetry)
        self.assertEqual(report["verdict"],"incomplete")
        self.assertIn("full main scene layout was not verified",report["missing"])
        runtime["final_layout"]["valid"] = True
        launcher["ac_power_all_samples"] = False
        self.assertEqual(assess(runtime,launcher,telemetry)["verdict"],"incomplete")

    def test_short_proxy_run_cannot_satisfy_sustained_evidence(self):
        report = assess({"measured_wall_seconds":10,"sample_batches":600,"event_count":1000}, {}, [])
        self.assertEqual(report["verdict"], "incomplete")
        self.assertIn("less than 600 measured wall seconds after warmup", report["missing"])

    def test_memory_slope_is_over_actual_wall_time(self):
        samples = [{"wall_s":t,"private_bytes":100+10*t} for t in (0, 1, 3, 7)]
        self.assertEqual(memory_trend(samples)["least_squares_private_bytes_per_second"], 10)


if __name__ == "__main__":
    unittest.main()
