# Event Vision Lab

Simulate event vision without a physical event camera. A game is an optional medium; this first implementation is an interactive Godot shader laboratory.

The GPU renders a controlled scene into linear intensity, maintains an ideal log-contrast event sensor, and displays decaying event counts, raw events or a time surface. Active-lighting controls include fixed, camera-mounted and orbiting point sources, with a matte-sphere control scene. Strobing is off by default. Lighting changes, object motion and changing surface appearance can be controlled independently. A labeled reference-intensity view helps compare the hidden scene with the sensor output.

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

The Windows/Iris Plus active-lighting trial passed 25 GPU checks at 240×180. The prototype targets 120 Hz sensor sampling and a 60 FPS display. These results cover a small analytic scene, not a calibrated camera or realistic general-purpose simulator.

## Materials

Development uses GitHub Issues to preserve feedback and decisions, with incremental changes on `main`. Branches are for genuinely divergent development, including environment-specific experiments; PRs are optional. See [AGENTS.md](AGENTS.md).

- [Documentation index](docs/README.md)
- [Prototype controls, results and fidelity limits](docs/godot-prototype.md)
- [Concept and requirements](docs/concept-and-requirements.md)
- [Hardware tiers](docs/hardware-tiers.md)

Source lives in `prototype/`; CPU benchmark tools live in `tools/readiness/`. Recorded measurements and a preview image live in `docs/evidence/`. The original conversation export supplies concept context.

Noise, refractory behavior, practical scene validation, full event-stream export and learned reconstruction remain future work. Ubuntu/TITAN RTX testing is deferred.
