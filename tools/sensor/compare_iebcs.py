"""Run pinned IEBCS source as an isolated comparison, never as the runtime model."""
from __future__ import annotations

import argparse
import cProfile
from dataclasses import asdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import pstats
import statistics
import sys
import time
import urllib.request

from generic_sensor import ActivityProfile, GenericSensor
from held_frame_adapter import simulate_frames
from readout import ReadoutEvent, ReadoutProfile, ReadoutQueue
from reference_sensor import ReferenceSensor, SensorProfile

PIN = "8fdab5c3d078435d091fa8a94ad657e1fedf0c59"
REPOSITORY = "https://github.com/neuromorphicsystems/IEBCS"
SOURCES = {
    "src/dvs_sensor.py": "bc8ed3f97b2a1c70591dc2d9db2e84155671147323287ce4fbebf1355ad04c03",
    "src/arbiter.py": "4e73cdd51ccd857ae168b01cd22f39f5b06e3d702360bad5b9352deebab66483",
    "src/event_buffer.py": "728d1c932cb68b4a9408a0f286d6aaa471ae6834104d845fd2bdecabfbf8cdb9",
    "src/dat_files.py": "e1d790514cacb4734a6d1559533dee9079512f857d1cb011593f6eae1c9a341f",
    "LICENSE": "e57f1c320b8cf8798a7d2ff83a6f9e06a33a03585f6e065fea97f1d86db84052",
}


def verify_sources(directory, fetch=False):
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for relative, expected in SOURCES.items():
        path = directory / Path(relative).name
        url = f"https://raw.githubusercontent.com/neuromorphicsystems/IEBCS/{PIN}/{relative}"
        if fetch:
            data = urllib.request.urlopen(url, timeout=30).read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"upstream hash mismatch: {relative}")
            path.write_bytes(data)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"cached source hash mismatch: {path}; fetch canonical bytes")
        records.append({"path": relative, "url": url, "sha256": expected,
                        "git_blob_sha1": hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()})
    return records


