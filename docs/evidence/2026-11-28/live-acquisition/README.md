# Live acquisition evidence

The goal is a representative 3D optical-to-event capture with an independent recorded-input comparison. The implementation was checked on Windows, Intel Iris Plus Graphics, Godot 4.7.2, Vulkan Mobile. The parent coordinator ran genuine hidden real-context GPU jobs. No Computer Use was used. Launcher records report zero visible or owned-window observations.

## Results

| Check | Result |
| --- | --- |
| Existing GPU sensor baseline | 25 of 25 passed |
| New GPU acquisition integration | 11 of 11 passed |
| Existing CPU suites | 75 tests passed |
| Recorded-input CPU reference tests | 10 tests passed |
| Existing headless controls | 69 of 69 passed |
| New headless acquisition contracts | 36 of 36 passed |
| Stationary sphere and moving light | 2,223 GPU and reference events, 315 ON and 1,908 OFF |
| Moving camera and occlusion | 5,787 GPU and reference events, 2,563 ON and 3,224 OFF |

Both representative comparisons have zero missing/extra events and zero capture loss. Maximum timestamp errors are 1,026 ns for the sphere and 1,679 ns for the camera. Both have 122 optical samples at 80 by 60 pixels over one second. The gate, set before comparison, requires exact count/polarity agreement and at most 100,000 ns event-time error. Synchronous readback is a diagnostic profile. These checks do not establish sustained frame rate or physical-camera fidelity.

`gpu-baseline.json` and `gpu-integration.json` contain the individual real-context checks. `sphere-comparison.json` and `camera-comparison.json` contain independent reference results. Run summaries preserve effective settings, source hashes, stage counts, and local raw artifact paths. CSV copies preserve exact exported events. Full optical/diagnostic archives remain in the recorded local `runs/next-acquisition/*-anchored` directories and can be regenerated with the commands below. Large diagnostic binaries are not duplicated in Git.

## Numerical failures retained

The first camera run exposed the old `+1e-5` count bias. At pixel 2125, the next OFF threshold lay about 1.30e-6 log units beyond the sampled endpoint. The shader nevertheless emitted it. `premature-crossing-counterexample.json` retains the actual values. Expansion rejected the event rather than widening its timestamp clamp.

After removing that bias, repeated absolute-reference additions still caused a one-event discrepancy at exact returns to the initial intensity. Both GPU FP32 and the naive binary64 reference could accumulate this error. The pre-anchor comparison reports retain the failed gates. Separate ON/OFF threshold counts now compute offsets relative to an anchor. The same strict gates then passed. Regression checks retain the early-crossing pixel, a nine-level exact return, and a below-threshold FP32 optical endpoint.

## Reproduction

```powershell
./run-lab.ps1 -AcquisitionConfig tools/acquisition/configs/sphere-light.json -EventCaptureDirectory runs/new-sphere -EvidenceDirectory runs/new-sphere-launch
python tools/acquisition/recorded_input.py runs/new-sphere/manifest.json --report runs/new-sphere/comparison.json
./run-lab.ps1 -AcquisitionConfig tools/acquisition/configs/camera-occlusion.json -EventCaptureDirectory runs/new-camera -EvidenceDirectory runs/new-camera-launch
python tools/acquisition/recorded_input.py runs/new-camera/manifest.json --report runs/new-camera/comparison.json
./run-pipeline.ps1 -ExistingRun runs/new-sphere -Replay
```

For a serialized real-context test, use Godot with `--path prototype --rendering-method mobile --rendering-driver vulkan --script res://tests/acquisition_gpu_tests.gd -- --report=<new report path>`. The parent used a hidden process launcher; the exact commands and window observations are retained in the launcher JSON files. Headless checks use `--headless --path prototype --script res://tests/acquisition_tests.gd` and `res://tests/controls_tests.gd`. CPU checks use `python -m unittest discover -s tools/<suite> -p test_*.py -v` for timing, sensor, rendering, coordination, pipeline, and acquisition. `cpu-tests.log` retains each actual command and result.

Source hashes identify the implementation tested while its changes were still uncommitted. The recorded Git base is `d8c7478`; it is not asserted to include those uncommitted changes. Final source and documentation commits are given in the handoff.

## Remaining acceptance work

The parent coordinator owns final event-only replay checks, repeated-run payload checks, and formal integration review. Reset, pause, overflow, incompatible configurations, and integer clock behavior have executable contract checks. A dedicated reset/overflow configuration is ready for the parent's real-context verification. Ten-minute sustained acquisition, optical sampling convergence, full interactive observation studies, processing integration, richer materials, and external simulator comparisons remain outside this bounded change.
