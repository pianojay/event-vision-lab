# Composed-stage validation commands

The validation tools exercise the live stage through `main.gd`. CPU tests and headless parsing verify the tools themselves. They do not establish GPU correctness, sustained performance, or output accessibility. Those results require separately recorded real-context runs.

## Run one profile

Run the GPU jobs serially on AC power. The Windows launcher starts one hidden, off-screen Godot process with the Windows display driver and Vulkan Mobile renderer. It never injects operating-system input or requests foreground focus. Timeout handling kills only the process it started. Each run requires a new output directory.

For a Git archive copied into a writable run directory, pass `--source-revision` with the full source commit SHA. The launcher hashes the actual project files and records the declared revision. It rejects a nested archived project without this option instead of accidentally attributing it to the enclosing repository.

The simulator has no NumPy dependency. Output analysis uses NumPy in the existing isolated environment. Plain runtime launch and reporting use Python's standard library.

```powershell
$python = 'D:\ChatGPT\Event Game\runs\reference-env\Scripts\python.exe'
$godot = 'C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
& $python -B tools/validation/run_hidden.py --engine $godot --project prototype --scenario tools/validation/scenarios/smoke.json --output runs/validation-smoke --timeout 60
& $python -B tools/validation/run_hidden.py --engine $godot --project prototype --scenario tools/validation/scenarios/stage-processing.json --output runs/validation-processing --timeout 750
& $python -B tools/validation/runtime_report.py runs/validation-processing
```

`stage-processing.json` and `stage-inference.json` request ten seconds of warmup and at least 600 actual wall seconds of measurement. Both use an 80 by 60 ideal event sensor, a 16,666,667 ns sample period, and synchronous streaming acquisition without optical archives. They include a 12 Hz strobe segment between measured seconds 200 and 400. The inference variant enables synchronous relative-grayscale integration. These are candidate profiles to measure, not advertised operating envelopes.

The runtime continues for the requested wall duration even if simulated time advances slowly. It requires event batches and emitted events. A scenario acknowledgement must contain every requested effective value. Scripted V and R events must change the selected observation and emit the reset signal, respectively, before a subsequent rendered-frame acknowledgement. An ignored reset fails the run.

At the wall limit, `validation_finish()` stops dispatch, drains the in-flight sample, and finalizes the streaming writer at its actual cursor. The report retains that finalization result and does not mark the configured one-hour simulation complete. Supplied sustained profiles disable recording; their stream can finalize without producing an event CSV archive.

Use `runtime.jsonl`, `process.jsonl`, and `launcher.log` to inspect progress without blocking on the whole run. The final files contain:

- `runtime-report.json` records actual event/sample counts, wall and simulated duration, median/p95/p99 frame intervals, batch intervals, sample-dispatch service time, inference observation age, scenario acknowledgements, and effective stage settings.
- `launcher.json` records source hashes and Git state, engine command, hardware/driver inventory, power scheme, sampled AC status, process outcome, and process-memory trend. `process.jsonl` retains one-second working-set/private-byte samples from Windows `GetProcessMemoryInfo`.
- `sustained-report.json` reports evidence completeness. It cannot pass with a short run, missing sample timings, battery or unknown-power samples, missing dense-phase work, ignored inputs, or output-capture instrumentation.

`sample_service` measures dispatch to the main-thread acquisition callback, before the processing work. Frame intervals include the composed application and validation callbacks. Batch intervals expose stalls separately. Processing overflow is accumulated across observed resets; raw and processed windows retain separate losses. Snapshot counters retain their original meanings. In particular, an omitted capture archive leaves events unretained; that count does not mean the live processor lost them. Readout loss is null because this profile has no readout model.

Inference age is the acquisition cursor minus the inference observation cursor. A synchronous estimator can report zero simulated age while the whole simulation runs slower than wall time. Scripted input latency ends at Godot's post-draw signal. It excludes a physical device, operating-system input delivery, compositor presentation, and monitor scanout.

The memory slope is a least-squares fit over sampled private bytes for the whole owned process, including warmup and instrumentation. It is an observation, not a leak diagnosis. AC status is checked at each process sample. One run cannot support a comparative performance claim. No GPU microkernel measurement substitutes for this composed application run.

## Analyze actual rendered output

Run the limited and legacy profiles separately. These short clips include the full viewport, including controls, labels, raw/processed panes, and the primary observation view.

