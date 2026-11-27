# Event Vision Lab

Simulate event vision without a physical event camera. A game is an optional medium; this first implementation is an interactive Godot shader laboratory.

The default live application is a navigable nine-station optical stage with an ideal log-contrast sensor, complete bounded event capture, post-event ROI/binning/polarity/time tools, and optional relative-grayscale contrast integration. Camera, objects, illumination, material state, sensor state, processing, and display are separate controls. Strobing is off by default. A labeled intensity view is diagnostic truth; it never supplies the inferred pane. Start with the [stage guide](docs/development/interaction-stage.md).

## Run on Windows

Requires the standard Windows x64 build of **Godot 4.7.2**, with a working Vulkan GPU/driver. The launcher uses `-GodotDirectory`, then `EVENT_LAB_GODOT_DIR`, then the shared installation at `C:\Godot_v4.7.2-stable_win64.exe\`, then checkout-local `tools/godot/4.7.2/`. Both GUI and console executables must be present; the version is checked before launch. The shared location is a directory despite its `.exe` suffix and works across component worktrees. The engine download and generated caches are excluded from Git. See the [prototype guide](docs/godot-prototype.md) for setup and checksum.

```powershell
.\run-lab.ps1
```

Alternatively, double-click `Run Event Vision Lab.cmd`, which uses built-in Windows PowerShell 5.1; PowerShell 7 is not required. Open the project in the editor with `./run-lab.ps1 -Editor`.

## Validate

```powershell
.\run-lab.ps1 -Validate
```

The GPU checks require a real rendering context; `--headless` does not validate this compute implementation. Test/profile commands replace the corresponding local evidence files.

For worktree checks, use `-EvidenceDirectory "$env:TEMP\event-lab-timing"` (or a distinct sensor/rendering directory) to preserve historical evidence. GPU runs must be sequential across worktrees.

The historical active-lighting baseline passed 25 GPU checks at 240×180. The new default bounded stream uses 80×60 and a 16,666,667 ns target sample period. It slows simulated time when composed work exceeds that budget, preserving scheduled intervals. A target cadence is not measured throughput. Use the [composed validation guide](docs/development/composed-validation.md) for actual-wall-time, power, loss, memory, input, inference-age, and rendered-output evidence. These restricted optical models are not a calibrated camera or a general renderer.

## Materials

Development uses GitHub Issues to preserve feedback and decisions, with incremental changes on `main`. Branches are for genuinely divergent development, including environment-specific experiments; PRs are optional. See [AGENTS.md](AGENTS.md).

- [Documentation index](docs/README.md)
- [Prototype controls, results and fidelity limits](docs/godot-prototype.md)
- [Concept and requirements](docs/concept-and-requirements.md)
- [Hardware tiers](docs/hardware-tiers.md)

Source lives in `prototype/`; CPU benchmark tools live in `tools/readiness/`. Recorded measurements and a preview image live in `docs/evidence/`. The original conversation export supplies concept context.

The separate [CPU pipeline](docs/pipeline-prototype.md) includes generic threshold mismatch, bandwidth, refractory behavior, seeded background activity, and bounded readout; [the sensor report](docs/research/sensor/generic-model.md) declares its assumptions and differences from pinned IEBCS. The live GPU sensor remains ideal. Reconstruction is constant-prior contrast integration, not a learned appearance model. Real-camera calibration, richer transport, and Ubuntu/TITAN RTX execution remain outside the demonstrated scope.
