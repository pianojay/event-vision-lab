"""Event-only paired observation summaries with truth used only for scoring."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def event_features(events, roi, start_ns, end_ns):
    if len(roi) != 4 or roi[0] >= roi[2] or roi[1] >= roi[3] or start_ns >= end_ns:
        raise ValueError("Invalid ROI or observation interval")
    selected = [event for event in events if roi[0] <= event[0] < roi[2] and roi[1] <= event[1] < roi[3]
                and start_ns <= event[2] <= end_ns]
    count = len(selected)
    on = sum(event[3] == 1 for event in selected)
    centroid = [sum(event[axis] for event in selected) / count for axis in (0, 1)] if count else None
    midpoint = (start_ns + end_ns) // 2
    early = [event for event in selected if event[2] <= midpoint]
    late = [event for event in selected if event[2] > midpoint]
    displacement = ([sum(event[axis] for event in late) / len(late) - sum(event[axis] for event in early) / len(early)
                     for axis in (0, 1)] if early and late else None)
    histogram = [0] * 16
    for event in selected:
        histogram[min(15, (event[2] - start_ns) * 16 // (end_ns - start_ns))] += 1
    return {"count": count, "on": on, "off": count - on, "centroid_xy": centroid,
            "centroid_displacement_xy": displacement, "temporal_counts": histogram,
            "events_per_second": count * 1e9 / (end_ns - start_ns),
            "active_pixels": len({(event[0], event[1]) for event in selected})}


def compare_pair(control, treatment, relative_count_threshold):
    denominator = max(control["count"], treatment["count"], 1)
    relative_difference = abs(treatment["count"] - control["count"]) / denominator
    first, second = control["centroid_xy"], treatment["centroid_xy"]
    distance = math.dist(first, second) if first is not None and second is not None else None
    return {"relative_count_difference": relative_difference, "centroid_distance_pixels": distance,
            "predicted_count_response_difference": relative_difference >= relative_count_threshold,
            "relative_count_threshold": relative_count_threshold}


def load_capture(path):
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    metadata = manifest["captures"]["events"]
    if metadata.get("stage") != "pixel-emitted" or not metadata.get("complete_relative_to_stage_input"):
        raise ValueError("Observation tasks require a complete pixel-emitted capture")
    csv_path = path.parent / metadata["file"]
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if metadata.get("sha256") != digest:
        raise ValueError("Event capture hash mismatch")
    epoch = int(metadata["epoch_ns"])
    events = []
    previous = None
    with csv_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            event = [int(row["x"]), int(row["y"]), int(row["t_ns"]) - epoch, int(row["p"])]
            if event[3] not in (-1, 1) or not 0 <= event[0] < metadata["width"] or not 0 <= event[1] < metadata["height"]:
                raise ValueError("Invalid event coordinate or polarity")
            if previous is not None and event[2] < previous:
                raise ValueError("Events are not ordered")
            previous = event[2]
            events.append(event)
    if len(events) != metadata["stored_count"]:
        raise ValueError("Event capture count mismatch")
    return events, {"manifest": str(path), "events_sha256": digest, "event_stage": metadata["stage"],
                    "width": metadata["width"], "height": metadata["height"]}


def evaluate(specification, base):
    results = []
    for pair in specification["pairs"]:
        features, provenance = {}, {}
        for side in ("control", "treatment"):
            events, identity = load_capture(base / pair[side])
            features[side] = event_features(events, pair["roi"], pair["start_ns"], pair["end_ns"])
            provenance[side] = identity
        prediction = compare_pair(features["control"], features["treatment"], pair["relative_count_threshold"])
        truth = pair.get("score_truth", {})
        expected = truth.get("count_response_difference")
        results.append({"station": pair["station"], "roi": pair["roi"], "declared_light_metadata": pair.get("light_metadata"),
                        "features": features, "prediction": prediction, "provenance": provenance,
                        "score": {"expected_count_response_difference": expected,
                                  "matches": prediction["predicted_count_response_difference"] == expected if expected is not None else None}})
    return {"schema": "event-lab-observation-evaluation-v1", "results": results,
            "estimator_inputs": "pixel-emitted events, declared ROI, interval, and predeclared comparison threshold",
            "truth_usage": "score only; unavailable to event_features and compare_pair",
            "limits": ["A detectable paired count change does not identify a material or recover normals/depth.",
                       "No human usability or calibrated-camera claim.",
                       "A zero count difference does not prove optical equivalence."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specification", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    specification = json.loads(args.specification.read_text(encoding="utf-8"))
    report = evaluate(specification, args.specification.parent)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
