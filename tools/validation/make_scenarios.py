"""Write reproducible scenario inputs without running the GPU."""

import argparse
import json
from pathlib import Path

STATIONS = ["absorption", "diffuse", "glossy", "transmission", "refraction", "fluorescence",
            "phosphorescence", "subsurface", "interreflection"]


def processing(mode="decay"):
    return {"roi": [0, 0, 80, 60], "bin_size": 2, "polarity": "both", "representation": mode,
            "window_ns": 100000000, "tau_ns": 100000000, "normalization": "count", "gain": 0.5,
            "window_capacity": 100000}


def scenario(inference=False, reduced=True, seconds=600):
    return {"name": "stage-inference" if inference else "stage-processing", "warmup_seconds": 10,
            "measure_seconds": seconds,
            "acquisition": {"archive_mode": "stream", "scene": "interaction-stage", "station": 1,
                            "stage_action": "light", "duration_ns": 3600000000000, "width": 80, "height": 60,
                            "sample_period_ns": 16666667, "wall_paced": True, "capture_capacity": 0},
            "initial": {"processing": processing(), "inference_enabled": inference, "reduced_flashes": reduced},
            "actions": [{"at_s": seconds * 0.1, "name": "observation-mode-input", "key": "V"},
                        {"at_s": seconds * 0.2, "name": "explicit-sensor-reset", "key": "R"},
                        {"at_s": seconds / 3, "name": "dense-events", "apply": {"strobe_enabled": True, "frequency": 12.0}},
                        {"at_s": seconds * 2 / 3, "name": "end-dense-events", "apply": {"strobe_enabled": False}}]}


def write_scenarios(directory):
    directory.mkdir(parents=True, exist_ok=True)
    configurations = {"stage-processing": scenario(), "stage-inference": scenario(inference=True),
                      "output-limited": scenario(seconds=12), "output-legacy": scenario(reduced=False, seconds=12),
                      "smoke": scenario(seconds=3)}
    for name, config in configurations.items():
        config["name"] = name
        if name in ("output-limited", "output-legacy", "smoke"):
            config["warmup_seconds"] = 2
        (directory / (name + ".json")).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def write_pairs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    pairs = []
    for station, name in enumerate(STATIONS):
        action = "pulse" if name in ("fluorescence", "phosphorescence") else "stripe" if name in ("transmission", "refraction") else "light"
        for treatment in (False, True):
            side = "treatment" if treatment else "control"
            config = {"scene": "interaction-stage", "station": station, "stage_action": action, "treatment": treatment,
                      "duration_ns": 1000000000, "sample_period_ns": 8333333, "width": 80, "height": 60,
                      "capture_capacity": 2000000, "stream_id": name + "-" + side}
            (directory / (name + "-" + side + ".json")).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        pairs.append({"station": name, "control": name + "-control/manifest.json",
                      "treatment": name + "-treatment/manifest.json", "roi": [0, 0, 80, 60],
                      "start_ns": 0, "end_ns": 1000000000, "relative_count_threshold": 0.05,
                      "light_metadata": {"prescribed_action": action}})
    (directory / "observations.json").write_text(json.dumps({"pairs": pairs}, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--pairs", action="store_true")
    args = parser.parse_args()
    if args.pairs:
        write_pairs(args.directory)
    else:
        write_scenarios(args.directory)


if __name__ == "__main__":
    main()
