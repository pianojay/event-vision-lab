# Sensor track — CPU reference milestone

November 22, 2026. Branch: `codex/fidelity-sensor`. Base: `7e90917` (shared Godot launcher setup, after coordination root `749c238`). Public progress belongs to [issue #5](https://github.com/pianojay/event-vision-lab/issues/5); sensor-local documentation and deliberate evidence live here.

**Implemented:** an isolated, Python-standard-library CPU pixel reference with an ideal mode, persistent seeded ON/OFF threshold mismatch, a generic intensity-dependent first-order response, an optional additive dark offset, and explicit refractory event gating. **21 analytical/statistical tests passed.** This is a small-fixture oracle, not a Godot feature, upstream simulator reproduction, calibrated camera or real-time implementation.

The [coordination document](../../development/fidelity-coordination.md) still reserves shared runtime interfaces for the coordinator. No common shader, runtime, launcher or test harness was edited. This milestone gives the other tracks concrete sensor semantics and comparison fixtures without imposing a shared buffer/API layout.

## Files and reproduction

- [Reference model](../../../tools/sensor/reference_sensor.py)
- [Analytical and statistical checks](../../../tools/sensor/test_reference_sensor.py)
- [Experiment/report runner](../../../tools/sensor/run_experiments.py)
- [Recorded CPU-only evidence](evidence/cpu-reference-v1.json)

From the repository root, with Python 3.10+ and no additional packages:

```powershell
python -B -m unittest discover -s tools/sensor -p 'test_*.py' -v
python -B tools/sensor/run_experiments.py --report docs/research/sensor/evidence/cpu-reference-v1.json
```

The second command reruns the checks and replaces the specified report. Omit `--report` to print JSON instead. The recorded run used Python 3.14.8 on Windows x64. The report records platform and canonical LF/UTF-8 SHA-256 source digests; it is deliberate fixture evidence, not a live runtime log. No GPU was used or reserved, and no Godot regressions were rerun because the runtime is unchanged.

## Model v1 contract

This is a **local diagnostic contract**, pending adaptation to the coordinator/timing contract.

`ReferenceSensor(width, height, profile)` creates a fixed sensor instance. Inputs are row-major, nonnegative linear optical intensity in relative units; they are not display RGB, lux or calibrated photocurrent. `I + dark_offset` must be finite and positive. Zero optical intensity is supported only with a positive offset. No silent epsilon floor or upper intensity saturation is applied.

`reset(t0, I0)` initializes the filtered value and contrast reference from `ln(I0 + dark_offset)`, clears counters and refractory history, and emits nothing. It retains the same pixel threshold maps. Constructing another instance with the same integer seed (including zero) reproduces those maps within the recorded Python implementation. Positive/negative thresholds are independent Gaussian draws, clamped to an explicit minimum; at large sigma this is a **clipped distribution with an atom at the floor**, not a Gaussian with unchanged moments. Map order is row-major, ON then OFF per pixel.

`advance(t1, Iheld)` declares that the given intensity is held over the interval starting at the previous time. It can jump at that interval's start. This is **not** an API for interpolating frame endpoints. The caller must describe optical changes explicitly; unseen flashes are never recovered. Time is float64 seconds, must increase, and remains independent of wall/display time.

With filtering disabled, every crossing caused by a jump has the interval-start timestamp. With filtering enabled, for constant effective input:

```text
L = ln(Iheld + dark_offset)
g = b_min + (1-b_min) * min((Iheld + dark_offset)/I_white, 1)
tau = 1 / (2*pi*f_white*g)
z(t0+s) = L + (z(t0)-L)*exp(-s/tau)
```

The reference advances by `+C_on` or `-C_off` for each crossing of filtered log value `z`. Crossing times are solved from that continuous RC response, not spread uniformly over a frame. A level equal to the asymptote is not reached in finite time. The bandwidth law and dark offset are generic, explicit choices in relative units; they are not measurements of any sensor. Zero `f_white` disables filtering. Splitting the same hold into smaller intervals should preserve the solution, subject to roundoff. Varying optical input is a different convergence problem and remains a timing-track responsibility.

Refractory behavior is an **event-gating approximation**: all candidate crossings advance the contrast reference, even when suppressed; only emissions update the last-emitted time. Both polarities share the dead time. A suppressed candidate is not queued for later emission, and there is no readout arbiter. A physical pixel's blind/reset behavior may require different state evolution; use this implementation only with its stated semantics.

`StepResult.candidates` contains `(x,y,t_s,p,emitted)` records, with `p` in `{-1,+1}`; `events` selects pixel emissions, not events delivered through simulated camera readout. Counters separately retain candidates, emissions and refractory suppression. Candidates are sorted within a call by `(t_s,y,x,p)`, with stable order for equal keys. Events at an exact continuous interval endpoint are returned by that call; a new optical jump at the same time may produce additional events in the next call. A combined stream needs an explicit boundary/tie convention from the timing track; this is not the shared event export format.

Candidate capacity is a resource guard, not sensor saturation: overflow raises an error and leaves the entire step's state, counters and time unchanged. Invalid inputs also fail before committing state. Threshold comparisons allow eight ULPs for arithmetic roundoff; this is not a physical threshold-noise mechanism. Long-duration float timestamp precision has not been validated.

## Evidence from the recorded fixture run

| Fixture | Result | Interpretation |
| --- | --- | --- |
| Ideal `delta log I=0.7`, C=0.2 | 3 simultaneous ON events at the declared jump | Ideal control, retained residual |
| Same step with 100 Hz white bandwidth, initial I=1 | First event at 0.535512 ms | Finite-response delay in the chosen model |
| Same fractional step, initial I=0.01 | First event at 4.533484 ms | Absolute intensity affects response even when ideal log contrast agrees |
| C=0.1, 100 Hz, 2 ms refractory | 6 candidates, 2 emissions, 4 suppressed | Explicit gating changes observations without inventing readout loss |
| Weak optical step with dark offset 0.1 | No events | Additive offset changes the effective fractional contrast |
| One hold versus 200 subdivisions | Same six candidates/polarities/gates; max timestamp difference about 8.7e-19 s | Numerical partition consistency for constant input, not arbitrary optical fidelity |
| 8,192-pixel mismatch map, seed 17, nominal C=0.2 and sigma=0.03 | ON mean 0.199735, stddev 0.030231; OFF mean 0.200419, stddev 0.029755 | Seeded-instance statistics; full ranges/floor counts in JSON |

Checks also cover both-polarity RC equations, threshold asymmetry, reset/replay, persistent maps, ideal scale invariance, ordering, capacity failure and invalid input. These values validate the selected mathematical model, not real camera behavior. No throughput or GPU cost claim follows from these CPU fixtures.

## Research basis and next integration milestone

The [v2e paper, sections 3–4](https://arxiv.org/html/2006.07722v2) motivates persistent mismatch, finite intensity-dependent response and low-light effects. Its [pinned implementation](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/emulator.py) is a future same-input comparison target. This code is independently implemented: the held-input closed-form solver, input scaling and chosen refractory semantics must not be described as v2e parity. No upstream package/checkpoint was installed or executed.

For coordinator handoff: expose a sensor-input boundary, explicit initialization/profile state and candidate-versus-emitted diagnostics. Adapt this oracle to that boundary before any GPU port. Preserve ideal defaults and compare new GPU state/count/timing against these small fixtures using a real graphics context, one GPU run at a time.

Remaining #5 work: leak/temporal noise with time-based seeds and statistical tests, realistic reset/blind behavior if required, readout queues/loss, same-input comparison with a pinned external simulator, measured implementation cost and eventual camera-specific calibration. Rendering/optics and unknown optical transitions remain separate. **Issue #5 stays open.**