def run(directory):
    sys.path.insert(0, str(directory.resolve()))
    import numpy as np
    import tqdm
    from dvs_sensor import DvsSensor
    from arbiter import BottleNeckArbiter
    from event_buffer import EventBuffer

    def upstream(width=1, height=1, *, seed=17, rate=.001, refractory_us=0, sigma=0):
        np.random.seed(seed)
        sensor = DvsSensor("pinned-comparison")
        sensor.initCamera(width, height, lat=0, jit=0, ref=refractory_us, tau=100,
                          th_pos=.2, th_neg=.2, th_noise=sigma, bgnp=rate, bgnn=rate)
        return sensor

    steps = []
    for initial, target in ((10., 20.), (20., 10.), (1000., 2000.), (2000., 1000.)):
        for refractory_us in (0, 2000):
            for step_us in (1000, 20000):
                u = upstream(refractory_us=refractory_us)
                u.init_image(np.full((1, 1), initial))
                first_noise_us = int(min(u.bgn_pos_next.min(), u.bgn_neg_next.min()))
                tau_s = 100 * 1000 / (target+1) * 1e-6
                profile = SensorProfile(dark_offset=1, bandwidth_white_hz=1/(2*math.pi*tau_s),
                                        minimum_bandwidth_fraction=1, refractory_s=refractory_us*1e-6)
                local = ReferenceSensor(1, 1, profile)
                local.reset(0, [initial])
                upstream_times, upstream_polarities, ours = [], [], []
                for end_us in range(step_us, 20001, step_us):
                    packet = u.update(np.full((1, 1), target), step_us)
                    upstream_times.extend(packet.get_ts().astype(int).tolist())
                    upstream_polarities.extend((packet.get_p().astype(int)*2-1).tolist())
                    ours.extend(local.advance(end_us*1e-6, [target]).events)
                delta = abs(math.log(target+1)-math.log(initial+1))
                analytic_us = -tau_s*1e6*math.log1p(-.2/delta)
                error_us = abs(float(upstream_times[0])-ours[0].t_s*1e6)
                if not first_noise_us > 20000 or error_us >= 1.000001:
                    raise AssertionError("first crossing disagrees outside upstream microsecond truncation")
                if abs(ours[0].t_s*1e6-analytic_us) > 1e-8 or upstream_polarities[0] != ours[0].p:
                    raise AssertionError("analytical crossing or polarity mismatch")
                steps.append({"input": {"initial_flux": initial, "held_flux": target, "duration_us": 20000, "step_us": step_us},
                              "local_pixel": asdict(profile), "upstream_refractory_us": refractory_us,
                              "upstream_min_scheduled_noise_us": first_noise_us,
                              "effective_tau_us": tau_s*1e6, "analytic_first_us": analytic_us,
                              "upstream_times_us": upstream_times,
                              "upstream_polarities": upstream_polarities,
                              "local_times_us": [e.t_s*1e6 for e in ours],
                              "local_polarities": [e.p for e in ours], "first_error_us": error_us})

    n, rate, duration_us = 256, 8, 1_000_000
    def noise_case(step_us):
        u = upstream(width=n, rate=rate)
        image = np.full((1, n), 100.)
        u.init_image(image)
        local = GenericSensor(n, 1, pixel=SensorProfile(dark_offset=1), activity=ActivityProfile(temporal_on_hz=rate,
                                                            temporal_off_hz=rate, seed=17))
        local.reset(0, image.ravel().tolist())
        up_counts = [[0]*n, [0]*n]
        own_counts = [[0]*n, [0]*n]
        own_events = []
        for end in range(step_us, duration_us+1, step_us):
            packet = u.update(image, step_us)
            for x, p in zip(packet.get_x(), packet.get_p()):
                up_counts[int(p)][int(x)] += 1
            for e in local.advance(end*1e-6, image.ravel().tolist()).events:
                own_counts[1 if e.p > 0 else 0][e.x] += 1
                own_events.append((e.t_s, e.x, e.p))
        def moments(counts):
            return {name: {"total": sum(c), "mean": statistics.mean(c),
                           "variance": statistics.pvariance(c)}
                    for name, c in zip(("off", "on"), counts)}
        return {"step_us": step_us, "upstream": moments(up_counts), "local": moments(own_counts),
                "local_event_digest": hashlib.sha256(repr(own_events).encode()).hexdigest()}
    noise = [noise_case(step) for step in (1_000_000, 50_000, 10_000)]
    if len({case["local_event_digest"] for case in noise}) != 1:
        raise AssertionError("Poisson schedule changed with timestep")
    for polarity in ("on", "off"):
        if abs(noise[0]["local"][polarity]["mean"]-rate) > 5*math.sqrt(rate/n):
            raise AssertionError("Poisson count mean outside declared 5-sigma bound")
        if abs(noise[0]["local"][polarity]["variance"]-rate) > 5*math.sqrt((rate+2*rate*rate)/n):
            raise AssertionError("Poisson count variance outside declared approximate 5-sigma bound")

    u = upstream(width=4096, sigma=.03)
    local = ReferenceSensor(4096, 1, SensorProfile(threshold_sigma=.03, seed=17))
    mismatch = {}
    for name, upstream_values, local_values in (
        ("on", u.cur_th_pos.ravel(), [pair[0] for pair in local.thresholds]),
        ("off", -u.cur_th_neg.ravel(), [pair[1] for pair in local.thresholds])):
        mismatch[name] = {"upstream_mean": float(np.mean(upstream_values)),
                          "upstream_std": float(np.std(upstream_values)),
                          "local_mean": statistics.mean(local_values),
                          "local_std": statistics.pstdev(local_values)}

    for values in mismatch.values():
        for model in ("upstream", "local"):
            if abs(values[f"{model}_mean"]-.2) > 5*.03/math.sqrt(4096):
                raise AssertionError("initial threshold mean outside 5-sigma bound")
            if abs(values[f"{model}_std"]-.03) > .002:
                raise AssertionError("initial threshold spread outside declared tolerance")

    packet = EventBuffer(0)
    for x in range(4):
        packet.add(0, 0, x, 1)
    arbiter = BottleNeckArbiter(10, 0)
    output = arbiter.process(packet, 100)
    queue = ReadoutQueue(ReadoutProfile(2, 10000))
    delivered = queue.advance([ReadoutEvent(x, 0, 0, 1) for x in range(4)], 100000)
    readout = {"input": {"count": 4, "timestamp_us": 0, "service_parameter_us": 10,
                          "advance_us": 100},
               "upstream": {"returned_times_us": output.get_ts().astype(int).tolist(),
                            "returned_count": int(output.i), "pending_count": int(arbiter.ev_acc.i),
                            "capacity": "unbounded; no drop counter"},
               "local": {"effective": queue.effective(), **queue.snapshot(), "original_times_ns": [d.event.t_ns for d in delivered],
                         "delivered_ns": [d.delivered_ns for d in delivered]},
               "interpretation": "Different queue laws. IEBCS mock scales processing time by backlog and rewrites timestamps; local bounded FIFO has per-event service and drops."}

    return {"dependencies": {"numpy": np.__version__, "tqdm": tqdm.__version__},
            "upstream_effective": {"seed": 17, "latency_us": 0, "jitter_us": 0,
                "tau_parameter_us": 100, "threshold_on": .2, "threshold_off_magnitude": .2,
                "threshold_noise": "0 except initial-map comparison .03",
                "background_rate_hz": "0.001 per polarity for step cases; 8 for noise cases",
                "radiometry": "identical raw flux; both use log(flux+1)",
                "response_alignment": "local constant tau chosen to match each held target's IEBCS tau; not a global bandwidth-law match"},
            "steps": steps, "noise": {"pixels": n, "flux": 100, "rate_per_polarity_hz": rate,
                "duration_us": duration_us, "cases": noise,
                "local_effective": GenericSensor(n, 1, pixel=SensorProfile(dark_offset=1),
                    activity=ActivityProfile(temporal_on_hz=rate, temporal_off_hz=rate, seed=17)).effective(),
                "interpretation": "IEBCS fixed-period random-phase background is not Poisson. Large updates check only one noise event per polarity per pixel; local continuous schedules preserve all arrivals."},
            "initial_threshold_maps": {"pixels": 4096, "nominal": .2, "sigma": .03,
                "moments": mismatch,
                "interpretation": "Initial distribution moments only; IEBCS redraws thresholds after events, local map remains fixed. RNGs and clipping floors differ."},
            "readout": readout}


