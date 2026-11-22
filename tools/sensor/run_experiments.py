"""Run sensor unit checks and write reproducible CPU-only diagnostic evidence."""

import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import unittest

from reference_sensor import ReferenceSensor, SensorProfile


def source_digest(path: Path) -> str:
    # Canonical newlines keep hashes comparable across Git's Windows checkout modes.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def step_trial(initial: float, profile: SensorProfile, log_change: float = .7) -> dict:
    sensor = ReferenceSensor(1, 1, profile)
    sensor.reset(0, [initial])
    result = sensor.advance(.1, [initial * math.exp(log_change)])
    return {
        "profile": asdict(profile), "initial_intensity": initial,
        "held_intensity": initial * math.exp(log_change), "hold_seconds": .1,
        "candidates": len(result.candidates), "emitted": len(result.events),
        "refractory_suppressed": result.refractory_suppressed,
        "crossings": [asdict(event) for event in result.candidates],
    }


def diagnostics() -> dict:
    population = ReferenceSensor(128, 64, SensorProfile(threshold_sigma=.03, seed=17))
    on, off = zip(*population.thresholds)
    moments = {}
    for name, values in (("ON", on), ("OFF", off)):
        moments[name] = {
            "mean": statistics.mean(values), "sample_stddev": statistics.stdev(values),
            "min": min(values), "max": max(values),
            "floor_count": sum(value == population.profile.minimum_threshold for value in values),
        }
    bandwidth = SensorProfile(bandwidth_white_hz=100)
    refractory = SensorProfile(on_threshold=.1, off_threshold=.1,
                               bandwidth_white_hz=100, refractory_s=.002)
    # Same held step, whole interval versus 200 equal subdivisions.
    a = ReferenceSensor(1, 1, refractory)
    b = ReferenceSensor(1, 1, refractory)
    a.reset(0, [1])
    b.reset(0, [1])
    whole = a.advance(.02, [math.exp(.7)]).candidates
    split = []
    for index in range(1, 201):
        split.extend(b.advance(index * .0001, [math.exp(.7)]).candidates)
    return {
        "mismatch": {"pixels": 8192, "profile": asdict(population.profile),
                     "moments": moments, "ON_OFF_correlation": statistics.correlation(on, off)},
        "ideal_step": step_trial(1, SensorProfile()),
        "bright_step": step_trial(1, bandwidth),
        "dark_step": step_trial(.01, bandwidth),
        "refractory_step": step_trial(1, refractory),
        "dark_offset_step": step_trial(.001, SensorProfile(dark_offset=.1)),
        "hold_partition": {
            "duration_s": .02, "subdivisions": 200, "profile": asdict(refractory),
            "whole_candidates": len(whole), "split_candidates": len(split),
            "same_polarity_and_gate": ([(e.p, e.emitted) for e in whole] ==
                                       [(e.p, e.emitted) for e in split]),
            "max_timestamp_difference_s": (max(abs(a.t_s - b.t_s) for a, b in zip(whole, split))
                                           if len(whole) == len(split) and whole else None),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="optional JSON evidence path")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py")
    tests = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema": "event-lab.sensor-cpu-reference.v1",
        "scope": "CPU-only closed-form generic pixel model for explicitly held optical inputs. "
                 "No Godot integration, real camera calibration, upstream simulator execution, "
                 "or GPU/real-time performance measurement.",
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "machine": platform.machine(), "processor": platform.processor()},
        "source_sha256_lf_utf8": {
            name: source_digest(directory / name)
            for name in ("reference_sensor.py", "test_reference_sensor.py", "run_experiments.py")
        },
        "tests": {"run": tests.testsRun, "failures": len(tests.failures),
                  "errors": len(tests.errors), "skipped": len(tests.skipped),
                  "passed": tests.wasSuccessful()},
        "diagnostics": diagnostics() if tests.wasSuccessful() else None,
    }
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
        print(f"Report: {args.report}")
    else:
        print(encoded)
    return 0 if tests.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
