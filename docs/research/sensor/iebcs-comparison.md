# Pinned IEBCS comparison

November 28, 2026. This is an executed CPU comparison for [issue #5](https://github.com/pianojay/event-vision-lab/issues/5), not a camera calibration. The [JSON evidence](evidence/iebcs-comparison-v1.json) retains effective parameters, every step's event times, distribution moments, queue counters, dependency versions, source hashes, and timing runs.

## Reproduce

The simulator and its unit tests use only Python's standard library. The external comparison additionally uses NumPy and tqdm in an isolated environment.

```powershell
python -m venv runs/reference-env
runs/reference-env/Scripts/python.exe -m pip install numpy==2.5.5 tqdm==4.70.1
runs/reference-env/Scripts/python.exe -B tools/sensor/compare_iebcs.py --fetch --reference-dir runs/reference-iebcs --report runs/iebcs-comparison.json
python -B -m unittest discover -s tools/sensor -p 'test_*.py' -v
python -B -m unittest discover -s tools/pipeline -p 'test_*.py' -v
```

Omit `--fetch` to reuse the checked cache. The runner validates every external file's canonical raw SHA-256 before import. It fails on altered files rather than normalizing or patching upstream code. The recorded run used Python 3.14.8, NumPy 2.5.5, and tqdm 4.70.1 on Windows 11.

The reference is [neuromorphicsystems/IEBCS at 8fdab5c3](https://github.com/neuromorphicsystems/IEBCS/tree/8fdab5c3d078435d091fa8a94ad657e1fedf0c59). Its `dvs_sensor.py`, `event_buffer.py`, `dat_files.py`, `arbiter.py`, and GPL-3.0 `LICENSE` remain external experiment inputs under ignored `runs/`. No upstream source is copied into the simulator or required by its runtime. The [comparison runner](../../../tools/sensor/compare_iebcs.py) records source URLs and SHA-256 plus Git blob IDs. The first connector-provided copies of two files differed in line endings; the experiment fetched and checked the canonical raw bytes before execution.

## Compatible first crossings and distinct reset behavior

Both models receive identical raw flux holds. The local profile explicitly sets `dark_offset=1`, matching upstream `log(flux+1)`. For each hold, the local fixed time constant matches upstream `tau_parameter_us * 1000 / (flux+1)`. This aligns that held case; it does not claim that the models' general brightness-to-bandwidth laws match.

Sixteen cases cover flux 10 to 20 and back, 1000 to 2000 and back, refractory periods of 0 and 2000 microseconds, and update periods of 1000 and 20000 microseconds. The first crossing is checked against the analytical RC solution and upstream's integer-microsecond timestamp. Maximum difference is 0.122442 microseconds. First-crossing polarity agrees in every case.

Upstream cannot set its background rate to zero. The run uses 0.001 Hz per polarity and seed 17, and asserts that the earliest scheduled background event is after each 20 ms fixture. Smaller rates can exceed Windows NumPy's `randint` int32 limit during upstream initialization. No upstream behavior was patched to bypass this constraint.

Later crossings deliberately remain visible in the report. With a 10-to-20 flux step and 2 ms refractory period, the local gate emits three events while upstream emits two. Upstream updates its reference at the end of its blind/reset period. The local gate consumes all optical crossings and only suppresses emissions. Even zero-refractory later timestamps can differ through accumulated upstream microsecond truncation. Agreement at the first crossing does not establish whole-stream equivalence.

## Statistical and timestep checks

For constant flux 100, 256 pixels, one second, and 8 Hz per polarity, the local Poisson source produces these count moments per pixel:

| Polarity | Mean | Population variance |
| --- | ---: | ---: |
| ON | 8.214844 | 7.770248 |
| OFF | 7.968750 | 7.084961 |

The checks compare these moments against the declared Poisson rate with stated statistical tolerances. Local event timestamps and counts have identical digests with 1 s, 50 ms, and 10 ms updates. The unit suite also checks seed replay, independent ON/OFF streams, and exact leak-schedule partitioning.

IEBCS uses a fixed period and a random initial phase. At 50 ms and 10 ms updates, every upstream pixel emits eight events per polarity, giving zero count variance over this exact one-second window. A single one-second update emits only one per polarity because upstream checks each noise schedule once per update. This result demonstrates an upstream timestep limit and a different stochastic law. It is not evidence that the local model reproduces IEBCS background activity.

The initial 4096-pixel threshold maps also pass mean and spread checks for nominal 0.2 and sigma 0.03. This compares initial distributions only. Upstream redraws a threshold after an event; the local map persists. Their RNGs and clipping floors differ.

Leak-like periodic candidates have an analytical unit/partition check, but no matched upstream leak-current reference. They do not drift the optical reference. See the [generic model contract](generic-model.md).

## Readout is a separate experiment

The runner feeds four simultaneous events to upstream's `BottleNeckArbiter` and the local bounded FIFO. Upstream returns two events at 0 and 40 microseconds and retains two. The local capacity-two queue delivers at 10 and 20 microseconds and drops two, while retaining original sensor timestamps of zero.

These are different queue laws. Upstream labels this arbiter a mock; its processing time depends on backlog and it rewrites event timestamps. The local queue has fixed service time per event, bounded capacity, and separate event and delivery times. This comparison does not validate a real camera bus or claim arbiter parity.

## Measured CPU cost and limits

An 8 by 8 fixture contains 100 ms of alternating held intensity at 10 ms intervals. The enabled run produces 1728 optical, 128 leak, and 107 temporal candidates. The timed region includes sensor evolution, readout, capture arrays, and metadata; it excludes disk serialization. Five alternating runs per configuration check stage conservation and confirm that each mechanism runs.

On the observed Intel Core i7-1065G7, with eight logical CPUs, the enabled configuration takes a median 210.35 ms, range 176.78 to 237.68 ms. Disabled activity takes a median 252.04 ms, range 184.72 to 280.51 ms. The ranges overlap, so this run does not establish a performance difference. A separate profile identifies interval-state copying as the dominant cost. Concurrent machine load was uncontrolled. This is an untuned small offline implementation, not a real-time or GPU throughput result.

The 37 sensor tests and 15 existing CPU pipeline tests pass. The original held-reference implementation and all 21 original tests are unchanged. No GPU or GUI was launched.

Issue #5 remains open. This work implements generic sources, a bounded queue, an optical-frame adapter, and scoped upstream comparisons. Physical leak-current interactions, matching stochastic/reset models, camera-specific calibration and held-out real data, and live GPU integration remain outside the validated result. No v2e reproduction or complete IEBCS parity is claimed.
