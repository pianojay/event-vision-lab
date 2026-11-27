# Bounded streaming event processing

`prototype/processing/streaming_processor.gd` provides forward-only processing for the live event boundary. `tools/processing/streaming_processor.py` is its numerical reference. Replay continues to use the full-history processor because it supports backward scrubbing and recomputation after configuration changes.

## API and lifecycle

The streaming class exposes the same `configure(config, sensor_size)`, `consume(events)`, `snapshot(cursor_ns)`, and `reset()` operations. Events are integer `[x,y,t_relative_ns,p]` rows in timestamp order. Consume every batch through its declared cursor, then request the snapshot. A snapshot cannot precede the last consumed event or the preceding snapshot. Events arriving before the current cursor are rejected. Ties at the cursor remain valid.

The class consumes copies of values into aggregate state. It does not modify or retain the source event arrays. The acquisition owner keeps the raw capture. No renderer or sensor resource belongs to this processor.

Changes to ROI, bins, polarity, representation, temporal parameters, dimensions, or capacity clear processing state and counters. The current clock remains unchanged. `configuration_generation` increments so callers can label the new processing interval. Gain and display normalization retain aggregate state. `reset()` clears state and permits a new clock origin, for example after an acquisition reset. None of these calls changes acquisition by itself.

ROI, partial-bin coordinates, polarity channels, and temporal equations match the [offline processing contract](event-processing.md). Counts are relative to the current processing interval. Acquisition and capture counters remain separate in the caller.

## State and overflow

| Mode | Retained state | Snapshot work |
| --- | --- | --- |
| Exact window | Fixed-capacity event ring and running ON/OFF counts | Expire old events, then copy output bins |
| Decaying counts | ON/OFF aggregate impulses and last-update times per bin | Decay each bin to the cursor |
| Time surface | Last ON/OFF timestamps per bin | Evaluate each bin's age |

The window parameter `window_capacity` defaults to 100,000 retained events and accepts 1 through 1,000,000. The ring stores timestamp, bin index, and polarity. Expiry removes events at or before `cursor-window_ns`, preserving the exact lower-exclusive boundary. Opposite polarities use separate running counts.

If the window ring is full, the processor drops the newest selected event from the processed view. `window_overflow_count` increments. `selected_count` still includes that input, while `visible_count` includes only retained events. `complete_since_reset` stays false after any overflow until reset or a semantic configuration change. The flag describes the processing interval, even after the overflowing window has expired. Raw capture is unaffected.

Each event is inserted and removed at most once. Work scales with the incoming batch and output dimensions, rather than accumulated stream duration. A single large batch or expiry of a full ring can still require capacity-sized work. No constant wall-clock latency is promised. Decay and time-surface modes retain no event queue. Their state scales with output bins, and their sums match the offline equations up to floating-point rounding.

The Godot ring uses 13 bytes of packed payload per capacity slot, plus array overhead. Four per-bin arrays hold counts/activity and timestamps. Snapshot output is a fresh copy. `resident_event_count`, `window_capacity`, `window_overflow_count`, and `state_cells` expose the relevant resource state. The Python reference uses a bounded deque, so its object overhead differs from Godot.

## Verification

Twenty-three processing tests pass, including the original fourteen offline tests and nine streaming tests. They check forward snapshots against the offline processor across 81 configurations, opposite-polarity overflow, exact expiry, batching, late-event rejection, reset, and configuration changes. Display-only changes preserve history.

The Godot comparison covers 85 streaming scenarios and 735 snapshots. Three scenarios consume 20,000 events each. The window keeps only its active bounded queue, and exponential modes keep no event rows. A separate 10,000-event Python test deliberately fills a 32-event queue and reports exactly 9,968 dropped events. No source events are changed.

```powershell
$env:GODOT='C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
python -B -m unittest discover -s tools/processing -p 'test_*.py' -v
python -B tools/processing/compare_stream_capture.py --manifest docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json --output runs/stream-comparison.json
```

The recorded [ideal](evidence/2026-11-28/event-toolkit/stream-ideal.json) and [nonideal](evidence/2026-11-28/event-toolkit/stream-nonideal.json) comparisons check eighteen configurations each. They consume only events available at each capture timestamp and compare counts and activity with the offline reference. The preliminary [3D camera comparison](evidence/2026-11-28/event-toolkit/stream-camera-preintegration.json) uses the exact source hash in its report. No optical intensity enters processing.

These checks establish bounded state and numerical behavior. Live acquisition integration, workload latency, backlog, and sustained rendering remain unmeasured here. The reconstruction baseline remains offline and full-history; this class does not make reconstruction bounded.
