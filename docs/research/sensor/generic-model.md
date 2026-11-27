# Generic background activity and readout

This offline CPU model extends the unchanged [held-input reference](README.md). It is generic and uncalibrated. The live Godot sensor remains ideal.

## Pixel and activity state

[`GenericSensor`](../../../tools/sensor/generic_sensor.py) composes the old exact held-input optical solver with two optional candidate sources. All defaults disable the new sources. The optical solver owns its filtered log intensity, contrast reference, and persistent threshold map. The composed sensor owns background schedules and the one shared refractory gate.

- `leak_log_per_s` produces periodic ON candidates at `C_on / leak_log_per_s` seconds per pixel. Phase starts at zero after reset, with the first event after one period. Threshold mismatch changes that pixel's period. This is a leak-like phenomenological source. It does not model leak current, drift the optical reference, or reproduce the interaction of physical leakage and signal crossings.
- `temporal_on_hz` and `temporal_off_hz` specify independent homogeneous Poisson candidate rates in events per pixel per second. Interarrival times are exponential. Each pixel and polarity has its own seeded Python random stream. This is background activity, not calibrated photon shot noise, analog voltage noise, or threshold jitter.
- Both sources enter once at the comparator-candidate boundary. They do not also change the optical intensity, contrast reference, or threshold map. Enabling both adds their rates. No v2e or IEBCS noise-law equivalence is implied.

Candidates retain `x, y, t_s, p, origin, emitted`. Optical, leak, and temporal candidates share the existing refractory event-gating approximation. All optical crossings consume the optical reference, including suppressed crossings. Synthetic candidates never change that reference. Only emissions update the shared gate. Ties sort by time, y, x, polarity, then origin in optical/leak/temporal order. This tie order applies within each call; preserve call order at an interval boundary.

Schedules use continuous absolute arrival times rather than drawing a probability per timestep. Subdividing a constant hold preserves synthetic arrivals exactly. The optical solver retains its float64 roundoff limits. Reset preserves the threshold map and restarts the noise streams and leak phase. The interval candidate guard aborts all state changes, including random draws. This atomicity uses a state copy and adds CPU cost.

## Camera readout

[`ReadoutQueue`](../../../tools/sensor/readout.py) accepts ordered pixel emissions as integer-nanosecond `ReadoutEvent` records. Its bounded FIFO is independent of the pixel model.

- `capacity_events` counts all accepted events awaiting delivery, including the event in service and events in fixed propagation latency.
- `service_ns` is the serialization time per accepted event. `latency_ns` is added after serialization and may overlap the next event's serialization.
- A full queue drops the newest arrival. Delivery at a timestamp precedes admission of new arrivals at that timestamp.
- A `Delivery` retains the original event timestamp and a separate `delivered_ns`. Readout delay must not replace the sensor timestamp.
- `advance(events, until_ns)` admits events between the previous watermark and `until_ns`, inclusive, and delivers only through that watermark. A later empty batch can drain pending work. A zero-capacity queue drops every input. Zero service and latency are an explicit bypass when capacity is positive.

Counters separate sensor candidates by origin, refractory suppression, pixel emissions, readout input, acceptance, drops, delivery, pending count, and peak occupancy. Capture truncation and missing optical inputs are downstream and upstream accounting respectively. Neither is readout loss.

## Checks

```powershell
python -B -m unittest discover -s tools/sensor -p 'test_*.py' -v
```

The checks retain every original analytical reference test. New checks cover disabled-source equivalence, leak units, exact schedule partitioning, independent random streams, reset reproducibility, Poisson count moments, the common refractory gate, atomic failure, queue bursts, boundary ties, delayed delivery, and batching invariance. These checks validate the declared model rather than a real camera.
