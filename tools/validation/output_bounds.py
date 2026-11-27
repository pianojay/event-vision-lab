"""Conservative SDR output bounds; a failed bound is inconclusive."""

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np

SOURCE = "https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html"


def linear_rgb(rgb):
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def maximum_window(mask, width=341, height=256):
    rows, columns = mask.shape
    integral = np.pad(mask.astype(np.int64), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    w, h = min(width, columns), min(height, rows)
    sums = integral[h:, w:] - integral[:-h, w:] - integral[h:, :-w] + integral[:-h, :-w]
    position = np.unravel_index(int(sums.argmax()), sums.shape)
    return {"pixels": int(sums[position]), "fraction": float(sums[position]) / (width * height),
            "top_left_xy": [int(position[1]), int(position[0])], "window_wh": [width, height]}


def analyze_bounds(minimum, maximum, saturated_red_seen=None):
    minimum, maximum = np.asarray(minimum), np.asarray(maximum)
    if minimum.dtype != np.uint8 or maximum.dtype != np.uint8 or minimum.shape != maximum.shape:
        raise ValueError("Bounds must be matching uint8 arrays")
    if minimum.ndim != 3 or minimum.shape[2] != 3 or np.any(minimum > maximum):
        raise ValueError("Expected ordered H x W x RGB bounds")
    lo, hi = linear_rgb(minimum), linear_rgb(maximum)
    low_luminance = lo @ np.array([0.2126, 0.7152, 0.0722])
    high_luminance = hi @ np.array([0.2126, 0.7152, 0.0722])
    general = (high_luminance - low_luminance >= 0.1 - 1e-12) & (low_luminance <= 0.8 + 1e-12)
    if saturated_red_seen is None:
        possible_red = hi[:, :, 0] + 1e-12 >= 4 * (lo[:, :, 1] + lo[:, :, 2])
    else:
        possible_red = np.asarray(saturated_red_seen)
        if possible_red.shape != minimum.shape[:2] or possible_red.dtype != np.bool_:
            raise ValueError("Saturated-red mask must be a matching boolean image")
    changing = np.any(minimum != maximum, axis=2)
    red = possible_red & changing & (hi[:, :, 0] > 0)
    union = general | red
    area = maximum_window(union)
    return {"method": "whole-clip per-channel extrema sufficient area bound",
            "source": SOURCE, "colorspace": "8-bit SDR sRGB",
            "reference_scale": "one captured pixel per reference CSS pixel; no resizing",
            "general_capable_pixels": int(general.sum()), "red_capable_pixels": int(red.sum()),
            "union_capable_pixels": int(union.sum()), "maximum_hot_area": area,
            "verdict": "sufficient-bound-pass" if area["fraction"] < 0.25 else "inconclusive",
            "limits": ["Only the recorded SDR viewport at the declared scale is covered.",
                       "All changed potentially saturated-red pixels count, without a chromaticity exemption.",
                       "Extrema can combine channels from different times and overestimate area.",
                       "An inconclusive bound is not an unsafe verdict or a WCAG failure.",
                       "No flash-rate, human usability, HDR, zoom, display calibration, or viewing-distance claim."]}


def write_png(path, rgb):
    height, width, channels = rgb.shape
    if channels != 3 or rgb.dtype != np.uint8:
        raise ValueError("PNG requires RGB8")
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    scanlines = b"".join(b"\0" + row.tobytes() for row in rgb)
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    Path(path).write_bytes(payload + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


class OutputAccumulator:
    def __init__(self, directory, duration_s):
        self.directory = Path(directory)
        self.duration_s = duration_s
        self.minimum = self.maximum = None
        self.saturated_red_seen = None
        self.first = self.middle = self.last = None
        self.middle_distance = float("inf")
        self.frames = 0
        self.gaps = 0
        self.previous_draw = None
        self.times = []

    def consume(self, metadata, payload):
        width, height = int(metadata["width"]), int(metadata["height"])
        if not (1 <= width <= 8192 and 1 <= height <= 8192) or len(payload) != width * height * 3:
            raise ValueError("Invalid RGB frame dimensions or byte count")
        rgb = np.frombuffer(payload, dtype=np.uint8).reshape(height, width, 3)
        if self.minimum is None:
            self.minimum, self.maximum = rgb.copy(), rgb.copy()
            self.saturated_red_seen = np.zeros(rgb.shape[:2], dtype=bool)
            self.first = (metadata.copy(), rgb.copy())
        else:
            if rgb.shape != self.minimum.shape:
                raise ValueError("Viewport size changed during clip")
            np.minimum(self.minimum, rgb, out=self.minimum)
            np.maximum(self.maximum, rgb, out=self.maximum)
        linear = linear_rgb(rgb)
        self.saturated_red_seen |= (linear[:, :, 0] + 1e-12 >= 4 * (linear[:, :, 1] + linear[:, :, 2])) & (linear[:, :, 0] > 0)
        draw = int(metadata["draw_frame"])
        if self.previous_draw is not None:
            self.gaps += max(0, draw - self.previous_draw - 1)
            if draw <= self.previous_draw:
                raise ValueError("Rendered frame identities must increase")
        self.previous_draw = draw
        distance = abs(float(metadata["wall_s"]) - self.duration_s / 2)
        if distance < self.middle_distance:
            self.middle, self.middle_distance = (metadata.copy(), rgb.copy()), distance
        self.last = (metadata.copy(), rgb.copy())
        self.frames += 1
        self.times.append({key: metadata[key] for key in ("wall_s", "draw_frame")})

    def finish(self, completed):
        if not self.frames:
            raise ValueError("No rendered frames received")
        self.directory.mkdir(parents=True, exist_ok=True)
        artifact = self.directory / "rgb-bounds.npz"
        np.savez_compressed(artifact, minimum=self.minimum, maximum=self.maximum, saturated_red_seen=self.saturated_red_seen)
        report = analyze_bounds(self.minimum, self.maximum, self.saturated_red_seen)
        report.update(frames=self.frames, missed_rendered_frames=self.gaps, completed=completed,
                      frame_times=self.times, bounds_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                      capture_role="actual full Godot root viewport after frame_post_draw, RGB8",
                      clip_start_wall_s=self.times[0]["wall_s"], clip_end_wall_s=self.times[-1]["wall_s"])
        report["images"] = {}
        for name, (metadata, rgb) in (("first", self.first), ("middle", self.middle), ("last", self.last)):
            path = self.directory / (name + ".png")
            write_png(path, rgb)
            report["images"][name] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **metadata}
        if not completed or self.gaps or self.times[-1]["wall_s"] < self.duration_s:
            report["verdict"] = "inconclusive-incomplete-capture"
        (self.directory / "output-analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bounds", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with np.load(args.bounds, allow_pickle=False) as data:
        report = analyze_bounds(data["minimum"], data["maximum"], data["saturated_red_seen"] if "saturated_red_seen" in data else None)
    report["verdict"] = "bounds-only-" + report["verdict"]
    report["limits"].append("Standalone extrema analysis does not verify capture completeness or provenance.")
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
