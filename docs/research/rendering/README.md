# Rendering track: deterministic optical fixtures

November 22, 2026. Track: `codex/fidelity-rendering`, [issue #6](https://github.com/pianojay/event-vision-lab/issues/6). Development base: `7e909179d8a3c5578a2758cd069635cc71655371` (shared Godot setup), following coordination root `749c238`. See [coordination](../../development/fidelity-coordination.md) and the [fidelity research](../sensor-simulation-fidelity.md).

## Implemented scope

The first independent deliverable is a **CPU-only optical-input fixture**, implemented in [optical_fixture.py](../../../tools/rendering/optical_fixture.py). It uses Python's standard library and does not change the game, common shader, sensor, launcher or GPU test harness. It can run while the coordinator defines the shared runtime boundary.

Two fixtures are provided:

- **Projected emissive edge:** a vertical straight boundary with constant linear intensity on each side. It supplies center-ray sampling, regular subpixel quadrature, and an exact pixel-box-area reference. The reference has no temporal exposure integration or lens PSF.
- **Isolated matte sphere:** a scalar CPU counterpart of the prototype's controlled pinhole/direct-light approximation. It supplies a reproducible scene input, including values above 1, rather than a richer or calibrated renderer. The axial-ray check uses an independently calculated surface point, normal and lamp distance.

The [input contract](input-contract.md) specifies coordinates, linear units, output encoding and limitations. This is a track-local interchange proposal, **not the shared GPU/runtime API**. No full event stream or electronic sensor is implemented here.

## Reproduce

From the repository root, using Python 3 (recorded with Python 3.14.8):

```powershell
python -m unittest discover -s tools/rendering -p test_optical_fixture.py -v
python tools/rendering/validate_fixtures.py --report tools/rendering/output/checks.json

python tools/rendering/optical_fixture.py --fixture tools/rendering/fixtures/edge.json --output tools/rendering/output/edge-center
python tools/rendering/optical_fixture.py --fixture tools/rendering/fixtures/edge.json --samples-per-axis 8 --output tools/rendering/output/edge-8
python tools/rendering/optical_fixture.py --fixture tools/rendering/fixtures/edge.json --exact-edge --output tools/rendering/output/edge-exact
python tools/rendering/optical_fixture.py --fixture tools/rendering/fixtures/matte-sphere.json --output tools/rendering/output/sphere
```

Outputs under `tools/rendering/output/` and Python caches are ignored by Git. Generation refuses existing output directories/reports; choose a new destination to repeat a run. Retain selected evidence deliberately under this documentation directory. No GPU slot, Godot installation, graphics context, additional package or external host is required.

## Evidence and first finding

The [recorded CPU checks](evidence/2026-11-22-cpu-fixtures.json) include analytic checks, a spatial quadrature sweep, float32 data/hash integrity and static-scene repeatability. See [results and handoff](results-and-handoff.md) for measured values, tested revision and integration boundaries.

For the edge fixture, changing a boundary within a pixel can leave the center ray unchanged while the area-integrated intensity changes. This affects the signal **before** the sensor's logarithm. Averaging log intensities or filtering an already generated event image does not implement the same optical integration. More temporal samples cannot recover a change which the spatial point sampler never observes.

This establishes a controlled mathematical example, not a measured model of a real pixel. Spatial quadrature and temporal sampling must both be assessed. The existing analytic scene remains a useful control; full optical calibration, roughness/specular material references, distortion/PSF, indirect illumination, glass and external renderer comparisons remain future work under #6.
