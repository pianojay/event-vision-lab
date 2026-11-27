"""Run CPU fixture checks and record spatial sampling measurements, not GPU FPS."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import time
import unittest

from optical_fixture import Fixture, encode_f32, load_fixture, render
from test_optical_fixture import OpticalFixtureTests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path,
                        help="New JSON file; existing evidence is not overwritten")
    args = parser.parse_args()
    if args.report.exists():
        parser.error("report already exists; choose a new evidence file")
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OpticalFixtureTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    print(stream.getvalue(), end="")
    tool_dir = Path(__file__).resolve().parent
    root = tool_dir.parents[1]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    config = load_fixture(tool_dir / "fixtures" / "edge.json")
    sweep = []
    for n in (1, 2, 4, 8, 16, 32):
        candidate = replace(config, samples_per_axis=n)
        absolute_errors = []
        log_errors = []
        start = time.perf_counter()
        for timestamp in config.sample_times_ns:
            # Include storage quantization: compare decoded float32 to float64 oracle.
            payload = encode_f32(render(candidate, timestamp))
            measured = struct.unpack(f"<{config.width * config.height}f", payload)
            expected = render(config, timestamp, exact_edge=True)
            absolute_errors.extend(abs(a - b) for a, b in zip(measured, expected))
            log_errors.extend(abs(math.log(a) - math.log(b)) for a, b in zip(measured, expected))
        sweep.append({"samples_per_axis": n,
                      "max_abs_intensity_error": max(absolute_errors),
                      "mean_abs_intensity_error": sum(absolute_errors) / len(absolute_errors),
                      "max_abs_log_intensity_error": max(log_errors),
                      "cpu_diagnostic_wall_seconds": time.perf_counter() - start})
    sphere = load_fixture(tool_dir / "fixtures" / "matte-sphere.json")
    start = time.perf_counter()
    sphere_frames = [encode_f32(render(sphere, t)) for t in sphere.sample_times_ns]
    sphere_seconds = time.perf_counter() - start
    hidden = Fixture(width=4, height=2, edge_x_px=1.1, edge_speed_px_s=30)
    t0, t1 = 0, 10_000_000
    exact0, exact1 = render(hidden, t0, exact_edge=True)[1], render(hidden, t1, exact_edge=True)[1]
    checks_passed = result.wasSuccessful() and len(set(sphere_frames)) == 1
    source_paths = sorted(tool_dir.glob("*.py")) + sorted((tool_dir / "fixtures").glob("*.json"))
    report = {
        "schema": "event-lab-rendering-checks-v1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit, "source_worktree_dirty": dirty,
        "source_sha256": {str(p.relative_to(root)).replace("\\", "/"):
                          hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        "execution": {"python": platform.python_version(), "os": platform.platform(),
                      "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
                      "gpu_executed": False,
                      "scope": "CPU-only analytical/serialization checks; wall times include Python overhead, not a sustained performance benchmark"},
        "tests": {"run": result.testsRun, "failures": len(result.failures),
                  "errors": len(result.errors), "skipped": len(result.skipped),
                  "output": stream.getvalue()},
        "edge_fixture": {"width": config.width, "height": config.height,
                         "times_ns": list(config.sample_times_ns),
                         "oracle": "exact box-area integral in linear intensity, float64",
                         "sweep": sweep},
        "hidden_subpixel_change": {"times_ns": [t0, t1], "exact_intensities": [exact0, exact1],
                                   "exact_delta_log": math.log(exact1 / exact0),
                                   "center_samples_unchanged": render(hidden, t0) == render(hidden, t1)},
        "static_sphere": {"width": sphere.width, "height": sphere.height,
                          "samples_per_axis": sphere.samples_per_axis,
                          "frames": len(sphere_frames), "identical_bytes": len(set(sphere_frames)) == 1,
                          "frame_sha256": hashlib.sha256(sphere_frames[0]).hexdigest(),
                          "cpu_diagnostic_wall_seconds": sphere_seconds},
        "passed": checks_passed,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as target:
        target.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("CPU fixture checks:", "PASS" if checks_passed else "FAIL")
    print("samples/axis | max intensity error | max log error")
    for item in sweep:
        print(f"{item['samples_per_axis']:12d} | {item['max_abs_intensity_error']:.9f} | {item['max_abs_log_intensity_error']:.9f}")
    raise SystemExit(0 if checks_passed else 1)


if __name__ == "__main__":
    main()
