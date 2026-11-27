# Event-only grayscale baseline

The optional grayscale view integrates emitted contrast events against a constant log-intensity prior. It consumes raw pixel coordinates and event timestamps. It never consumes the ROI, bins, selected polarity, RGB, geometry, or optical intensity. The raw event window remains visible beside inferred output.

## Method and inputs

For each pixel, the baseline computes `L(t) = L_prior + C_ON*N_ON(t) - C_OFF*N_OFF(t)`. The default prior is zero log intensity, or one arbitrary intensity unit. ON and OFF thresholds are independent, explicit parameters. Replay initializes them from the capture's nominal sensor parameters. The CLI requires both thresholds.

This is a direct contrast-integration baseline derived from the declared ideal sensor crossing rule. There is no trained model, checkpoint, external implementation, or added package dependency. It uses Python's standard library and the existing Godot runtime. No model or dataset license is needed. The new code follows the repository's licensing state.

Events do not determine absolute intensity or the spatially varying initial image. A silent pixel remains at its prior. Threshold variation, event loss, noise, refractory suppression, and sensor resets can produce persistent errors. A single global scale fit cannot supply missing initial texture. The displayed grayscale is inferred relative intensity, not recovered scene appearance.

The module retains the raw log estimate and computes `I=exp(clamp(L,-80,80))`. Saturated output pixels are counted explicitly. Display uses fixed `I/(1+I)` exposure. It does not normalize each frame to truth or to its own extrema.

## Replay controls and state

Select **Infer grayscale** to show the third pane. **Constant log prior**, **C ON**, and **C OFF** recompute raw event history. **Reset prior here** excludes events at or before the current cursor and initializes every pixel to the constant prior. **Warm from start** restores integration from the capture start, including events at time zero.

Disabling inference hides the pane and skips snapshots. Raw history and the reset boundary remain retained. Re-enabling deterministically integrates the retained events through the current cursor. There is no recurrent learned state or hidden warmup interval. This offline implementation scans retained history, so enabling it can cost more work on a long capture. Scrubbing before the reset boundary shows the constant prior.

**Save settings** also writes a `<processing-path>.reconstruction.json` companion with thresholds, prior, reset time, and enabled state. **Load settings** validates that companion independently. The `--reconstruct` replay flag enables the inferred pane on startup and in a verification screenshot.

## Reproduce an offline run

```powershell
python -B tools/reconstruction/contrast_integrator.py --manifest docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --on-threshold .2 --off-threshold .2 --output runs/reconstruction
python -B tools/reconstruction/evaluate_capture.py --manifest docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --output runs/reconstruction-evaluation
```

The first command writes a numerical JSON result and a PGM image from events only. It works when the input directory contains just `manifest.json` and `events.csv`. The second command evaluates completed inference against separately read FP32 optical samples. Output images use no fitted scale. Evaluation reports both unaligned log RMSE and a separately labeled global log-offset fit.

Optical samples can be zero. When the capture declares a sensor `intensity_floor`, evaluation compares the estimate with `log(max(archived_intensity, intensity_floor))`. The report records the floor, its manifest sources, and the number of floored pixels per frame. Negative or nonfinite optical values fail validation. Zero without a declared positive floor also fails; positive legacy captures need no added floor. The raw truth image remains unchanged, and neither truth nor the evaluation floor enters reconstruction. Reports retain the actual scene, station, effective configuration, and capture source. An offline evaluation covers that capture and does not establish sustained live throughput.

`--reset-ns` sets the exclusive integration start, and `--initial-log-intensity` changes the constant prior. The default reset time is -1, so time-zero events are included. Events are read in their recorded order. Splitting consumption into batches does not change the result. The loader rejects candidate and ideal-truth capture stages.

## Recorded outcomes and failures

