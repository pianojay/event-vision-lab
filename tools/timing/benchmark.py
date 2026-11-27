"""Deterministic scalar-signal timing sweep; no engine/GPU performance inference."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
import subprocess
import time

from timing_reference import (PiecewiseLogSignal, SineLogSignal, compare,
                              continuous_events, sampled_events, uniform_times, write_events)


def midpoint_times(signal, base_times, threshold=0.2):
    """Candidate black-box refinement; intentionally has no no-missed-pulse guarantee."""
    cache = {}

    def value(t):
        if t not in cache:
            cache[t] = signal(t)
        return cache[t]

    def refine(a, b, depth):
        m = (a + b) / 2
        error = abs(value(m) - (value(a) + value(b)) / 2)
        if error <= threshold / 4 or depth == 12:
            return [a]
        return refine(a, m, depth + 1) + refine(m, b, depth + 1)

    times = [t for a, b in zip(base_times, base_times[1:]) for t in refine(a, b, 0)]
    times.append(base_times[-1])
    value(times[-1])
    return times, len(cache)


def schedule(signal, hz, strategy):
    times = uniform_times(signal.duration, hz)
    if strategy == "uniform":
        return times, len(times)
    if strategy == "known-boundaries":
        times = sorted(set(times + signal.monotone_times()))
        return times, len(times)
    if strategy == "slope-bound":
        # Global known derivative bound; densification, not render-coupled ESIM.
        rate = max(hz, signal.slope_bound / (0.2 / 4))
        times = uniform_times(signal.duration, rate)
        return times, len(times)
    return midpoint_times(signal, times)


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def clock_report():
    rows = []
    for epoch_s in (0, 3600, 86400, 262144):
        represented_dt = f32(epoch_s + 1 / 120) - f32(epoch_s)
        # Adjacent positive binary32 value; at zero this is the subnormal spacing.
        bits = struct.unpack("I", struct.pack("f", float(epoch_s)))[0]
        next_value = struct.unpack("f", struct.pack("I", bits + 1))[0]
        rows.append({"elapsed_s": epoch_s, "fp32_ulp_s": next_value - f32(epoch_s),
                     "fp32_next_120hz_interval_s": represented_dt,
                     "interval_error_s": represented_dt - 1 / 120})
    return rows


def fixtures(hz, phase):
    center = 0.025 + phase / hz
    for width in (0.001, 0.004, 0.016):
        yield f"pulse-{width * 1000:g}ms", PiecewiseLogSignal([
            (0, 0), (center, 0), (center + width / 2, 0.7), (center + width, 0), (0.1, 0)])
    for frequency in (5, 30, 90):
        yield f"sine-{frequency}hz", SineLogSignal(0.1, frequency, phase=phase * math.tau)


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    gate = 0.0005
    for hz in (120, 240, 480, 960):
        for phase_index in range(16):
            phase = phase_index / 16
            for fixture, signal in fixtures(hz, phase):
                oracle = continuous_events(signal)
                for strategy in ("uniform", "known-boundaries", "slope-bound", "midpoint-adaptive"):
                    start = time.perf_counter()
                    times, evaluations = schedule(signal, hz, strategy)
                    observed = sampled_events(signal, times)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    metrics = compare(oracle, observed, gate)
                    rows.append({"fixture": fixture, "hz": hz, "phase_index": phase_index,
                                 "strategy": strategy, "sample_count": len(times),
                                 "schedule_signal_evaluations": evaluations,
                                 "cpu_schedule_and_sample_ms": elapsed_ms,
                                 "missed_whole_signal": bool(oracle) and not observed, **metrics})
    with (output / "phase-sweep.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for hz in (120, 240, 480, 960):
        for fixture in sorted({r["fixture"] for r in rows}):
            for strategy in ("uniform", "known-boundaries", "slope-bound", "midpoint-adaptive"):
                group = [r for r in rows if (r["hz"], r["fixture"], r["strategy"]) == (hz, fixture, strategy)]
                maxima = [r["abs_error_max_s"] for r in group if r["abs_error_max_s"] is not None]
                summary.append({"hz": hz, "fixture": fixture, "strategy": strategy,
                                "phases": len(group),
                                "phases_without_unmatched_events": sum(r["missing"] == r["extra"] == 0 for r in group),
                                "missed_whole_signal_phases": sum(r["missed_whole_signal"] for r in group),
                                "missing_total": sum(r["missing"] for r in group),
                                "extra_total": sum(r["extra"] for r in group),
                                "reference_event_total": sum(r["reference_events"] for r in group),
                                "observed_event_total": sum(r["observed_events"] for r in group),
                                "absolute_count_error_total": sum(abs(r["reference_events"] - r["observed_events"]) for r in group),
                                "worst_matched_error_s": max(maxima) if maxima else None,
                                "sample_count_min": min(r["sample_count"] for r in group),
                                "sample_count_max": max(r["sample_count"] for r in group)})
    pulse = PiecewiseLogSignal([(0, 0), (0.001, 0), (0.0015, 0.7), (0.002, 0), (0.025, 0)])
    captures = {}
    for name, events in (("reference", continuous_events(pulse)),
                         ("uniform", sampled_events(pulse, uniform_times(pulse.duration, 120))),
                         ("known-boundaries", sampled_events(pulse, schedule(pulse, 120, "known-boundaries")[0]))):
        captures[name] = write_events(output / f"pulse-{name}.csv", events, capacity=100)
    try:
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        base = "unknown"
    report = {"schema": "event-lab-timing-sweep-v1", "base_commit": base,
              "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), Path(__file__).with_name("timing_reference.py"))},
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "processor": platform.processor(), "gpu_used": False},
              "scope": "CPU scalar log-signal oracle/sampler only; no Godot, spatial renderer, GPU or real sensor validation",
              "configuration": {"on_log_threshold": 0.2, "off_log_threshold": 0.2,
                                "duration_s": 0.1, "phases": 16, "matching_gate_s": gate,
                                "pulse_peak_log_change": 0.7, "sine_amplitude_log": 0.7,
                                "phase_definition": "pulse start=0.025+index/(16*hz); sine angle=index*tau/16"},
              "cases": len(rows), "summary": summary, "binary32_clock": clock_report(),
              "example_captures": captures}
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} cases and {len(summary)} summaries to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
