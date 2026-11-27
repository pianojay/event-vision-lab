"""Offline held-frame adapter for the generic sensor and separate readout stages."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

from generic_sensor import ActivityProfile, GenericSensor
from readout import ReadoutEvent, ReadoutProfile, ReadoutQueue
from reference_sensor import SensorProfile


def simulate_frames(width, height, times_ns, frames, *, pixel=SensorProfile(),
                    activity=ActivityProfile(), readout=ReadoutProfile(),
                    candidate_limit_per_step=1_000_000, capture_capacity=1_000_000,
                    source_loss_count=0, drain_readout=True):
    """Consume row-major linear-intensity frames, holding each LEFT sample.

    The final frame closes the sampling interval and is validated, but has no
    following hold. No interpolation, radiometric rescaling or floor is applied.
    All times are relative to this reset; represent a large epoch separately.
    """
    times_ns, frames = tuple(times_ns), tuple(tuple(frame) for frame in frames)
    if (len(times_ns) < 2 or len(times_ns) != len(frames) or times_ns[0] != 0 or
        any(type(t) is not int or not 0 <= t <= 3_600_000_000_000 for t in times_ns) or
        any(a >= b for a, b in zip(times_ns, times_ns[1:]))):
        raise ValueError("frame times must start at zero and increase through at most one hour")
    for name, value in (("capture_capacity", capture_capacity), ("source_loss_count", source_loss_count)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if type(drain_readout) is not bool:
        raise ValueError("drain_readout must be a boolean")
    sensor = GenericSensor(width, height, pixel, activity, candidate_limit_per_step)
    for frame in frames:
        sensor.optical._input(frame)
    sensor.reset(0, frames[0])
    queue = ReadoutQueue(readout)
    candidates, emitted, delivered = [], [], []
    for index, end_ns in enumerate(times_ns[1:]):
        step = sensor.advance(end_ns * 1e-9, frames[index])
        candidates.extend(step.candidates)
        batch = tuple(ReadoutEvent(e.x, e.y, min(end_ns, max(times_ns[index], round(e.t_s*1e9))),
                                   e.p, e.origin) for e in step.events)
        emitted.extend(batch)
        delivered.extend(queue.advance(batch, end_ns))
    if drain_readout and queue.pending:
        delivered.extend(queue.advance((), queue.pending[-1].delivered_ns))

    def capture(events, stage):
        retained = events[:capture_capacity]
        return {"stage": stage, "input_count": len(events), "stored_count": len(retained),
                "capture_capacity": capture_capacity, "capture_overflow_count": len(events)-len(retained),
                "complete_relative_to_stage_input": len(retained) == len(events),
                "rows": [[e.x, e.y, e.t_ns, e.p, i] for i, e in enumerate(retained)],
                "origins": [e.origin for e in retained]}

    payload = {"times_ns": times_ns, "frames": frames}
    result = {
        "schema": "event-lab-generic-held-report-v1",
        "software": {"python": platform.python_version(), "rng": "stdlib random.Random/expovariate"},
        "effective": {"sensor": sensor.effective(), "readout": queue.effective(),
                      "capture_capacity_per_stage": capture_capacity, "drain_readout": drain_readout,
                      "duration_ns": times_ns[-1], "timestamp_origin": "reset at relative zero",
                      "timestamp_quantization": "binary64 seconds to nearest ties-even nanoseconds",
                      "stages": ["held-linear-optical-input", "sensor-candidate", "pixel-emitted",
                                 "readout-delivered", "capture"]},
        "input": {"sha256": hashlib.sha256(json.dumps(payload, allow_nan=False,
                    separators=(",", ":")).encode()).hexdigest(), "frame_count": len(frames),
                  "source_loss_count": source_loss_count,
                  "source_loss_unit": "caller-declared missing optical frames; not inferred by adapter",
                  "complete_relative_to_declared_source": source_loss_count == 0,
                  "intensity": "linear relative units; supplied values used without rescaling/floor",
                  "trajectory": "left-sample hold; final frame is endpoint only"},
        "counters": {**sensor.counters, **queue.snapshot()},
        "sensor_candidates": [asdict(e) for e in candidates],
        "pixel_capture": capture(emitted, "pixel-emitted"),
        "readout_capture": capture([d.event for d in delivered], "readout-delivered"),
    }
    result["readout_capture"]["delivered_ns"] = [d.delivered_ns for d in delivered[:capture_capacity]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON width,height,times_ns,frames and optional profiles")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.input.read_text(encoding="utf-8"))
    for name, cls in (("pixel", SensorProfile), ("activity", ActivityProfile), ("readout", ReadoutProfile)):
        config[name] = cls(**config.get(name, {}))
    report = simulate_frames(**config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(report["counters"]))


if __name__ == "__main__":
    main()
