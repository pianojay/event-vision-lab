# CPU pipeline v1 profile reference

Implemented on `codex/fidelity-integration` for issues #4, #5, #6, and #7. These are named prototype choices, not a universal simulator or dataset contract. The retained component oracles remain independently usable. The new adapter owns configuration, trajectory selection, run lifecycle, stage labels, artifact writing, and replay boundaries.

## Data and ownership

`tools/pipeline/pipeline.py` exposes `Config`, `load_config(path)`, `simulate(config)`, `run(config, output)`, `write_capture`, and `read_capture`. `Config` validates external input before a run. `run` rejects an existing output directory. The pipeline has no wall-clock acquisition or concurrent writers.

The flow is optical fixture, declared reconstruction, sensor candidates, pixel emissions, bounded capture, then event-count display. There is no readout queue. `candidates.csv`, `events.csv`, and `truth.csv` identify different stages. Capture success means completeness relative to pixel emissions, not completeness relative to a physical camera or unseen optical changes.

`ReferenceSensor` owns threshold maps, filtered log intensity, contrast reference, and refractory history for held-input runs. `SampledPixel` owns ideal references for log-linear runs. The exact solver owns each ideal continuous segment. Neither Godot replay nor capture changes sensor state.

## Configuration

The schema is `event-lab-pipeline-v1`. Unknown fields and unsupported schema versions are rejected. Omitted fields take the defaults in `Config`. `config.json` expands all fields and all sensor parameters. `profile_name` describes a selected model; the name does not silently override its fields.

| Field | Meaning and allowed values |
| --- | --- |
| `stream_id` | Caller-supplied nonempty run identity. Use another identity for a new acquisition. Repeated simulations have independent state even if the caller repeats the name. |
| `width`, `height` | Integers from 1 through 256. Row-major coordinates, x right, y down, top-left origin. |
| `duration_ns` | Positive integer duration, up to one hour. Solver time is run-relative binary64 seconds. |
| `sample_period_ns` | Positive integer period. Endpoint and reset samples are included. |
| `epoch_ns` | Nonnegative integer origin. Exported as a decimal string in JSON. Origin plus duration must fit signed int64. |
| `scene` | `edge` or `pulse`. |
| `dark`, `bright` | Positive relative scene-linear intensities. Values must fit the float32 archive. No exposure scaling, clipping, gamma, or silent dark floor. |
| `edge_start_px`, `edge_speed_px_s` | Initial vertical edge position and constant horizontal speed. The bright region is right of the edge. |
| `pulse_knots` | Increasing `[time_ns, intensity]` pairs spanning the run. Intensity is linearly interpolated, not log-interpolated. The pulse fills the image. |
| `spatial` | `exact-area` integrates a unit pixel box exactly for the edge. `midpoint` uses `samples_per_axis` horizontal midpoint samples. The pulse is spatially uniform. No lens PSF or motion blur is modeled. |
| `trajectory` | `exact`, `log-linear`, or `held`, as defined below. |
| `sampling` | `uniform` or `known-boundaries`. The latter adds known pixel-edge boundaries or pulse knots, rounded to integer ns. Knowledge of those times is privileged fixture information. |
| `sensor` | `ideal` or `generic-nonideal`. |
| `sensor_parameters` | Overrides for the retained `SensorProfile`. Effective values are always exported. Unknown parameter names fail. |
| `reset_times_ns` | Strictly increasing interior run times. Samples are inserted at these times. |
| `capture_capacity` | Number of pixel emissions to retain. Zero is valid. Newest events beyond capacity are dropped and counted. |
| `candidate_limit_per_step` | Positive resource guard, at most one million. Exact truth uses a conservative whole-run bound before solving. Log-linear generation checks each step before allocation. Held generation uses the sensor's transactional guard. Exceeding a guard aborts the run. |
| `comparison_gate_ns` | Nonnegative matching tolerance for per-pixel, per-polarity event comparison. |

The CPU prototype also rejects more than ten million sampled pixel values, more than one million scheduled sample intervals, and more than two million generated candidates. These are software resource bounds, not sensor saturation. The exact conservative bound can reject a run whose actual event count would be smaller.

## Optical trajectory and sensor choices

