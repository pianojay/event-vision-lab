"""Classify evidence completeness without inventing performance or fidelity gates."""

import argparse
import json
from pathlib import Path


REQUIRED_COUNTERS = ("samples", "emitted", "skipped", "suppressed", "readout_loss", "capture_overflow",
                     "processing_overflow", "raw_display_overflow", "backlog", "buffer_peak", "cursor_ns", "inference_cursor_ns")


def assess(runtime, launcher, telemetry):
    missing = []
    if launcher.get("exit_code") != 0 or launcher.get("timeout"):
        missing.append("owned Godot process did not complete successfully")
    if not runtime.get("success") or runtime.get("errors"):
        missing.append("runtime scenario assertions failed")
    if runtime.get("measured_wall_seconds", 0) < 600:
        missing.append("less than 600 measured wall seconds after warmup")
    if not launcher.get("ac_power_all_samples"):
        missing.append("AC power was not confirmed for every process sample")
    if runtime.get("output_capture_instrumented"):
        missing.append("output readback instrumentation was enabled during throughput run")
    if runtime.get("event_count", 0) <= 0 or runtime.get("sample_batches", 0) <= 0:
        missing.append("no measured event/sample work")
    final = runtime.get("final_snapshot", {})
    for key in REQUIRED_COUNTERS:
        if key not in final:
            missing.append("missing counter: " + key)
    sample_count = runtime.get("sample_service", {}).get("count", 0)
    if sample_count != runtime.get("sample_batches"):
        missing.append("sample service timing does not cover every measured batch")
    dense_actions = [action for action in runtime.get("actions", []) if action.get("requested", {}).get("strobe_enabled") is True]
    if not dense_actions:
        missing.append("no acknowledged dense-event phase")
    if not any("latency_usec" in action for action in runtime.get("actions", [])):
        missing.append("scripted input-to-render acknowledgement missing")
    if not any(action.get("key") == "R" and "latency_usec" in action for action in runtime.get("actions", [])):
        missing.append("requested sensor reset acknowledgement missing")
    ages = []
    dense_events = 0
    dense_wall_seconds = 0
    previous = None
    for row in telemetry:
        state = row["snapshot"]
        if state.get("inference_cursor_ns") is not None:
            ages.append((int(state["cursor_ns"]) - int(state["inference_cursor_ns"])) * 1e-6)
        if previous and state.get("effective", {}).get("strobe_enabled") and previous["snapshot"].get("effective", {}).get("strobe_enabled"):
            dense_events += row["events"] - previous["events"]
            dense_wall_seconds += row["wall_s"] - previous["wall_s"]
        previous = row
    if dense_events <= 0:
        missing.append("no event work confirmed inside the dense phase")
    initial = runtime.get("initial_snapshot", {})
    deltas = {key: final[key] - initial[key] for key in REQUIRED_COUNTERS if isinstance(final.get(key), (int, float))
              and isinstance(initial.get(key), (int, float)) and key not in ("buffer_peak", "backlog", "cursor_ns", "inference_cursor_ns")}
    return {"schema": "event-lab-sustained-evidence-v1",
            "verdict": "evidence-complete-for-recorded-profile" if not missing else "incomplete",
            "missing": missing, "counter_deltas": deltas,
            "processing_losses_across_resets": runtime.get("observed_processing_losses"),
            "dense_phase_observed_events": dense_events,"dense_phase_observed_wall_seconds":dense_wall_seconds,
            "simulated_per_wall_second": runtime.get("simulated_seconds", 0) / max(runtime.get("measured_wall_seconds", 0), 1e-9),
            "inference_age_ms": {"samples": len(ages), "max": max(ages) if ages else None,
                                 "scope": "simulated acquisition cursor minus inference observation cursor at telemetry samples"},
            "memory": launcher.get("memory"), "hardware": runtime.get("hardware"),
            "source": launcher.get("source"), "settings": final.get("effective"),
            "limits": ["Evidence completeness does not establish optical accuracy or real-time operation.",
                       "Scripted acknowledgement excludes physical input, OS, compositor, and display latency.",
                       "One sustained run describes one profile on one machine; no comparative speedup claim.",
                       "Zero skipped samples can coexist with simulated-time slowdown."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    runtime = json.loads((args.directory / "runtime-report.json").read_text(encoding="utf-8"))
    launcher = json.loads((args.directory / "launcher.json").read_text(encoding="utf-8"))
    telemetry = [json.loads(line) for line in (args.directory / "runtime.jsonl").read_text(encoding="utf-8").splitlines()]
    report = assess(runtime, launcher, telemetry)
    (args.directory / "sustained-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
