"""Independent ideal log-linear reference driven by archived FP32 optical inputs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
from collections import defaultdict

PROFILE = "gpu-ideal-log-linear-v1"
# Before scene comparisons: zero count/polarity mismatch, <=100 us event time error.
# The time gate covers FP32 log/reference roundoff on sampled low-slope 3D pixels.
# It is an experimental acceptance gate, not a universal error bound.
DEFAULT_GATE_NS = 100_000


def load_sequence(manifest_path):
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    config = manifest["effective_config"]
    if manifest.get("schema") != "event-lab-pipeline-v1" or config.get("profile_name") != PROFILE:
        raise ValueError("unsupported recorded-input profile")
    if config.get("sensor") != "ideal" or config.get("trajectory") != "log-linear":
        raise ValueError("recorded-input adapter supports ideal log-linear only")
    width, height = config["width"], config["height"]
    if type(width) is not int or type(height) is not int or not 1 <= width <= 256 or not 1 <= height <= 256:
        raise ValueError("invalid dimensions")
    if not 0 < config["intensity_floor"] == 1e-6:
        raise ValueError("unsupported floor")
    config["intensity_floor"] = struct.unpack("<f",struct.pack("<f",config["intensity_floor"]))[0]
    data = (path.parent / "intensity.f32").read_bytes()
    frames = []
    offset = 0
    last_ns = -1
    for entry in manifest["optical_input"]["frames"]:
        t_ns = entry["time_ns"]
        reset = entry.get("reset")
        if type(t_ns) is not int or not 0 <= t_ns <= config["duration_ns"] or t_ns < last_ns or type(reset) is not bool:
            raise ValueError("invalid frame time/reset")
        if t_ns == last_ns and not reset:
            raise ValueError("same-time sample must initialize reset")
        if not frames and (t_ns != 0 or not reset):
            raise ValueError("first sample must initialize at zero")
        length = width * height * 4
        if entry["file"] != "intensity.f32" or entry["offset_bytes"] != offset or entry["length_bytes"] != length:
            raise ValueError("invalid optical layout")
        payload = data[offset:offset+length]
        if len(payload) != length or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("optical frame hash mismatch")
        values = struct.unpack(f"<{width*height}f", payload)
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("invalid pre-floor intensity")
        params = entry["parameters"]
        if len(params) != 28 or any(not math.isfinite(v) for v in params) or params[4] <= 0 or params[5] <= 0:
            raise ValueError("invalid archived parameters")
        params = list(struct.unpack("<28f",struct.pack("<28f",*params)))
        frames.append((t_ns, reset, values, params))
        offset += length
        last_ns = t_ns
    if offset != len(data) or last_ns != config["duration_ns"]:
        raise ValueError("incomplete optical archive")
    return manifest, frames


def simulate_frames(frames, width, floor=1e-6, limit=2_000_000):
    """Independent binary64 reference with anchored integer threshold counts."""
    anchor = previous = None
    on_counts = off_counts = None
    previous_thresholds = None
    start_ns = 0
    events = []
    for t_ns, reset, intensity, params in frames:
        current = [math.log(max(value, floor)) for value in intensity]
        thresholds = params[4:6]
        if reset:
            anchor = current.copy()
            on_counts = [0] * len(current)
            off_counts = [0] * len(current)
        else:
            if anchor is None or previous is None or t_ns <= start_ns:
                raise ValueError("uninitialized or unordered reference input")
            if thresholds != previous_thresholds:
                anchor = [a+n*previous_thresholds[0]-m*previous_thresholds[1]
                          for a,n,m in zip(anchor,on_counts,off_counts)]
                on_counts = [0] * len(current)
                off_counts = [0] * len(current)
            step = []
            for index, log_i in enumerate(current):
                offset = on_counts[index]*thresholds[0] - off_counts[index]*thresholds[1]
                relative = log_i-anchor[index]
                prev_relative = previous[index]-anchor[index]
                difference = relative-offset
                polarity = 1 if difference >= 0 else -1
                threshold = thresholds[0] if polarity == 1 else thresholds[1]
                count = math.floor(abs(difference)/threshold)
                if len(events)+len(step)+count > limit:
                    raise OverflowError("reference candidate bound exceeded")
                for level in range(1,count+1):
                    crossing = (on_counts[index]+(level if polarity>0 else 0))*thresholds[0] - (off_counts[index]+(level if polarity<0 else 0))*thresholds[1]
                    fraction = (crossing-prev_relative)/(relative-prev_relative) if abs(relative-prev_relative)>1e-10 else 1.0
                    step.append((min(1.0,max(0.0,fraction)),index//width,index%width,polarity))
                if polarity>0: on_counts[index] += count
                else: off_counts[index] += count
            step.sort()
            events.extend((x,y,start_ns+round(fraction*(t_ns-start_ns)),polarity)
                          for fraction,y,x,polarity in step)
        previous = current
        previous_thresholds = thresholds
        start_ns = t_ns
    return events


def diagnostic_events(manifest_path, manifest, frames):
    """Reconstruct complete GPU emissions for comparison even when capture drops rows."""
    path = Path(manifest_path).parent / "diagnostics.f32"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["diagnostics"]["sha256"]:
        raise ValueError("diagnostic hash mismatch")
    width, height = manifest["effective_config"]["width"], manifest["effective_config"]["height"]
    expected_length = width * height * 32 * len(frames)
    if len(data) != expected_length:
        raise ValueError("diagnostic length mismatch")
    events = []
    start_ns = 0
    for frame_index, (t_ns, reset, _, params) in enumerate(frames):
        offset = frame_index * width * height * 32
        if manifest["optical_input"]["frames"][frame_index]["diagnostic_offset_bytes"] != offset:
            raise ValueError("diagnostic offset mismatch")
        step = []
        for index in range(width * height):
            ref, prev, curr, signed_count, n_on, n_off, c_on, c_off = struct.unpack_from("<8f", data, offset + 32 * index)
            if any(not math.isfinite(v) for v in (ref, prev, curr, signed_count)) or signed_count != int(signed_count):
                raise ValueError("invalid diagnostic record")
            if reset and signed_count:
                raise ValueError("reset emitted events")
            count = abs(int(signed_count))
            if len(events) + len(step) + count > 2_000_000:
                raise OverflowError("diagnostic event bound exceeded")
            polarity = 1 if signed_count >= 0 else -1
            threshold = params[4] if polarity == 1 else params[5]
            for level in range(1, count + 1):
                on_level = struct.unpack("<f",struct.pack("<f",(n_on+(level if polarity>0 else 0))*c_on))[0]
                off_level = struct.unpack("<f",struct.pack("<f",(n_off+(level if polarity<0 else 0))*c_off))[0]
                crossing = struct.unpack("<f",struct.pack("<f",on_level-off_level))[0]
                fraction = (crossing - prev) / (curr - prev) if abs(curr-prev) > 1e-10 else 1.0
                if not 0 <= fraction <= 1:
                    raise ValueError("diagnostic crossing outside interval")
                step.append((min(1.0, max(0.0, fraction)), index // width, index % width, polarity))
        step.sort()
        events.extend((x, y, start_ns + round(fraction * (t_ns-start_ns)), p) for fraction,y,x,p in step)
        start_ns = t_ns
    return events


def compare_events(reference, actual, gate_ns=DEFAULT_GATE_NS):
    groups = []
    for stream in (reference, actual):
        grouped = defaultdict(list)
        for x,y,time_ns,p in stream:
            grouped[x,y,p].append(time_ns)
        groups.append(grouped)
    missing = extra = outside = 0
    errors = []
    for key in groups[0].keys() | groups[1].keys():
        wanted, found = groups[0][key], groups[1][key]
        missing += max(0,len(wanted)-len(found))
        extra += max(0,len(found)-len(wanted))
        for a,b in zip(wanted,found):
            error = abs(a-b)
            errors.append(error)
            outside += error > gate_ns
    def polarities(events):
        return {"on":sum(e[3]==1 for e in events),"off":sum(e[3]==-1 for e in events)}
    return {"reference_count":len(reference),"actual_count":len(actual),"reference_polarity":polarities(reference),
            "actual_polarity":polarities(actual),"missing":missing,"extra":extra,
            "timestamp_max_error_ns":max(errors,default=0),"timestamp_mean_error_ns":sum(errors)/len(errors) if errors else 0,
            "timestamp_outside_gate":outside,"gate_ns":gate_ns,"passed":missing==extra==outside==0}


def evaluate(manifest_path, gate_ns=DEFAULT_GATE_NS):
    manifest, frames = load_sequence(manifest_path)
    config = manifest["effective_config"]
    reference = simulate_frames(frames,config["width"],config["intensity_floor"])
    generated = diagnostic_events(manifest_path,manifest,frames)
    meta = manifest["captures"]["events"]
    event_path = Path(manifest_path).parent / "events.csv"
    if meta.get("schema") != "event-lab-capture-v1" or meta.get("stage") != "pixel-emitted" or hashlib.sha256(event_path.read_bytes()).hexdigest() != meta["sha256"]:
        raise ValueError("invalid event capture identity or hash")
    with event_path.open(newline="") as f:
        reader = csv.reader(f)
        if next(reader) != ["x","y","t_ns","p","sequence"]:
            raise ValueError("invalid event header")
        stored = []
        for seq,row in enumerate(reader):
            x,y,t_ns,p,index = map(int,row)
            if seq != index:
                raise ValueError("invalid sequence")
            stored.append((x,y,t_ns-int(meta["epoch_ns"]),p))
    if len(generated) != meta["input_count"] or len(stored) != meta["stored_count"] or stored != generated[:meta["capacity"]]:
        raise ValueError("capture does not equal bounded complete GPU emission prefix")
    if meta["overflow_count"] != len(generated)-len(stored) or meta["complete_relative_to_stage_input"] != (len(generated)==len(stored)):
        raise ValueError("invalid capture loss accounting")
    result = compare_events(reference,generated,gate_ns)
    return {"profile":PROFILE,"reference":"binary64 log-linear solver consuming archived FP32 pre-floor optical input and FP32 thresholds",
            "comparison":result,"capture":{"stored":len(stored),"overflow":meta["overflow_count"],"prefix_exact":True},
            "sampling":{"skipped_scheduled_samples":manifest["optical_input"]["skipped_scheduled_samples"],"unseen_between_sample_changes":"not bounded"},
            "sensor_suppressed":0,"input_sha256":hashlib.sha256((Path(manifest_path).parent/"intensity.f32").read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest",type=Path)
    parser.add_argument("--report",type=Path)
    parser.add_argument("--gate-ns",type=int,default=DEFAULT_GATE_NS)
    args=parser.parse_args()
    result=evaluate(args.manifest,args.gate_ns)
    text=json.dumps(result,indent=2)+"\n"
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(text,encoding="utf-8")
    print(text,end="")
    raise SystemExit(0 if result["comparison"]["passed"] else 1)

if __name__=="__main__":
    main()
