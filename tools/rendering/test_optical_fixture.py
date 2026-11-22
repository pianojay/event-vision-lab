"""Analytic, spatial-convergence and data-integrity checks for the CPU fixtures."""

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from optical_fixture import (Fixture, camera_ray, encode_f32, exact_edge_pixel,
                             load_fixture, render, sphere_intensity, write_sequence)


class OpticalFixtureTests(unittest.TestCase):
    def test_exact_edge_coverage_and_image_orientation(self):
        config = Fixture(width=4, height=2, edge_x_px=1.25, edge_speed_px_s=0)
        expected_row = [.1, .775, 1., 1.]
        for actual, expected in zip(render(config, 0, exact_edge=True), expected_row * 2):
            self.assertAlmostEqual(actual, expected)

    def test_edge_outside_image(self):
        config = Fixture(width=4, height=2, edge_x_px=-1, edge_speed_px_s=0)
        self.assertEqual(render(config, 0, exact_edge=True), [1.] * 8)
        self.assertEqual(render(replace(config, edge_x_px=5), 0, exact_edge=True), [.1] * 8)

    def test_edge_motion_changes_integrated_flux_by_exact_area(self):
        config = Fixture(width=8, height=3, edge_x_px=2.1, edge_speed_px_s=30)
        first = sum(render(config, 0, exact_edge=True))
        later = sum(render(config, 10_000_000, exact_edge=True))
        self.assertAlmostEqual(first - later, 3 * .3 * .9)

    def test_midpoint_quadrature_error_bound_across_phases(self):
        for n in (1, 2, 4, 8, 16, 32):
            for phase in (.001, .1, .25, .37, .5, .62, .87, .999):
                config = Fixture(width=4, height=2, samples_per_axis=n,
                                 edge_x_px=1 + phase, edge_speed_px_s=0)
                approximate = render(config, 0)
                exact = render(config, 0, exact_edge=True)
                error = max(abs(a - b) for a, b in zip(approximate, exact))
                # Midpoint count differs from the covered fraction by <= 1/(2n).
                self.assertLessEqual(error, .9 / (2 * n) + 1e-14)

    def test_point_samples_can_hide_subpixel_optical_change(self):
        config = Fixture(width=4, height=2, edge_x_px=1.1, edge_speed_px_s=30)
        self.assertEqual(render(config, 0), render(config, 10_000_000))
        self.assertAlmostEqual(exact_edge_pixel(config, 1, 0), .91)
        self.assertAlmostEqual(exact_edge_pixel(config, 1, 10_000_000), .64)

    def test_linear_area_integration_precedes_log(self):
        config = Fixture(width=1, height=1, edge_x_px=.5, edge_speed_px_s=0,
                         dark=.1, bright=1.)
        intensity = render(config, 0, exact_edge=True)[0]
        self.assertAlmostEqual(intensity, .55)
        self.assertGreater(abs(math.log(intensity) - (math.log(.1) + math.log(1)) / 2), .5)

    def test_constant_field_and_zero_are_preserved(self):
        config = Fixture(width=3, height=2, dark=2.5, bright=2.5)
        self.assertEqual(render(config, 0), [2.5] * 6)
        self.assertEqual(render(replace(config, dark=0, bright=0), 0), [0.] * 6)

    def axial_sphere(self):
        return Fixture(scene="sphere", width=3, height=3, camera_position=(0., 1., 5.),
                       camera_pitch_rad=0., light_position=(0., 1., 2.))

    def test_camera_axis_and_top_left_orientation(self):
        config = self.axial_sphere()
        self.assertEqual(camera_ray(config, 1.5, 1.5), (0., 0., -1.))
        ray = camera_ray(config, .5, .5)
        self.assertLess(ray[0], 0)
        self.assertGreater(ray[1], 0)
        self.assertAlmostEqual(sum(v * v for v in ray), 1.)
        rotated = camera_ray(replace(config, camera_yaw_rad=math.pi / 2), 1.5, 1.5)
        self.assertAlmostEqual(rotated[0], 1.)
        self.assertAlmostEqual(rotated[2], 0.)

    def test_axial_sphere_matches_closed_form_and_preserves_hdr(self):
        # Central hit is (0,1,0), normal +Z, lamp at (0,1,2), distance=2.
        expected = .55 * (.035 + 5. * 6. / 5.)
        measured = sphere_intensity(self.axial_sphere(), 1.5, 1.5)
        self.assertAlmostEqual(measured, expected, places=12)
        self.assertGreater(measured, 1.)

    def test_sphere_backlight_and_lamp_off_leave_ambient(self):
        config = self.axial_sphere()
        ambient = config.albedo * config.ambient
        self.assertAlmostEqual(sphere_intensity(replace(config, lamp_strength=0), 1.5, 1.5), ambient)
        self.assertAlmostEqual(sphere_intensity(replace(config, light_position=(0, 1, -3)), 1.5, 1.5), ambient)

    def test_sphere_background_and_repeatability(self):
        config = Fixture(scene="sphere", width=16, height=12, samples_per_axis=2)
        first = encode_f32(render(config, 0))
        self.assertEqual(first, encode_f32(render(config, 16_666_667)))
        self.assertAlmostEqual(sphere_intensity(config, .5, .5), config.background)

    def test_f32_encoding_roundtrip_keeps_hdr_and_order(self):
        values = [0., .1, 1., 4.]
        payload = encode_f32(values)
        self.assertEqual(len(payload), 16)
        self.assertEqual(payload[:4], b"\0\0\0\0")
        for actual, expected in zip(struct.unpack("<4f", payload), values):
            self.assertAlmostEqual(actual, expected, places=7)

    def test_invalid_intensity_is_rejected(self):
        for value in (-.1, math.nan, math.inf, 1e39):
            with self.assertRaises(ValueError):
                encode_f32([value])

    def test_invalid_dimensions_time_and_geometry_are_rejected(self):
        cases = ({"width": 0}, {"height": -1}, {"samples_per_axis": 0},
                 {"sample_times_ns": (0, 0)}, {"sample_times_ns": (-1,)},
                 {"sample_times_ns": (0, 1.5)}, {"sample_times_ns": ()},
                 {"albedo": 2}, {"vertical_fov_deg": 180}, {"bright": math.nan},
                 {"scene": "sphere", "light_position": (0., 1., -1.)})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Fixture(**changes)

    def test_invalid_exact_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            render(self.axial_sphere(), 0, exact_edge=True)

    def test_sequence_manifest_hashes_and_samples_match_payloads(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "sequence"
            config = Fixture(width=3, height=2, edge_x_px=1.25)
            manifest = write_sequence(config, output, exact_edge=True)
            self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
            self.assertFalse(manifest["encoding"]["log_applied"])
            for entry in manifest["frames"]:
                payload = (output / entry["file"]).read_bytes()
                self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(entry["bytes"], 24)
                expected = render(config, entry["sample_time_ns"], exact_edge=True)
                for actual, value in zip(struct.unpack("<6f", payload), expected):
                    self.assertAlmostEqual(actual, value, places=7)

    def test_existing_sequence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "sequence"
            config = Fixture(width=2, height=2)
            write_sequence(config, output)
            before = (output / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write_sequence(config, output)
            self.assertEqual(before, (output / "manifest.json").read_bytes())

    def test_checked_in_fixtures_load_and_typo_is_rejected(self):
        fixtures = Path(__file__).parent / "fixtures"
        for name in ("edge.json", "matte-sphere.json"):
            self.assertIsInstance(load_fixture(fixtures / name), Fixture)
        with tempfile.TemporaryDirectory() as temp:
            typo = Path(temp) / "typo.json"
            typo.write_text('{"widht": 64}')
            with self.assertRaises(TypeError):
                load_fixture(typo)


if __name__ == "__main__":
    unittest.main()
