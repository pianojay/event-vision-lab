"""Deterministic optical input fixtures; no event sensor or display processing.

Python standard library only. See docs/research/rendering/input-contract.md.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess


Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Fixture:
    scene: str = "edge"
    width: int = 64
    height: int = 48
    samples_per_axis: int = 1
    # Integer time is an artifact convention, not the shared runtime/event API.
    sample_times_ns: tuple[int, ...] = (0, 8_333_333, 16_666_667)
    edge_x_px: float = 32.37
    edge_speed_px_s: float = 30.0
    dark: float = 0.1
    bright: float = 1.0
    camera_position: Vec3 = (0.0, 1.55, 5.1)
    camera_yaw_rad: float = 0.0
    camera_pitch_rad: float = -0.10
    vertical_fov_deg: float = 58.0
    sphere_center: Vec3 = (0.0, 1.0, -1.0)
    sphere_radius: float = 1.0
    light_position: Vec3 = (-2.0, 3.0, 2.0)
    albedo: float = 0.55
    lamp_strength: float = 5.0
    ambient: float = 0.035
    background: float = 0.015

    def __post_init__(self) -> None:
        if self.scene not in {"edge", "sphere"}:
            raise ValueError("scene must be edge or sphere")
        for field in ("width", "height", "samples_per_axis"):
            value = getattr(self, field)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        times = self.sample_times_ns
        if not times or any(type(t) is not int or t < 0 for t in times):
            raise ValueError("sample_times_ns must contain nonnegative integers")
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("sample times must be strictly increasing")
        vector_fields = ("camera_position", "sphere_center", "light_position")
        for field in vector_fields:
            vector = getattr(self, field)
            if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
                raise ValueError(f"{field} must be a finite xyz vector")
        for field in ("edge_x_px", "edge_speed_px_s", "dark", "bright",
                      "camera_yaw_rad", "camera_pitch_rad", "vertical_fov_deg",
                      "sphere_radius", "albedo", "lamp_strength", "ambient", "background"):
            if not math.isfinite(getattr(self, field)):
                raise ValueError(f"{field} must be finite")
        if not 0 < self.vertical_fov_deg < 180 or abs(self.camera_pitch_rad) >= math.pi / 2:
            raise ValueError("invalid FOV or pitch")
        if self.sphere_radius <= 0 or not 0 <= self.albedo <= 1:
            raise ValueError("invalid sphere radius or albedo")
        if min(self.dark, self.bright, self.lamp_strength, self.ambient, self.background) < 0:
            raise ValueError("intensities and illumination parameters must be nonnegative")
        # The isolated convex-sphere fixture assumes an external camera and lamp.
        if self.scene == "sphere":
            for position in (self.camera_position, self.light_position):
                if length(sub(position, self.sphere_center)) <= self.sphere_radius:
                    raise ValueError("camera and light must be outside the sphere")


def sub(a: Vec3, b: Vec3) -> Vec3:
    return tuple(x - y for x, y in zip(a, b))


def dot(a: Vec3, b: Vec3) -> float:
    return sum(x * y for x, y in zip(a, b))


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec3) -> Vec3:
    norm = length(a)
    return tuple(x / norm for x in a)


def camera_ray(config: Fixture, image_x: float, image_y: float) -> Vec3:
    """Continuous image coordinates; origin at upper left, ray at (x+.5,y+.5)."""
    yaw, pitch = config.camera_yaw_rad, config.camera_pitch_rad
    forward = (math.sin(yaw) * math.cos(pitch), math.sin(pitch),
               -math.cos(yaw) * math.cos(pitch))
    right = (math.cos(yaw), 0.0, math.sin(yaw))
    up = (-math.sin(yaw) * math.sin(pitch), math.cos(pitch),
          math.cos(yaw) * math.sin(pitch))
    scale = math.tan(math.radians(config.vertical_fov_deg) / 2)
    sx = (2 * image_x / config.width - 1) * config.width / config.height * scale
    sy = (1 - 2 * image_y / config.height) * scale
    return unit(tuple(forward[i] + sx * right[i] + sy * up[i] for i in range(3)))


def sphere_intensity(config: Fixture, image_x: float, image_y: float) -> float:
    """Grayscale version of the existing isolated matte-sphere approximation.

    No physical radiometry, indirect illumination or room geometry is implied.
    """
    ray = camera_ray(config, image_x, image_y)
    oc = sub(config.camera_position, config.sphere_center)
    b = dot(oc, ray)
    discriminant = b * b - (dot(oc, oc) - config.sphere_radius ** 2)
    if discriminant < 0:
        return config.background
    distance = -b - math.sqrt(discriminant)
    if distance <= 0.001:
        return config.background
    hit = tuple(config.camera_position[i] + distance * ray[i] for i in range(3))
    normal = unit(sub(hit, config.sphere_center))
    to_light = sub(config.light_position, hit)
    cosine = max(dot(normal, unit(to_light)), 0.0)
    direct = config.lamp_strength * cosine * 6.0 / (dot(to_light, to_light) + 1.0)
    return config.albedo * (config.ambient + direct)


def edge_position(config: Fixture, time_ns: int) -> float:
    return config.edge_x_px + config.edge_speed_px_s * (time_ns * 1e-9)


def exact_edge_pixel(config: Fixture, x: int, time_ns: int) -> float:
    """Exact box-area integral for a vertical emissive edge, bright on the right."""
    bright_fraction = min(1.0, max(0.0, x + 1.0 - edge_position(config, time_ns)))
    return config.dark * (1 - bright_fraction) + config.bright * bright_fraction


def render(config: Fixture, time_ns: int, *, exact_edge: bool = False) -> list[float]:
    """Return top-down scalar *linear* intensity, before any log or dark floor."""
    if type(time_ns) is not int or time_ns < 0:
        raise ValueError("time_ns must be a nonnegative integer")
    if exact_edge and config.scene != "edge":
        raise ValueError("exact area solution is available only for the edge fixture")
    n = config.samples_per_axis
    if config.scene == "edge":
        boundary = edge_position(config, time_ns)
        # Edge is constant in y: integrating y analytically avoids redundant work.
        row = [exact_edge_pixel(config, x, time_ns) if exact_edge else
               sum(config.bright if x + (i + .5) / n >= boundary else config.dark
                   for i in range(n)) / n for x in range(config.width)]
        return row * config.height
    result = []
    for y in range(config.height):
        for x in range(config.width):
            result.append(sum(sphere_intensity(config, x + (i + .5) / n,
                                               y + (j + .5) / n)
                              for j in range(n) for i in range(n)) / (n * n))
    return result


def encode_f32(values: list[float]) -> bytes:
    """Explicit little-endian float32, without clipping/normalizing/gamma/log."""
    if not all(math.isfinite(value) and 0 <= value <= 3.4028234663852886e38
               for value in values):
        raise ValueError("intensity must be finite, nonnegative and representable as f32")
    return struct.pack(f"<{len(values)}f", *values)


def load_fixture(path: Path) -> Fixture:
    values = json.loads(path.read_text(encoding="utf-8"))
    # Dataclass rejects unknown keys. Do not silently ignore misspelled parameters.
    return Fixture(**values)


def write_sequence(config: Fixture, output: Path, *, exact_edge: bool = False) -> dict:
    if exact_edge and config.scene != "edge":
        raise ValueError("exact area solution is available only for the edge fixture")
    output.mkdir(parents=True, exist_ok=False)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                          cwd=Path(__file__).resolve().parents[2],
                                          text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"],
                                            cwd=Path(__file__).resolve().parents[2], text=True))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    frames = []
    for index, timestamp in enumerate(config.sample_times_ns):
        payload = encode_f32(render(config, timestamp, exact_edge=exact_edge))
        name = f"intensity-{index:04d}.f32"
        (output / name).write_bytes(payload)
        frames.append({"file": name, "sample_time_ns": timestamp, "bytes": len(payload),
                       "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {
        "schema": "event-lab-optical-fixture-v1", "source_commit": revision,
        "source_worktree_dirty": dirty, "parameters": json.loads(json.dumps(asdict(config))),
        "encoding": {"dtype": "float32", "byte_order": "little", "channels": 1,
                     "shape": [config.height, config.width], "row_order": "top-to-bottom",
                     "axis_order": "y,x", "units": "relative linear intensity",
                     "log_applied": False, "dark_floor_applied": False,
                     "exposure_duration_ns": 0},
        "spatial_integration": "exact box area" if exact_edge else f"{config.samples_per_axis}x{config.samples_per_axis} midpoint box quadrature",
        "scope": "CPU optical fixture only; no sensor, event stream, temporal integration, lens PSF or calibrated irradiance",
        "frames": frames,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n",
                                          encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory; existing paths are never overwritten")
    parser.add_argument("--samples-per-axis", type=int)
    parser.add_argument("--exact-edge", action="store_true")
    args = parser.parse_args()
    try:
        config = load_fixture(args.fixture)
        if args.samples_per_axis is not None:
            from dataclasses import replace
            config = replace(config, samples_per_axis=args.samples_per_axis)
        manifest = write_sequence(config, args.output, exact_edge=args.exact_edge)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"Fixture generation failed: {error}\n")
    print(f"Wrote {len(manifest['frames'])} linear-intensity frames to {args.output}")


if __name__ == "__main__":
    main()
