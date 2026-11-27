"""Configurable CPU fixture pipeline. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
for track in ("timing", "sensor", "rendering"):
    sys.path.insert(0, str(ROOT / "tools" / track))
from timing_reference import Event, SampledPixel, continuous_events, compare
from reference_sensor import ReferenceSensor, SensorProfile
from optical_fixture import Fixture, render, encode_f32

SCHEMA = "event-lab-pipeline-v1"
FIELDS = ["x", "y", "t_ns", "p", "sequence"]
MAX_NS = 2**63 - 1


def integer(value, name, minimum=0, maximum=MAX_NS):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")


@dataclass(frozen=True)
class Config:
    schema: str = SCHEMA
    profile_name: str = "edge-ideal-log-linear-v1"
    stream_id: str = "edge-demo"
    width: int = 32
    height: int = 16
    duration_ns: int = 320_000_000
    sample_period_ns: int = 5_000_000
    epoch_ns: int = 0
    scene: str = "edge"
    dark: float = 1.0
    bright: float = 2.0
    edge_start_px: float = 32.0
    edge_speed_px_s: float = -100.0
    pulse_knots: tuple = ((0, 1.0), (3_000_000, 1.0), (4_000_000, 2.0),
                          (5_000_000, 1.0), (10_000_000, 1.0))
    spatial: str = "exact-area"
    samples_per_axis: int = 4
    trajectory: str = "log-linear"
    sampling: str = "uniform"
    sensor: str = "ideal"
    sensor_parameters: dict = field(default_factory=dict)
    reset_times_ns: tuple = ()
    capture_capacity: int = 1_000_000
    candidate_limit_per_step: int = 1_000_000
    comparison_gate_ns: int = 2_000_000

    def __post_init__(self):
        if self.schema != SCHEMA:
            raise ValueError("unsupported config schema")
        if not all(isinstance(v, str) and v.strip() for v in (self.profile_name, self.stream_id)):
            raise ValueError("profile_name and stream_id must be nonempty strings")
        integer(self.width, "width", 1, 256)
        integer(self.height, "height", 1, 256)
        integer(self.duration_ns, "duration_ns", 1, 3_600_000_000_000)
        integer(self.sample_period_ns, "sample_period_ns", 1)
        integer(self.epoch_ns, "epoch_ns", 0, MAX_NS - self.duration_ns)
        integer(self.samples_per_axis, "samples_per_axis", 1, 64)
        integer(self.capture_capacity, "capture_capacity")
        integer(self.candidate_limit_per_step, "candidate_limit_per_step", 1, 1_000_000)
        integer(self.comparison_gate_ns, "comparison_gate_ns")
        if self.scene not in ("edge", "pulse") or self.spatial not in ("exact-area", "midpoint"):
            raise ValueError("unsupported scene or spatial integration")
        if self.trajectory not in ("exact", "log-linear", "held"):
            raise ValueError("unsupported trajectory reconstruction")
        if self.sampling not in ("uniform", "known-boundaries"):
            raise ValueError("unsupported sampling policy")
        if self.sensor not in ("ideal", "generic-nonideal"):
            raise ValueError("unsupported sensor mode")
        if self.sensor == "generic-nonideal" and self.trajectory != "held":
            raise ValueError("generic-nonideal requires held trajectory in v1")
        if self.trajectory == "exact" and self.spatial != "exact-area":
            raise ValueError("exact trajectory requires exact-area optical input")
        for name in ("dark", "bright", "edge_start_px", "edge_speed_px_s"):
            if not isinstance(getattr(self, name), (float, int)) or not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not 1.4e-45 <= min(self.dark, self.bright) <= max(self.dark, self.bright) <= 3.402823466e38:
            raise ValueError("optical intensity must be positive and representable in the float32 archive")
        previous = -1
        for t in self.reset_times_ns:
            integer(t, "reset time", 1, self.duration_ns - 1)
            if t <= previous:
                raise ValueError("reset times must strictly increase")
            previous = t
        previous = -1
        for knot in self.pulse_knots:
            if len(knot) != 2:
                raise ValueError("pulse knots are [time_ns, positive_linear_intensity]")
            t, value = knot
            integer(t, "pulse knot time")
            if t <= previous or not math.isfinite(value) or not 1.4e-45 <= value <= 3.402823466e38:
                raise ValueError("pulse knots must increase and have positive finite intensity")
            previous = t
        if self.scene == "pulse" and (len(self.pulse_knots) < 2 or
                                     self.pulse_knots[0][0] != 0 or
                                     self.pulse_knots[-1][0] != self.duration_ns):
            raise ValueError("pulse knots must span [0,duration_ns]")
        profile = self.effective_sensor()
        if self.sensor == "ideal" and any((profile.threshold_sigma, profile.bandwidth_white_hz,
                                           profile.dark_offset, profile.refractory_s)):
            raise ValueError("ideal mode cannot enable nonideal parameters")
        if len(self.sample_times()) * self.width * self.height > 10_000_000:
            raise ValueError("CPU prototype supports at most 10 million sampled pixel values per run")

    def effective_sensor(self):
        defaults = {"on_threshold": .2, "off_threshold": .2}
        if self.sensor == "generic-nonideal":
            defaults.update(threshold_sigma=.01, bandwidth_white_hz=100.0,
                            refractory_s=.001, dark_offset=.01, seed=17)
        defaults.update(self.sensor_parameters)
        return SensorProfile(**defaults)

    def boundaries(self):
        if self.scene == "pulse":
            return [t for t, _ in self.pulse_knots]
        times = [0, self.duration_ns]
        if self.edge_speed_px_s:
            for x in range(self.width + 1):
                t = (x - self.edge_start_px) / self.edge_speed_px_s * 1e9
                if 0 < t < self.duration_ns:
                    times.append(t)
        return sorted(set(times))

    def sample_times(self):
        count = (self.duration_ns + self.sample_period_ns - 1) // self.sample_period_ns
        if count > 1_000_000:
            raise ValueError("too many optical samples for CPU prototype")
        times = set(range(0, self.duration_ns, self.sample_period_ns))
        times.update((self.duration_ns, *self.reset_times_ns))
        if self.sampling == "known-boundaries":
            times.update(round(t) for t in self.boundaries())
        return sorted(times)

    def effective(self):
        values = asdict(self)
        values["epoch_ns"] = str(self.epoch_ns)
        values["sensor_parameters"] = asdict(self.effective_sensor())
        return json.loads(json.dumps(values, allow_nan=False))


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    if isinstance(data.get("epoch_ns"), str):
        if not data["epoch_ns"].isdigit():
            raise ValueError("epoch_ns string must contain decimal digits")
        data["epoch_ns"] = int(data["epoch_ns"])
    return Config(**data)


def optical_frame(config, time_ns, *, truth=False):
    if config.scene == "edge":
        fixture = Fixture(width=config.width, height=config.height, dark=config.dark,
                          bright=config.bright, edge_x_px=config.edge_start_px,
                          edge_speed_px_s=config.edge_speed_px_s,
                          samples_per_axis=config.samples_per_axis)
        # render() owns integer frame samples; the continuous oracle below owns float time.
        return render(fixture, time_ns, exact_edge=truth or config.spatial == "exact-area")
    knots = config.pulse_knots
    for (a, va), (b, vb) in zip(knots, knots[1:]):
        if a <= time_ns <= b:
            fraction = (time_ns-a)/(b-a)
            value = (1-fraction)*va + fraction*vb
            return [value] * (config.width * config.height)
    raise ValueError("time outside optical trajectory")


class ExactSignal:
    def __init__(self, config, x, start_ns, end_ns):
        self.config, self.x = config, x
        self.start_ns, self.end_ns = start_ns, end_ns

    def __call__(self, local_s):
        t = self.start_ns + local_s * 1e9
        c = self.config
        if c.scene == "edge":
            edge = c.edge_start_px + c.edge_speed_px_s * (t * 1e-9)
            fraction = min(1.0, max(0.0, self.x + 1 - edge))
            value = c.dark * (1 - fraction) + c.bright * fraction
        else:
            t = min(c.duration_ns, max(0, t))
            value = optical_frame(c, t, truth=True)[0]
        return math.log(value)

    def monotone_times(self):
        return [0.0] + [(t - self.start_ns) * 1e-9 for t in self.config.boundaries()
                        if self.start_ns < t < self.end_ns] + [(self.end_ns-self.start_ns)*1e-9]


def exact_events(config):
    profile = config.effective_sensor()
    result = []
    resets = [0, *config.reset_times_ns, config.duration_ns]
    bound = 0
    for start, end in zip(resets, resets[1:]):
        for x in range(config.width):
            signal = ExactSignal(config, x, start, end)
            knots = signal.monotone_times()
            for a, b in zip(knots, knots[1:]):
                change = abs(signal(b)-signal(a))
                if change:
                    bound += math.ceil(change/min(profile.on_threshold,profile.off_threshold))*config.height
                if bound > config.candidate_limit_per_step:
                    raise OverflowError("conservative exact truth event bound exceeds candidate limit before solve")
    for start, end in zip(resets, resets[1:]):
        for x in range(config.width):
            events = continuous_events(ExactSignal(config, x, start, end),
                                       profile.on_threshold, profile.off_threshold)
            for y in range(config.height):
                for e in events:
                    absolute = end*1e-9 if e.t == (end-start)*1e-9 else e.t + start*1e-9
                    result.append(Event(absolute, e.p, x, y))
    return sorted(result, key=lambda e: (e.t, e.y, e.x, e.p))


def simulate(config):
    times = config.sample_times()
    frames = [optical_frame(config, t) for t in times]
    profile = config.effective_sensor()
    candidates, emitted = [], []
    reset_records = [{"time_ns": 0, "kind": "new-stream", "stream_id": config.stream_id}]
    if config.trajectory == "exact":
        emitted = exact_events(config)
        candidates = emitted[:]
        if len(candidates) > config.candidate_limit_per_step:
            raise OverflowError("exact offline solve exceeds candidate limit")
    elif config.trajectory == "log-linear":
        pixels = [SampledPixel(profile.on_threshold, profile.off_threshold)
                  for _ in range(config.width * config.height)]
        for i, (time_ns, frame) in enumerate(zip(times, frames)):
            step = []
            for index, (pixel, value) in enumerate(zip(pixels, frame)):
                if pixel.reference is not None:
                    count_bound = math.floor((abs(math.log(value)-pixel.reference)+1e-12)/min(profile.on_threshold,profile.off_threshold))
                    if len(step)+count_bound > config.candidate_limit_per_step:
                        raise OverflowError("log-linear candidate bound exceeds limit before solve")
                step.extend(Event(e.t, e.p, index % config.width, index // config.width)
                            for e in pixel.feed(time_ns * 1e-9, math.log(value)))
                if time_ns in config.reset_times_ns:
                    pixels[index] = SampledPixel(profile.on_threshold, profile.off_threshold)
                    pixels[index].feed(time_ns * 1e-9, math.log(value))
            if len(step) > config.candidate_limit_per_step:
                raise OverflowError("log-linear step exceeds candidate limit")
            candidates.extend(step)
            if len(candidates) > 2_000_000:
                raise OverflowError("CPU run exceeds 2 million candidates")
        emitted = candidates[:]
    else:
        sensor = ReferenceSensor(config.width, config.height, profile,
                                 config.candidate_limit_per_step)
        sensor.reset(0, frames[0])
        for i in range(len(times)-1):
            # The LEFT sample is held over [t_i,t_i+1), never the future endpoint.
            step = sensor.advance(times[i+1] * 1e-9, frames[i])
            candidates.extend(Event(e.t_s, e.p, e.x, e.y) for e in step.candidates)
            emitted.extend(Event(e.t_s, e.p, e.x, e.y) for e in step.events)
            if len(candidates) > 2_000_000:
                raise OverflowError("CPU run exceeds 2 million candidates")
            if times[i+1] in config.reset_times_ns:
                sensor.reset(times[i+1] * 1e-9, frames[i+1])
    for t in config.reset_times_ns:
        reset_records.append({"time_ns": t, "kind": "in-run-reset", "stream_id": config.stream_id})
    for events in (candidates, emitted):
        events.sort(key=lambda e: (e.t, e.y, e.x, e.p))
    truth = exact_events(config)
    return times, frames, candidates, emitted, truth, reset_records


def write_capture(path, events, config, stage, capacity=None):
    capacity = config.capture_capacity if capacity is None else capacity
    integer(capacity, "capacity")
    rows = []
    previous = -1.0
    for e in events:
        if not 0 <= e.x < config.width or not 0 <= e.y < config.height:
            raise ValueError("event coordinate outside sensor")
        duration_s = config.duration_ns*1e-9
        end_slack = 4*max(math.ulp(e.t),math.ulp(duration_s))
        if e.t < previous or e.t > duration_s + end_slack:
            raise ValueError("event outside ordered stream duration")
        previous = e.t
        if len(rows) < capacity:
            relative_ns = min(config.duration_ns, round(e.t*1e9))
            rows.append((e.x, e.y, config.epoch_ns + relative_ns, e.p, len(rows)))
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return {"schema": "event-lab-capture-v1", "stage": stage,
            "file": Path(path).name, "width": config.width, "height": config.height,
            "epoch_ns": str(config.epoch_ns), "duration_ns": config.duration_ns,
            "stream_id": config.stream_id, "input_count": len(events), "stored_count": len(rows),
            "capacity": capacity, "overflow_count": len(events)-len(rows),
            "complete_relative_to_stage_input": len(events) <= capacity,
            "overflow_policy": "drop-newest; sensor generation continues",
            "timestamp": "signed int64 nanoseconds; integer epoch + rounded run-relative ns",
            "quantization": "nearest ties-to-even; at most 0.5 ns plus binary64 solver roundoff",
            "ordering": "unquantized (t,y,x,p), stable ties; sequence preserves order after quantization",
            "polarity": {"on": 1, "off": -1},
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def read_capture(path, metadata):
    if not isinstance(metadata, dict):
        raise ValueError("capture metadata must be an object")
    required = {"schema", "stage", "epoch_ns", "duration_ns", "width", "height", "input_count",
                "stored_count", "capacity", "overflow_count", "complete_relative_to_stage_input",
                "stream_id", "polarity", "sha256"}
    if not required.issubset(metadata):
        raise ValueError("missing required capture metadata")
    if metadata.get("schema") != "event-lab-capture-v1":
        raise ValueError("unsupported capture schema")
    if metadata.get("stage") not in ("pixel-emitted", "sensor-candidate", "ideal-optical-truth"):
        raise ValueError("unknown event stage")
    epoch_text = metadata["epoch_ns"]
    if not isinstance(epoch_text, str) or not epoch_text or any(c not in "0123456789" for c in epoch_text):
        raise ValueError("capture epoch_ns must be a decimal integer string")
    if type(metadata["complete_relative_to_stage_input"]) is not bool:
        raise ValueError("capture completeness must be a boolean")
    if not isinstance(metadata["stream_id"], str) or not metadata["stream_id"].strip():
        raise ValueError("capture stream_id must be a nonempty string")
    polarity = metadata["polarity"]
    if (not isinstance(polarity, dict) or polarity != {"on": 1, "off": -1} or
        any(type(value) is not int for value in polarity.values())):
        raise ValueError("capture polarity convention must be integer ON +1, OFF -1")
    epoch = int(epoch_text)
    duration = metadata["duration_ns"]
    integer(epoch, "epoch", 0, MAX_NS)
    integer(duration, "duration", 1, MAX_NS-epoch)
    for name in ("width", "height", "input_count", "stored_count", "capacity", "overflow_count"):
        integer(metadata[name], name, 1 if name in ("width", "height") else 0)
    if (metadata["stored_count"] != min(metadata["input_count"], metadata["capacity"]) or
        metadata["overflow_count"] != metadata["input_count"] - metadata["stored_count"] or
        metadata["complete_relative_to_stage_input"] != (metadata["overflow_count"] == 0)):
        raise ValueError("inconsistent capture completeness counters")
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("capture hash mismatch")
    events = []
    previous = epoch
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        if next(reader, None) != FIELDS:
            raise ValueError("invalid CSV header")
        for sequence, row in enumerate(reader):
            if len(row) != 5:
                raise ValueError("malformed event record")
            x, y, t, p, seq = map(int, row)
            if not (0 <= x < metadata["width"] and 0 <= y < metadata["height"] and
                    previous <= t <= epoch + duration and seq == sequence and p in (-1, 1)):
                raise ValueError("invalid event coordinate, polarity, time, order or sequence")
            events.append(Event((t-epoch)*1e-9, p, x, y))
            previous = t
    if len(events) != metadata["stored_count"]:
        raise ValueError("stored event count mismatch")
    return events


def source_identity():
    files = [Path(__file__), ROOT / "tools/timing/timing_reference.py",
             ROOT / "tools/sensor/reference_sensor.py", ROOT / "tools/rendering/optical_fixture.py",
             ROOT / "tools/pipeline/test_pipeline.py", ROOT / "tools/pipeline/validate_pipeline.py",
             ROOT / "tools/pipeline/validate_replay.py", ROOT / "prototype/replay.gd",
             ROOT / "run-pipeline.ps1"]
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return {"commit": revision, "worktree_dirty": dirty,
            "source_sha256_lf": {str(p.relative_to(ROOT)).replace("\\", "/"):
                hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in files},
            "python": sys.version, "platform": platform.platform(), "processor": platform.processor()}


def run(config, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    times, frames, candidates, emitted, truth, resets = simulate(config)
    output.mkdir(parents=True)
    frame_entries = []
    with (output/"intensity.f32").open("wb") as optical_file:
        for t, frame in zip(times, frames):
            payload = encode_f32(frame)
            frame_entries.append({"file": "intensity.f32", "offset_bytes": optical_file.tell(),
                                  "length_bytes": len(payload), "time_ns": t,
                                  "sha256": hashlib.sha256(payload).hexdigest()})
            optical_file.write(payload)
    captures = {}
    for key, events, stage, capacity in (("events", emitted, "pixel-emitted", config.capture_capacity),
                                        ("candidates", candidates, "sensor-candidate", len(candidates)),
                                        ("truth", truth, "ideal-optical-truth", len(truth))):
        captures[key] = write_capture(output / f"{key}.csv", events, config, stage, capacity)
        read_capture(output / f"{key}.csv", captures[key])
    stored = read_capture(output / "events.csv", captures["events"])
    effective = config.effective()
    (output / "config.json").write_text(json.dumps(effective, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    manifest = {"schema": SCHEMA, "effective_config": effective, "source": source_identity(),
        "optical_input": {"shape": [config.height, config.width], "axes": "y,x; top-left origin",
            "units": "positive relative scene-linear intensity", "exposure_duration_ns": 0,
            "archive_dtype": "little-endian float32", "solver_dtype": "binary64",
            "archive_role": "diagnostic rounded samples; solver uses unrounded analytic samples",
            "spatial": config.spatial, "trajectory": config.trajectory, "frames": frame_entries,
            "sample_count": len(times), "skipped_scheduled_samples": 0,
            "unobserved_between_sample_changes": "not generally bounded; compare declared fixture truth"},
        "lifecycle": {"records": resets, "reset_policy": "finish prior interval, then initialize reference/filter without events; retain threshold map and cumulative run counters",
                      "new_stream_policy": "new sensor state and counters; seed regenerates threshold map; caller supplies stream_id and epoch"},
        "stages": {"sensor_candidates": len(candidates), "pixel_emitted": len(emitted),
                   "refractory_suppressed": len(candidates)-len(emitted), "readout": "not modeled",
                   "capture_stored": len(stored), "capture_overflow": len(emitted)-len(stored),
                   "candidate_resource_guard": "abort run on limit; no truncated successful run",
                   "complete_relative_to_pixel_emissions": len(stored) == len(emitted),
                   "complete_relative_to_physical_camera": "not claimed"},
        "captures": captures,
        "comparison": {"reference": "same optical fixture, exact area and continuous trajectory, nominal ideal thresholds, same reset schedule",
                       "gate_ns": config.comparison_gate_ns,
                       "pixel_emitted_vs_ideal_truth": compare(truth, emitted, config.comparison_gate_ns*1e-9),
                       "stored_vs_ideal_truth": compare(truth, stored, config.comparison_gate_ns*1e-9)},
        "limits": ["generic mathematical profiles, no camera calibration", "no noise process, leak or readout arbiter",
                   "held nonideal input is a sampling approximation", "analytic edge and finite-rise pulse only",
                   "offline CPU run, no realtime performance claim", "viewer is event accumulation, not intensity reconstruction"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(load_config(args.config), args.output)
    except (OSError, ValueError, TypeError, OverflowError) as error:
        parser.exit(1, f"Pipeline failed: {error}\n")
    print(json.dumps({"output": str(args.output), "stages": result["stages"],
                      "comparison": result["comparison"]["stored_vs_ideal_truth"]}, indent=2))


if __name__ == "__main__":
    main()
