# Event processing toolkit

The replay toolkit applies post-event ROI, spatial bins, polarity selection, and a temporal representation to one immutable pixel-emitted capture. It uses no intensity or geometry input. Acquisition and capture counters retain their original meanings.

## Run and save settings

Run the existing replay launcher with a pipeline manifest. The replay window shows the full-frame raw event window beside the processed view. Processing controls are available as selectors, numeric inputs, and the following shortcuts.

| Control | Operation |
| --- | --- |
| ROI bounds | Set sensor-coordinate half-open `[x0,y0,x1,y1)` bounds |
| F / Full | Restore the full sensor extent |
| E / Empty | Select an empty ROI |
| B / bin selector | Cycle 1×1, 2×2, and 4×4 bins |
| O / polarity selector | Cycle both, ON-only, and OFF-only output |
| V / representation selector | Cycle exact window, decaying counts, and time surface |
| Window ms | Set the finite window width in event time |
| Decay tau ms | Set the exponential time constant in event time |
| Sum per bin / Divide by bin area | Set display normalization |
| Display gain / ON-OFF colors | Change display brightness or polarity colors |
| Space / Play-pause | Pause the event-time cursor |
| R / Replay from start | Resume from time zero |
| Scrub / Slower / Faster | Set cursor or replay rate without changing the event window |

Every processing change recomputes captured history at the current cursor. It does not reset the sensor or change source rows. Numeric text fields own their input. Modified or repeated shortcut presses do not cycle tools.

**Save settings** writes processing parameters to the displayed JSON path. **Load settings** validates that file and retains current settings if validation fails. The default path is Godot's `user://event-processing.json`. `--processing-config=<path>` selects a startup file. The saved JSON is also accepted by the Python CLI. Playback rate and polarity colors are display-session settings. Reconstruction settings use a companion file described in [the reconstruction guide](event-reconstruction.md).

```powershell
python -B tools/processing/event_processor.py --manifest docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --config docs/evidence/2026-11-28/event-toolkit/replay-controls.json.settings.json --cursor-ns 160000000 --output runs/processed.json
```

## Numerical contract

The integration module is `prototype/processing/event_processor.gd`. `configure(settings, sensor_size)` retains history, `consume(rows)` copies timestamp-ordered `[x,y,t_relative_ns,p]` rows, `snapshot(cursor_ns)` returns a new result, and `reset()` clears history. A sensor dimension change requires a reset. Timestamps and count accumulation use integers. Python uses arbitrary-size counts, and Godot uses signed 64-bit counts rather than 32-bit image arrays.

ROI selection happens before binning. Bin coordinates are local to the ROI origin, which remains explicit as `origin=[x0,y0]` in every snapshot. A bin covers sensor coordinates `[x0+b*i, min(x1,x0+b*(i+1)))` and the corresponding y interval. Partial edge bins are retained. Their actual areas appear in `bin_areas`.

ON and OFF values remain separate. Opposite events in one bin never cancel. `received_count` includes all loaded rows, `incoming_count` includes rows through the cursor, `roi_count` follows ROI selection, and `selected_count` follows polarity selection. `visible_count` counts contributing rows. For exponential modes it includes all selected past events, even when floating-point exponential underflow makes their numerical contribution zero.

| Representation | Value per bin and polarity |
| --- | --- |
| Exact window | Count of events with `cursor-window < t <= cursor` |
| Decaying counts | Sum of `exp(-(cursor-t)/tau)` for all events through the cursor |
| Time surface | `exp(-(cursor-last_event)/tau)`, or zero if the bin has no event |

Time surfaces take the last timestamp after binning, separately for each polarity. A burst increases decaying counts but does not increase a time surface. Colors mix the two nonnegative channels. Monochrome brightness uses their sum. Display gain maps activity with `1-exp(-gain*activity)`. Optional bin-area division occurs only in display and does not create additional information.

Snapshots recompute from retained event history. This supports deterministic pause, backward scrub, and configuration comparisons. Its work grows with capture length. It is an offline replay baseline. A [separate bounded streaming class](streaming-processing.md) supports the live acquisition boundary without backward scrub. Post-event ROI does not save completed rendering or sensor-generation work.

## Recorded comparisons

Run `tools/processing/compare_capture.py --manifest <manifest> --output <directory>` to reproduce the comparison artifacts. The retained [ideal capture comparison](evidence/2026-11-28/event-toolkit/ideal/comparison.svg) and [nonideal comparison](evidence/2026-11-28/event-toolkit/nonideal/comparison.svg) use the same 160 ms cursor and fixed display gain. Each report contains 54 configurations and a separately declared sparse-feature fixture. Both source CSV hashes remain unchanged.

The ideal moving edge contributes 48 events within 10 ms and 192 within 40 ms. At 40 ms, 1×1, 2×2, and 4×4 bins conserve all 192 events while reducing active output bins from 64 to 16 to 4. Brighter coarse bins reflect accumulated count, while the wider window retains a longer trail. The nonideal capture contributes 193 events over 40 ms. Its active-bin counts are 78, 24, and 8, including dispersed activity that binning merges.

The sparse fixture places adjacent opposite-polarity events at x=1 and x=2. A 4×4 bin merges their locations but retains both counts. This demonstrates lost detail and polarity overlap. It is a declared synthetic fixture, not a representative stage or user perception evaluation. The ideal capture has no OFF events, so OFF-only output is empty. The nonideal comparison retains both channels and noise-related clutter.

## Verification and remaining work

Fourteen Python tests pass, including one headless Godot comparison across 81 configurations, six cursor visits, reconfiguration, and reset. That comparison checks 648 snapshots against the Python reference. The replay's [control report](evidence/2026-11-28/event-toolkit/replay-controls.json) records 16 passing checks of actual signals and keyboard events, including saved settings, scrub, speed, and raw preservation. These are headless behavior checks, not GPU pixel validation.

```powershell
$env:GODOT='C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
python -B -m unittest discover -s tools/processing -p 'test_*.py' -v
& $env:GODOT --headless --path prototype --script res://replay.gd -- --manifest=../docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --verify --report=../docs/evidence/2026-11-28/event-toolkit/replay-controls.json
```

Issues #11–14 remain open for live acquisition integration, representative task comparisons, and visual validation. This module does not change the live GPU renderer or sensor.