```powershell
& $python -B tools/validation/run_hidden.py --engine $godot --project prototype --scenario tools/validation/scenarios/output-limited.json --output runs/output-limited --timeout 90 --capture-output
& $python -B tools/validation/run_hidden.py --engine $godot --project prototype --scenario tools/validation/scenarios/output-legacy.json --output runs/output-legacy --timeout 90 --capture-output
```

After every `RenderingServer.frame_post_draw`, the script reads the actual root viewport as RGB8 and streams it over loopback to the Python receiver. The receiver retains per-pixel, per-channel minima/maxima, a mask of pixels observed as saturated red, and frame identities/times. It saves first/middle/last PNGs and a compressed `rgb-bounds.npz`, with SHA-256 hashes in `output-analysis.json`. It does not retain all frame images. Missing rendered-frame identities, a short clip, or an interrupted connection makes the result inconclusive. Capture overhead affects cadence, so these clips do not serve as throughput evidence.

The analyzer implements a conservative sufficient area bound based on [W3C's WCAG 2.2 flash guidance](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html), checked November 28, 2026. It converts sRGB bytes to linear relative luminance. A pixel is a general-flash candidate if its whole-clip channel extrema could produce a luminance change of at least 0.1 with a darker value below 0.8. Every changed pixel observed in a saturated-red state is a red candidate, without using a chromaticity exemption. This intentionally overestimates candidate area.

The union includes all candidate pixels across the whole clip, even if they change at different times. The analyzer finds the largest union area in any 341 by 256 reference-pixel rectangle. A fraction strictly below 25% is a sufficient bound for that recorded SDR output at one captured pixel per reference CSS pixel. The union contains every possible simultaneous flash region, so its area bounds every individual instant. This calculation does not rely on adjacent-frame differences or assume that slow fades remain small.

A failed bound is **inconclusive**, not a finding that the output is unsafe or fails WCAG. A pass covers only the recorded viewport, conditions, scale, and clip after warmup. It does not establish app-wide conformance, startup behavior, unseen modes, zoom, HDR, arbitrary viewing distance, physical display calibration, or human usability. Extrema combine channels from different instants; this can enlarge the bound. The saturated-red observation mask avoids inventing a red state from unrelated grayscale channel extrema. When that mask is absent, standalone analysis conservatively uses every possible red corner of the extrema box.

```powershell
& $python -B tools/validation/output_bounds.py runs/output-limited/rgb-bounds.npz --report runs/output-limited/recomputed-bounds.json
```

Standalone reanalysis checks the numerical bound only. The original capture report supplies completeness and provenance.

## Evaluate paired stage observations

Generate eighteen prescribed acquisition inputs, one treatment/control pair per station, and a paired observation specification:

```powershell
& $python -B tools/validation/make_scenarios.py runs/station-pairs --pairs
```

The station order follows the composed stage's nine IDs. Pairs select each material's treatment flag. Transmission/refraction use a moving excitation stripe, fluorescence/phosphorescence use a finite excitation pulse, and the remaining stations use moving light. Run these inputs through the diagnostic acquisition route and place each `manifest.json` under its matching control/treatment directory. The parent GPU runner owns those jobs.

```powershell
& $python -B tools/validation/observations.py runs/station-pairs/observations.json --report runs/station-pairs/observations-report.json
```

The evaluator reads only complete, hash-verified `pixel-emitted` event CSVs. Inputs are integer events, declared ROI, time interval, and a predeclared relative-count threshold. It reports polarity counts, active pixels, event centroid displacement, temporal counts, and paired count/centroid differences. Optional `score_truth.count_response_difference` is consumed only after prediction, for scoring. Ground-truth optical images never enter the estimator. Declared illumination metadata is retained as provenance.

This baseline tests whether a selected process produces a detectable event-count change under its paired control. It does not classify materials, recover geometry, or establish human performance. A zero count difference does not prove optical equivalence. Review ROI visibility and paired controls before interpreting the results; the generated full-sensor ROIs are explicit initial choices.

## Verify the tools without a GPU run

```powershell
& $python -B -m unittest discover -s tools/validation -p 'test_*.py' -v
& $godot --headless --path prototype --script res://tests/runtime_scenario.gd --check-only
```

Synthetic tests include full-field flashes, slow fades whose adjacent changes remain small, saturated-red changes, a small flashing area, fixed bright output, missing frames, ROI/polarity/motion summaries, and short-run rejection. No real-context result is implied by those tests.
