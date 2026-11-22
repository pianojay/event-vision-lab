# Optical fixture input contract v1

This contract describes the standalone CPU artifacts in [the rendering tools](../../../tools/rendering/optical_fixture.py). It proposes an explicit boundary for comparisons; it does not establish the common runtime ABI, GPU bindings or timing track's event format. Changes to those shared interfaces belong to the coordinator.

## Intensity and coordinates

Each frame is an instantaneous sample of a scalar, scene-linear, relative-intensity field. No exposure integration, gamma, display tone mapping, per-frame normalization, logarithm, noise or dark floor is applied. Nonnegative zero and HDR values above 1 are allowed. Values must remain representable as finite float32. These units are not lux, spectral radiance, calibrated irradiance or photocurrent. Scene RGB conversion is unnecessary because both current fixtures are grayscale.

Image origin is top-left. `x` increases right and `y` increases down. Pixel `(x,y)` occupies `[x,x+1] × [y,y+1]` in continuous image coordinates; its center is `(x+0.5,y+0.5)`. The regular `n×n` midpoint quadrature averages linear intensity uniformly over this square. This is an ideal box pixel footprint, not calibrated lens blur, diffraction, sensor fill factor or an angle-dependent irradiance falloff. A physical optics model may replace it later.

The sphere uses the prototype camera convention: world up `+Y`, yaw zero looks toward `-Z`, positive pitch looks up, positive yaw turns toward `+X`. Aspect ratio is width/height and the FOV is vertical. All poses are fixed for a sequence in this first tool; the edge has an explicit projected trajectory.

## Defined fixtures

**Edge:** a frontoparallel emissive target with a projected vertical boundary at

`e(t) = edge_x_px + edge_speed_px_s * t_seconds`.

Intensity is `dark` to the left and `bright` to the right (`x >= e`), constant in `y`. The trajectory is defined in projected pixel units; no camera depth, world-space velocity, illumination interaction or material inference is implied for this fixture. For a pinhole image, such a straight boundary can be produced by a translated frontoparallel target under the ideal no-vignetting assumptions.

The exact bright fraction of pixel column `x` is `f=clamp(x+1-e,0,1)`. Its exact area-averaged intensity is `(1-f)*dark + f*bright`. This formula is the independent spatial oracle. For quadrature, sampling is necessary only along `x` because `y` is constant; the implementation integrates `y` analytically. The `n×n` description denotes an equivalent box quadrature, not `n²` work for this special edge. Midpoint error is bounded by `abs(bright-dark)/(2n)` before storage quantization; it need not decrease strictly for every individual sample count/phase.

**Sphere:** ray/sphere intersection followed by

`I = albedo * (ambient + lamp_strength * max(n·l,0) * 6/(distance²+1))`.

Missed rays return `background`. The fixed defaults reproduce the isolated matte-control camera, sphere and point-light approximation in [sensor.glsl](../../../prototype/shaders/sensor.glsl). This is not a normalized/calibrated BRDF: the softened attenuation, scale factor and constant ambient deliberately preserve the prototype control. There is no room, specular term, indirect illumination, transmission or refraction. Camera and lamp must be outside the convex sphere. There is no additional occluder; the clipped cosine rejects back illumination. The spatial average includes silhouette/background coverage.

These functions use float64 arithmetic during calculation and round only exported intensity to float32. Agreement with these equations is an analytic test; CPU-to-current-GPU numerical parity has **not** been run in this milestone. The GPU's historical sphere check is separate evidence.

## Time, files and provenance

`sample_times_ns` is a strictly increasing sequence of nonnegative integer times relative to simulation time zero. The first need not be zero. Files sample the field at these instants; frames are not integrated over intervals, and no continuity/interpolation or accurate event timestamps are promised between them. Integer nanoseconds are an artifact convention only. A future consumer must explicitly adapt this to the agreed simulation clock.

Each output directory contains:

- `intensity-0000.f32`, etc.: headerless, scalar IEEE float32, little-endian, row-major `[height,width]`, top row first. Byte length is exactly `4*width*height`. There is no padding, color/alpha channel or hidden log clamp.
- `manifest.json`: schema `event-lab-optical-fixture-v1`, all resolved parameters including defaults, dimensions/encoding, spatial method, each frame's filename/time/byte count/SHA-256, source commit and worktree dirty state. The file is written after frame generation; a partial run without its manifest is not a complete sequence.

An existing output directory is rejected to preserve previous data. Unknown fixture keys, invalid dimensions/times and invalid intensity are rejected. No API promises interoperability with other simulators' normal/HDR paths; their range, linear/log conventions and spectral assumptions require adapters.

Minimal decoding, using `entry` and `manifest` loaded from JSON:

```python
import struct
payload = (output_directory / entry["file"]).read_bytes()
height, width = manifest["encoding"]["shape"]
assert len(payload) == 4 * width * height
values = struct.unpack(f"<{width * height}f", payload)
intensity_xy = values[y * width + x]
```

Check the supplied hash before analysis. Consumers may apply their own documented floor, logarithm and pixel model after reading the **linear** field. Keep the original frame for cross-model comparisons.