| Capture | Events | Final unaligned log RMSE | After explicitly fitted global log offset |
| --- | ---: | ---: | ---: |
| Existing ideal moving edge | 1,536 | 0.0931 | 0.0000 |
| Existing nonideal moving edge | 1,526 | 0.1032 | 0.0351 |
| Existing illumination pulse | 6 | approximately zero | zero |
| Preliminary 3D moving-light sphere | 2,223 | 4.1047 | 0.9179 |
| Preliminary 3D moving-camera scene | 5,786 | 4.1010 | 0.9545 |

The [ideal edge comparison](evidence/2026-11-28/event-reconstruction/ideal/comparison.svg) has a uniform initial intensity that happens to match the declared constant prior. Its residual threshold error is almost uniform at the end. The [nonideal comparison](evidence/2026-11-28/event-reconstruction/nonideal/comparison.svg) retains spatial errors. The [pulse trial](evidence/2026-11-28/event-reconstruction/pulse/comparison.svg) includes static intervals and an ON/OFF illumination change. The estimate holds during silence and returns near its prior after the pulse. This is a favorable controlled case.

The [3D sphere](evidence/2026-11-28/event-reconstruction/sphere-preintegration/comparison.svg) and [camera-motion](evidence/2026-11-28/event-reconstruction/camera-preintegration/comparison.svg) comparisons preserve the principal failure. Their initial spatial intensity varies, while the reconstruction starts uniformly. Only 227 and 299 of 4,800 pixels, respectively, received events by the end. Global scale alignment leaves substantial spatial error. Truth was used only for these labeled evaluations, after inference.

Those two 3D inputs are preliminary captures from the acquisition branch. Their evaluation reports retain exact event SHA-256 hashes and source paths. The acquisition implementation was still under validation, so these results do not certify its final recurrence or camera model. Re-run the commands on the final integrated capture. A representative reflective or transmissive station remains unevaluated.

## Verification and measurement scope

Eleven reconstruction tests pass. They cover constant-prior ambiguity, independent thresholds, timestamp ties, reset boundaries, silence, scrub, batching, saturation, and rejection of non-emitted capture stages. One test compares Godot with Python across 12 configurations and 72 snapshots. Another executes the CLI with no optical archive present. Fourteen processing tests also pass.

The [headless replay report](evidence/2026-11-28/event-reconstruction/replay-controls.json) contains 22 passing routed checks. The parent independently ran the same 22 checks with a real Vulkan context on the preliminary 3D sphere capture and inspected the 1280×800 layout. Its [report](evidence/2026-11-28/event-reconstruction/sphere-replay-report.json) and [screenshot](evidence/2026-11-28/event-reconstruction/sphere-replay.png) are retained. The optional inference pane was disabled in that GPU screenshot. This validates replay execution and control routing, not reconstruction quality.

The offline evaluator repeats full-sequence snapshots five times, asserts the integrated event work, and profiles a separate run. It excludes capture loading, rendering, and truth evaluation from latency. It records Python 3.14.8, Windows 11, the processor identifier, and logical CPU count in each report. Concurrent project work affected these measurements. No speed comparison or live performance conclusion is drawn.

The preliminary sphere and camera trials averaged 4.80 ms and 7.69 ms per snapshot in their median sequence runs. Their run ranges were 3.07–4.96 ms and 7.03–10.36 ms. These are sequence-average snapshot times, not per-frame latency percentiles. Profiling identifies full-array construction, exponentiation, and event-history scans as the work. Peak Python allocations in separate tracemalloc runs were about 29.3 MB and 29.7 MB, including retained outputs for all 122 snapshots. Those figures are not a constant-memory streaming budget.

Observation age is reported as cursor time minus the latest integrated event, or null for no event. It does not measure sensor-to-display wall-clock latency. Sustained concurrent acquisition backlog is unmeasured. Issue #15 remains open for the final stage, reflective/transmissive evaluation, bounded concurrent work, and sustained timing.

```powershell
$env:GODOT='C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
python -B -m unittest discover -s tools/reconstruction -p 'test_*.py' -v
& $env:GODOT --headless --path prototype --script res://replay.gd -- --manifest=../docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --verify --reconstruct --report=../docs/evidence/2026-11-28/event-reconstruction/replay-controls.json
```