| Choice | Behavior |
| --- | --- |
| Ideal + exact | Exact box-area edge or finite-rise pulse with known monotone segments. The retained timing oracle inverts each threshold with bisection. Optical frame rate does not constrain this privileged reference mode. Requires `exact-area`. |
| Ideal + log-linear | Render at scheduled times, interpolate natural-log intensity between consecutive samples, and retain contrast residuals. Samples do not reveal an unseen pulse or reversal. |
| Ideal + held | Hold the left sample over `[t_i,t_i+1)`. A jump is timestamped at the beginning of the hold. The final sample initializes no subsequent interval and does not produce a terminal jump. |
| Generic nonideal + held | Same left-held optical input, followed by the retained seeded threshold mismatch, brightness-dependent first-order log response, additive dark offset, and refractory event gating. |

Generic nonideal + exact or log-linear is rejected. Ideal profiles reject nonzero mismatch, bandwidth, dark offset, or refractory settings. Ideal defaults have ON and OFF threshold 0.2. Generic defaults have threshold 0.2, threshold sigma 0.01, minimum threshold 0.01, white bandwidth 100 Hz, white intensity 1, minimum bandwidth fraction 0.1, dark offset 0.01, refractory time 1 ms, and seed 17.

The [sensor model reference](../research/sensor/README.md) specifies the equations and clipped threshold distribution. Suppressed candidates still advance the contrast reference. Only emitted events update refractory history. There is no temporal noise, leak, readout arbitration, or camera calibration.

The exact ideal comparison uses the same optical fixture, nominal ON/OFF thresholds, and reset schedule. It excludes nonideal parameters. Nonideal differences from that reference are not automatically implementation errors. The validation report also compares coarse and fine held sampling against a finer run of the same nonideal profile.

## Lifecycle and time

Each `simulate` or `run` call creates a new stream with new state and zero cumulative counts. A seed regenerates the same threshold map under the recorded Python implementation. The integer epoch never enters the sensor's float arithmetic.

At an in-run reset, the previous interval finishes first. Its continuous endpoint crossings remain. Then current optical intensity initializes filter and reference without generating events. The threshold map is retained. Refractory history is cleared. The pipeline's cumulative candidate, emission, and suppression counts remain intact. For a held trajectory, a new optical jump at the reset time belongs to the next interval and is replaced by the explicit reset initialization.

Events are sorted by unquantized `(time, y, x, polarity)` with stable ties. The capture assigns increasing sequence numbers, then rounds relative seconds to integer nanoseconds, nearest with ties to even. Sequence preserves order when different times quantize to the same nanosecond. Absolute CSV time is integer epoch plus relative nanoseconds. Readers subtract the integer epoch before any float conversion. ON is +1 and OFF is -1.

Exact segment endpoint times are reconstructed from their absolute integer boundary to avoid addition drift across resets. Capture accepts at most four binary64 ULPs of endpoint arithmetic roundoff and clamps those endpoint values to the declared duration. Other out-of-range or unordered times fail.

## Artifact and display contracts

`manifest.json` records effective configuration, source revision, dirty status, canonical LF source hashes, Python/platform identity, input dimensions/units, explicit sample times, lifecycle records, stage counts, comparisons, and limits. The source hashes identify uncommitted implementations more precisely than a dirty commit marker alone.

`intensity.f32` packs little-endian float32 frames. Each manifest frame gives offset, byte length, timestamp, and SHA-256. The solver uses unrounded binary64 analytic samples. The archive is a rounded diagnostic record, not the numerical input to a file-based adapter. Reproduce the solver from the effective configuration and identified source.

All captures have `(x,y,t_ns,p,sequence)` CSV columns, integer fields, a SHA-256, stage, stream identity, dimensions, epoch, duration, input/stored/overflow counts, capacity, and an explicit completeness flag. `read_capture` validates hash, schema, stage, metadata counters, dimensions, ordering, bounds, polarity, and sequence. Ground-truth and candidate captures retain all generated records. Only the pixel-emitted capture uses the configured drop-newest capacity.

Godot `prototype/replay.gd` accepts only the pixel-emitted capture, checks its metadata and hash, and reads `events.csv`. It does not load optical frames or ideal truth. The image is a finite sliding-window count mapped with `1-exp(-0.5*count)`. Optional color indicates the sign of the summed polarities within each pixel window. Mixed polarities can cancel in color while count brightness remains positive. Scrubbing recomputes the count window directly from recorded events.

## Remaining scope

The implemented path is offline CPU generation followed by Godot replay. The interactive GPU shader retains its earlier ideal model. Full runtime parity, calibrated/nonideal GPU acquisition, richer optics, full scene rendering, external dataset adapters, and comparison with a pinned upstream simulator remain open. No issue is closed by this prototype.