def cost_report():
    # Claim: observed cost of this exact offline 8x8/100 ms fixture, not realtime throughput.
    times = list(range(0, 100_000_001, 10_000_000))
    frames = [[1 if i%2 == 0 else 2]*64 for i in range(len(times))]
    def workload(enabled):
        return simulate_frames(8, 8, times, frames,
            activity=ActivityProfile(leak_log_per_s=4, temporal_on_hz=8, temporal_off_hz=8)
                     if enabled else ActivityProfile(),
            readout=ReadoutProfile(32, 10000))
    timings = {"disabled_activity": [], "enabled_activity": []}
    counters = {}
    for _ in range(5):
        for enabled in (False, True):
            name = "enabled_activity" if enabled else "disabled_activity"
            start = time.perf_counter()
            result = workload(enabled)
            timings[name].append(time.perf_counter()-start)
            counters[name] = result["counters"]
            c = result["counters"]
            if c["readout_input"] != c["readout_delivered"]+c["readout_dropped"] or c["optical_candidates"] == 0 or (enabled and c["leak_candidates"] == 0):
                raise AssertionError("cost workload failed conservation or did no optical work")
    profiler = cProfile.Profile()
    profiler.runcall(workload, True)
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(10)
    return {"scope": "entire in-memory held-frame adapter including generation, readout, capture arrays and metadata; no disk serialization",
            "settings": {"width": 8, "height": 8, "duration_ns": times[-1], "sample_period_ns": 10000000,
                         "frames": "alternating 1 and 2", "repetitions_per_configuration": 5,
                         "pixel": asdict(SensorProfile()), "readout": asdict(ReadoutProfile(32, 10000)),
                         "disabled_activity": asdict(ActivityProfile()),
                         "enabled_activity": asdict(ActivityProfile(leak_log_per_s=4, temporal_on_hz=8, temporal_off_hz=8)),
                         "capture_capacity_per_stage": 1_000_000, "candidate_limit_per_step": 1_000_000,
                         "source_loss_count": 0, "drain_readout": True},
            "seconds": {name: {"runs": values, "median": statistics.median(values),
                              "min": min(values), "max": max(values)} for name, values in timings.items()},
            "counters": counters, "profile_separate_untimed_run": stream.getvalue(),
            "limitation": "Small offline workload, untuned Python, concurrent machine load uncontrolled. No adoption/speedup or real-time/GPU claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, default=Path("runs/reference-iebcs"))
    parser.add_argument("--fetch", action="store_true", help="fetch pinned GPL reference into ignored runtime directory")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sources = verify_sources(args.reference_dir, args.fetch)
    report = {"schema": "event-lab-pinned-sensor-comparison-v1", "repository": REPOSITORY, "commit": PIN,
              "license": "upstream GPL-3.0 license file; external experiment input, not vendored/runtime dependency",
              "sources": sources, "environment": {"python": platform.python_version(),
                "platform": platform.platform(), "processor": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
                "logical_cpus": os.cpu_count()}, "comparison": run(args.reference_dir), "cost": cost_report(),
              "unresolved": ["No calibrated real-camera validation", "No physical leak-current model or matching upstream leak law",
                "Poisson and periodic-background noise laws differ", "Pixel reset/blind semantics differ",
                "No whole-model IEBCS/v2e parity", "No GPU implementation or live-runtime cost measurement"]}
    report["local_source_sha256_lf"] = {p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
        for p in Path(__file__).parent.glob("*.py")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"step_cases": len(report["comparison"]["steps"]),
                      "max_first_error_us": max(c["first_error_us"] for c in report["comparison"]["steps"]),
                      "report": str(args.report)}))


if __name__ == "__main__":
    main()

