# Proposed timing and diagnostic-event contract

Status: **Timing proposal v0.1**, November 22, 2026, for coordinator review. No shared runtime layout, Godot API or other track's implementation is changed by this document. The offline implementation is [timing_reference.py](../../../tools/timing/timing_reference.py); issue: [#4](https://github.com/pianojay/event-vision-lab/issues/4).

## Input and initialization

At the timing boundary use run-relative, finite, nonnegative **simulation time**, independent of presentation and wall time. Samples increase strictly, including an in-run reset. A new run starts a new clock/stream. Reset initializes the pixel reference to the new input without events; it does not invent an observed transition across reset.

The offline fixture supplies `L=ln(I_relative)` in dimensionless natural-log units directly, avoiding gamma, color-space and logarithm-clamp ambiguity. Positive linear intensity is `exp(L)` when needed. A runtime adapter must declare its linear-intensity encoding, floor and conversion to log input. No lux, photocurrent or camera calibration is implied by these fixtures.

Separate positive and negative threshold magnitudes `C_on,C_off>0` advance the stored reference by the corresponding amount for each crossing. Retain residuals across intervals and polarity reversals. The offline reference has no physical noise, bandwidth, refractory period or readout suppression; future sensor models must label those effects separately.

## Interval and timing semantics

Each interval owns `(t_previous,t_current]`. Equality at a threshold triggers, including a touch at a known extremum; do not duplicate a turning-point event in the following interval. Initialization/reset owns no events. Discontinuous jumps are **not supported** by the current continuous fixtures: use finite-rise signals here, and agree on a pre/post-transition convention before adding ideal steps to the runtime API.

The sampled model assumes linear **log intensity** between observations. Emit all crossings with their individual interpolation times. The continuous oracle instead partitions known analytic monotone intervals and inverts the crossing level using 60 bisections; known endpoint matches are assigned exactly to that endpoint. Its `1e-12` log-unit endpoint allowance handles floating-point arithmetic. It is not the shader's `+1e-5` count bias, a physical uncertainty or a guarantee near arbitrary nearly tangent signals.

For runtime clocks, propose an integer epoch plus bounded local time, with an explicit origin and precision budget. The offline tool uses binary64 seconds relative to the run and adds the integer epoch **after** nanosecond conversion. Do not put an ever-growing absolute-seconds value into an FP32 buffer and assume microsecond precision. Exact GPU types/epoch-rebasing and resource bindings remain the coordinator's decision. Nanosecond units in a file describe encoding, not physical accuracy.

## Diagnostic records and capture

The tool's `event-lab-timing-csv-v1` fields are:

| Field | Meaning |
| --- | --- |
| `x,y` | Nonnegative integer pixel coordinates; scalar fixtures use `(0,0)` |
| `t_ns` | Integer `epoch_ns + round(t_relative_seconds*1e9)`; nearest, ties-to-even |
| `p` | Integer `+1` for ON, `-1` for OFF |
| `sequence` | Zero-based contiguous capture order, preserving deterministic input order at timestamp ties |

Upstream producers supply chronological events; the sink rejects decreasing time and preserves ties. A multi-pixel runtime must establish a deterministic producer/tie order before capture, and record sensor dimensions and coordinate origin. The parser verifies fields, coordinates/polarity, sequence and nondecreasing timestamps; subtract the integer epoch before converting back to relative float time. Current helpers use Python integers; this is not a binary GPU ABI or a guarantee that arbitrary epochs fit an eventual int64 field.

`write_events` consumes all candidates, stores the first `capacity` and reports `candidate_events`, `stored_events`, `overflow_events`, `complete`, epoch, units and rounding. Capacity zero is valid and drops every event. Capture overflow is drop-newest; it never feeds back into the pixel reference. The sink bounds stored records, **not** upstream oracle/sample generation memory, which currently holds finite fixture lists.

The caller must retain this metadata beside the CSV (the benchmark keeps it in `summary.json`). A CSV by itself cannot establish completeness: `read_events` is a low-level parser and does not certify an absent overflow report. Do not treat a truncated capture as a full sensor stream. Distinguish optical samples skipped by scheduling, physical pixel/readout suppression, and software capture overflow in future runtime counters. Any future delivered-event filtering requires a separate stage label; these exports are ideal candidate crossings.

## Checks before runtime adoption

Compare event-derived ON/OFF totals and latest times with the existing textures for identical controlled input. Check interval boundaries, asymmetric thresholds, reset, batching, tie order, forced overflow and a large epoch. Assert that loss reporting remains visible and reference state continues after overflow. Verify GPU timestamp precision over the declared supported run duration. Run baseline sensor GPU checks as well as event-level comparisons; the CPU reference tests cannot replace them.
