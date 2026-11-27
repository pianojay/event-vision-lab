# Live 3D acquisition profile

`gpu-ideal-log-linear-v1` connects the analytic 3D lab to complete timestamped event capture and event-only replay. It is an ideal sampled-input profile. Generic nonideal CPU profiles remain offline.

## Run a prescribed experiment

Use a new output directory for each run. The launcher refuses an existing capture directory.

```powershell
./run-lab.ps1 -AcquisitionConfig tools/acquisition/configs/sphere-light.json -EventCaptureDirectory runs/sphere-light -EvidenceDirectory runs/sphere-launch
python tools/acquisition/recorded_input.py runs/sphere-light/manifest.json --report runs/sphere-light/comparison.json
./run-pipeline.ps1 -ExistingRun runs/sphere-light -Replay
```

Repeat with `tools/acquisition/configs/camera-occlusion.json`. The first scene keeps the matte sphere and camera stationary while a point light orbits. The second moves the camera around a stationary sphere and foreground box with fixed illumination. Both use `stage_controller.gd`, the same optical shader, the same sensor, and the same capture writer. The room remains available in the interactive profile.

`tools/acquisition/configs/interactive.json` captures ten seconds of simulation with the existing lab controls. Each archived sample contains the actual FP32 scene, camera, illumination, sensor, and display-decay parameters. `static.json` is the silence control. `reset-overflow.json` exercises an interior reset, seven-event capture capacity, and a large integer epoch.

Prescribed runs disable scene controls. P pauses, R requests a sensor reset, and V/C change the observation. Interactive runs allow all existing scene controls and presets. Presets request a sensor reset. A threshold edit preserves the current reference and starts a new threshold-count anchor. The OFF threshold follows the configured OFF/ON ratio when the interactive threshold slider changes.

## Configuration and bounds

`run_config.gd` applies defaults, then fields from the supplied JSON. The launcher records the Git revision separately. Interactive changes apply at the next dispatched sample and are retained in its parameter array. Unknown keys and unsupported profile, sensor, trajectory, or floor combinations fail before GPU acquisition.

| Field | Supported values |
| --- | --- |
| `profile_name` | `gpu-ideal-log-linear-v1` |
| `sensor`, `trajectory` | `ideal`, `log-linear` |
| `width`, `height` | Integer 1 through 256 |
| `scene` | `sphere-light`, `camera-occlusion`, `static`, `interactive` |
| `duration_ns` | Integer 1 through 3,600,000,000,000, subject to resource limits |
| `sample_period_ns` | Positive integer no greater than duration |
| `epoch_ns` | Canonical decimal string; epoch plus duration fits signed int64 |
| `stream_id` | Nonempty string |
| `on_threshold`, `off_threshold` | Finite 0.001 through 10, quantized to the actual GPU FP32 values |
| `intensity_floor` | Fixed numerical floor 0.000001 |
| `reset_times_ns` | Increasing interior integer times; inserted into the schedule |
| `capture_capacity` | Integer 0 through 2,000,000; drop newest after capacity |
| `candidate_limit_per_step` | Integer 1 through 1,000,000; failure aborts the interval/run |

A run permits at most 10,000 optical frames, ten million sampled pixel values, and two million generated events. The generated-event bound keeps the per-polarity integer-valued FP32 counters below their exact-integer limit of 2^24. Capture overflow does not reduce generated counts or stop the sensor. Resource failure produces `failure.json` and no successful manifest. Invalid crossing diagnostics also retain the failing optical/diagnostic buffers and sample parameters.

The representative settings are 80 by 60 pixels, one second, and 8,333,333 ns sample period. They produce 122 optical samples including initialization and the exact terminal time. Synchronous readback processes one scheduled sample at a time. If rendering or export takes longer, simulation slows. No scheduled samples are skipped. The bounds describe supported resource use; they do not promise real-time operation or a universal numerical error bound.

## Optical and sensor boundary

