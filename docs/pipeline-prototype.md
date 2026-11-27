# Run the configurable event pipeline

The CPU prototype renders an optical fixture, generates events, writes a reproducible run, and replays the emitted capture in Godot. It uses Python 3.10+ with the standard library. Godot 4.7.2 is needed only for replay. The existing interactive GPU laboratory remains available through `run-lab.ps1`.

## Generate and replay an edge

From the repository root on Windows, run:

```powershell
.\run-pipeline.ps1 -Replay
```

The command prints a fresh output directory under ignored `runs/pipeline/`. The replay shows a bright band of recent events as the edge moves across the sensor. It shows windowed event counts, not reconstructed intensity. The renderer's ground-truth frames are separate artifacts and are never loaded by replay.

Use **Play / pause** or Space to pause. Drag the time slider to inspect a moment. Use **Replay from start**, **Slower**, **Faster**, or **ON / OFF colors** to change the display. These controls change replay only. They do not rerun or reset the simulated sensor.

Replay a saved run with its printed path:

```powershell
.\run-pipeline.ps1 -ExistingRun 'runs\pipeline\YOUR-RUN' -Replay
```

The launcher checks `-GodotDirectory`, then `EVENT_LAB_GODOT_DIR`, then the shared `C:\Godot_v4.7.2-stable_win64.exe` directory. Pass the engine directory explicitly for a different installation.

## Compare sensor and timing choices

Run the generic sensor profile with finite response, fixed threshold mismatch, dark offset, and refractory gating:

```powershell
.\run-pipeline.ps1 -Config tools/pipeline/configs/edge-nonideal.json -Replay
```

Run an ideal sensor directly on the continuous exact-area optical trajectory:

```powershell
.\run-pipeline.ps1 -Config tools/pipeline/configs/edge-exact.json -Replay
```

Compare a narrow pulse that falls between uniform samples with a sampler that knows the pulse's change boundaries:

```powershell
.\run-pipeline.ps1 -Config tools/pipeline/configs/pulse-uniform.json -Replay
.\run-pipeline.ps1 -Config tools/pipeline/configs/pulse-boundaries.json -Replay
```

The uniform run is blank because its optical samples miss the pulse. The known-boundaries run captures ON and OFF events. Open each `manifest.json` to compare missing events, extra events, and timing error. A low error among matched events does not imply that all events were captured.

## Make a repeatable experiment

Copy a JSON profile from `tools/pipeline/configs/` and change its parameters. Run it with `-Config` and an explicit new `-OutputDirectory`. Existing output directories are rejected.

```powershell
.\run-pipeline.ps1 -Config tools/pipeline/configs/edge-ideal.json -OutputDirectory runs/my-experiment
```

Every output contains an expanded `config.json`. Reuse that file to reproduce the configuration. `manifest.json` records source hashes, commit, dirty state, runtime, input units, sample times, reset records, and separate stage counts. `events.csv` contains captured pixel emissions. `candidates.csv` contains sensor candidates before refractory gating. `truth.csv` contains ideal events from the same continuous optical fixture. `intensity.f32` contains the sampled optical frames with offsets and hashes in the manifest.

Read the [v1 profile reference](development/pipeline-v1.md) before changing trajectory, reset, timestamp, or sensor parameters. Unsupported combinations fail explicitly.

## Reproduce the checks

Run the CPU behavioral checks and generate 15 complete experiment runs into a new directory:

```powershell
python -B tools/pipeline/validate_pipeline.py --output runs/my-validation
```

After reserving the shared GPU slot, run the twelve serialized real-context replay checks:

```powershell
python -B tools/pipeline/validate_replay.py --output runs/my-replay-validation
```

For one saved run, `-VerifyReplay` writes a midpoint screenshot and report, then exits:

```powershell
.\run-pipeline.ps1 -ExistingRun runs/my-experiment -VerifyReplay
```

The [recorded evidence](evidence/2026-11-28/pipeline-prototype/README.md) describes measured results and remaining limits. This prototype does not establish camera calibration, upstream simulator parity, complex scene fidelity, or real-time performance. The generic CPU sensor is not part of live GPU acquisition.
