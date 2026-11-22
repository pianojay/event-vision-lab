# Timing track — issue #4

First independent milestone, November 22, 2026. Branch: `codex/fidelity-timing`; implementation base: `7e90917` (coordination root `749c238`). See [coordination](../../development/fidelity-coordination.md) and [issue #4](https://github.com/pianojay/event-vision-lab/issues/4).

## Implemented

An offline **CPU reference and timing sweep**, under [tools/timing](../../../tools/timing/), using Python's standard library:

- Continuous ideal crossing oracle for piecewise-linear and sinusoidal natural-log intensity, including threshold residuals, reversals and independent polarity thresholds.
- Stateful sampled pixel that emits **every** interpolated crossing, separately from the continuous oracle. Its mathematical semantics resemble the ideal prototype; it is not a bit-exact FP32 shader emulator.
- CSV capture/parser with integer nanosecond timestamps, stable sequence numbers, explicit capacity and overflow accounting. Capture does not alter the sensor reference.
- Phase/rate sweeps of fixed sampling, known-boundary sampling, global slope-bound densification and a deliberately limited midpoint-adaptive candidate.
- Event matching by pixel/polarity with missing/extra counts and timestamp errors; separate binary32 clock arithmetic checks.

No runtime shader, shared harness, launcher, integration contract or other track's files changed. No GPU, external simulator or remote machine was used. The [time/event contract](time-event-contract.md) is a proposal for the coordinator, not an already adopted runtime API.

## Run from the repository root

```powershell
python -m unittest discover -s tools/timing -p 'test_*.py' -v
python tools/timing/benchmark.py --output "$env:TEMP\event-lab-timing-reference"
```

Python 3.14.8 on Windows 11 was used for the recorded run; no third-party packages are needed. Commands operate on CPU and need no GPU scheduling slot. The benchmark is a short scalar numerical experiment, not a performance estimate for a full pixel array or Godot. It writes explicit output files; use a new output directory to retain previous evidence.

## Recorded results

[Summary/configuration](evidence/2026-11-22/summary.json), [all 1,536 phase cases](evidence/2026-11-22/phase-sweep.csv), and [representative reference events](evidence/2026-11-22/pulse-reference.csv) are retained. See [measurement details and limitations](results-2026-11-22.md).

**16 unit tests passed.** At a nominal 120 Hz, the 1 ms triangular log pulse was completely missed in **15/16 sampled phases**; midpoint-adaptive refinement missed it in **14/16**. Adding its known slope boundaries recovered all six crossings in all phases. That uses privileged waveform knowledge and does not establish a general adaptive-rendering guarantee.

For the 30 Hz sinusoid, uniform 120 Hz input had no phase with all events matched inside the 0.5 ms gate; uniform 480 Hz passed that criterion for all 16 tested phases. This is an observed fixture result, not a universal supported frequency. Exact threshold touches at extrema can lose events even with small intensity changes between samples.

The binary32 check shows that at elapsed time `262144 s`, rounding `t` and `t+1/120 s` separately to FP32 produces the same value. The shader's current absolute FP32 clock therefore deserves a bounded epoch/relative representation. This checks arithmetic only; it does not measure Godot behavior over a multi-day run.

## Integration handoff and remaining scope

Changed paths are limited to `tools/timing/` and `docs/research/timing/`. Source hashes and the pre-change base SHA are recorded with evidence. Candidate merge unit: the offline reference tools, evidence and contract proposal together. The coordinator can adopt these without runtime changes, then decide the concrete GPU buffer/clock interface.

Next runtime milestones for #4 remain: complete GPU event output with integrity checks against count textures; transition-aware/adaptive scene sampling; spatial moving-edge/shadow fixtures; overload/drop accounting; long-run clock validation; sustained cost and a measured supported stimulus envelope. Integration code must consume the reference against identical signals and run the real-context GPU checks. This CPU milestone does **not** resolve #4.