`optical.glsl` writes scene-linear RGB and pre-floor scalar detector intensity in RGBA32F. The scalar is the fixed weighted RGB sum. There is no exposure integration, lens PSF, automatic exposure, or temporal antialiasing. `sensor.glsl` consumes this texture in a separate dispatch. Zero is archived unchanged, and the sensor applies the declared numerical floor before taking the natural logarithm. The manifest counts clamped sample values. This floor is not a calibrated dark response.

The sensor maintains an initial log-intensity anchor and separate ON/OFF threshold-level counts. The reference offset is `N_on*C_on - N_off*C_off`. Threshold products and their subtraction use explicit FP32 operations. Counts are estimated by division and checked against the next representable level. There is no additive count bias. The anchored representation avoids repeated absolute-reference addition drift when intensity returns exactly to its starting value.

Every interval exports eight FP32 values per pixel:

```text
reference_offset, previous_log_minus_anchor, current_log_minus_anchor,
signed_count, prior_on_count, prior_off_count, on_threshold, off_threshold
```

`crossings.gd` expands every threshold level using those recorded counts and parameters. It orders unquantized local fractions by fraction, y, x, and polarity before rounding local nanosecond offsets to nearest, ties to even. Host interval starts and epochs remain integers. This is a complete crossing expansion, not recovery from the last timestamp texture. The GPU count/display textures remain available for ordinary fast viewing.

The pure expansion function is independent of the writer. `main.gd` emits `event_batch(events, cursor_ns)` with immutable-by-convention rows `[x,y,t_relative_ns,p]`, then `acquisition_reset(cursor_ns)` after a reset boundary. Processing can consume these rows without reading optical textures. `latest_event_batch` exposes the last batch for integration. Capture storage limits do not truncate the emitted live batch.

## Lifecycle and serialization

Initialization samples time zero and emits nothing. A requested or scheduled reset first finishes the preceding interval, then dispatches a same-time reset using the current optical input. The reset clears sensor/display history. It preserves cumulative capture counters and does not reset optical material state. Current stages have no material population state.

Pause prevents new sample dispatch and freezes the acquisition clock. An already dispatched interval can complete. Queued optical edits take effect on resume. Observation changes do not reset acquisition. Host event time uses integer interval origins and local fractions. The optical shader still receives FP32 phase/time and the legacy display uses FP32 time; long-duration optical phase accuracy and uncaptured fast-mode long-run precision are not established by this profile.

Artifacts use the existing `event-lab-pipeline-v1` envelope and `event-lab-capture-v1` pixel-emitted metadata. `events.csv` keeps `x,y,t_ns,p,sequence`. `intensity.f32` is the actual FP32 detector input, with per-frame offsets and hashes. `diagnostics.f32` retains complete interval diagnostics. The manifest records effective settings, all frame parameters, lifecycle, source hashes, hardware, clamp counts, generated/stored/dropped counts, and synchronous readback time. Event-only replay reads the capture and does not load either optical or diagnostic files.

The independent `recorded_input.py` reference consumes the archived FP32 intensities and thresholds. It computes natural logs and anchored threshold crossings in binary64. It never consumes GPU diagnostic state while solving reference events. Diagnostic expansion separately verifies that the CSV equals the exact bounded GPU emission prefix. This distinguishes sensor numerical differences, missing/extra emissions, timestamp errors, and capture overflow.

## Evidence and limits

The [recorded evidence](../evidence/2026-11-28/live-acquisition/README.md) includes the real-context baseline, integration checks, CPU/headless checks, failed numerical comparisons, and successful representative comparisons. The strict event-count and polarity gate remained unchanged during the fixes. The 100 microsecond timestamp gate was declared before the first stage comparison. It is an experimental acceptance gate for these samples, not a guarantee at arbitrary near-threshold or low-slope inputs.

The live profile does not add a calibrated camera, nonideal sensor behavior, readout arbitration, reconstruction, a larger material stage, adaptive optical sampling, or sustained performance evidence. Endpoint samples can miss changes between samples. The legacy uncaptured interactive path retains its wall-paced skip policy and has no newly validated long-run precision or throughput guarantee. Issues #4, #7, and #9 retain their broader criteria.
