# First milestone compatibility check

November 22, 2026. Local combination of timing `32554b54b0037cb0301be2037c656d3413bddbb0`, sensor `bb0eeb4d7c1fccbedabfa610470cd8b248cb172b`, and rendering `960e844` from shared base `7e90917`. Combined source revision before these probes: `c7cc43fc64db2724db000ad19c3713f9660eb195`. Branch: `codex/fidelity-compatibility-2026-11-22`. No remote branch or daughter checkout was modified by this check.

## Assessment

**Compatible to retain together as independent CPU milestones. Not yet a single interchangeable simulation pipeline or a frozen runtime contract.** All three merged without conflicts; their added files occupy separate track directories. `prototype/` and `run-lab.ps1` are identical to the shared base. The combined tools import together without module-name collisions.

Local verification used Python 3.14.8 on Windows x64, standard library only:

- Timing: 16/16 tests passed; CLI reproduced 1,536 cases / 96 summaries.
- Sensor: 21/21 tests passed; experiment CLI completed successfully.
- Rendering: 18/18 tests passed; validation CLI completed its spatial-error sweep and static fixture checks.
- Coordinator: 5/5 cross-component probes passed, bringing the distinct test count to **60**. The experiment CLIs also rerun some track checks; those reruns are not additional distinct tests.

The [coordinator probes](../../tools/coordination/test_milestone_compatibility.py) exercise actual optical manifest/payload hashes and decoding, top-left row-major coordinates, linear-to-log conversion, both ideal models, static sphere silence, sensor-event conversion to timing CSV with a large integer epoch, refractory-versus-capture loss accounting, a held-input approximation converging toward a log ramp, and explicit treatment of zero intensity. These are CPU adapter probes, not GPU parity.

## Boundaries requiring coordinator decisions

| Boundary | Observed behavior | Required action before runtime wiring |
| --- | --- | --- |
| Signal over an interval | Rendering produces instantaneous linear frames. Timing interpolates log endpoints. Sensor interprets supplied intensity as held over the interval starting at its previous time; ideal jumps emit at that start. | Make the trajectory mode explicit. Do not feed endpoint frames into `advance` and claim equivalent event timing. The probe gets the same edge counts but deliberately different timestamps. |
| Interval endpoint ownership | Timing documents `(previous,current]` for continuous signals. Sensor docstring says a hold over `[previous,current)`, yet its RC solver includes a crossing exactly at `current`. | Clarify optical hold validity separately from event ownership, including jump-at-start and exact-end events. Add a shared boundary test before adoption. This is a concrete sensor documentation/code inconsistency. |
| Reset | Timing rejects non-increasing time even for reset; sensor `reset` accepts a backward time and clears its counters. | Distinguish a new run/stream from an in-run reset; adapt or align behavior explicitly. Do not concatenate a restarted sensor stream into an existing timing capture without a new origin/stream identity. |
| Zero intensity | Rendering permits zero. Timing requires finite log input; sensor requires positive `I+dark_offset`. | Define a consumer policy and record it. A numeric log floor and a physical dark offset are different models; neither should be silently inserted by the renderer. |
| Event stages and capacity | Sensor counts candidate/emitted/refractory-suppressed events and raises atomically on generation-capacity failure. Timing capture drops newest records beyond storage capacity; its `candidate_events` means all records submitted to that sink. | Carry stage-labeled metadata. Sensor candidates, delivered events, capture input records and stored records cannot share one ambiguous counter. Preserve retry/failure versus drop semantics. |
| Numeric precision and ordering | Optical payloads are FP32; CPU state is binary64. Timing CSV rounds to integer ns and retains producer order at ties. Sensor sorts by time/y/x/p. Threshold tolerances also differ. | Specify quantization, bounds and deterministic tie order. Do not claim bit-exact parity near thresholds or treat ns encoding as physical accuracy. |

The exact-end discrepancy was reproduced with the sensor's RC first crossing: `t=-profile.time_constant(exp(0.65))*log1p(-0.2/0.65)`; after initialization at intensity 1, `advance(t,[exp(0.65)])` emits at exactly `t` (0.0005852521645432462 s for 100 Hz). No daughter semantics were changed to conceal the difference.

## Reproduction and retained scope

```powershell
python -B -m unittest discover -s tools/timing -p 'test_*.py' -v
python -B -m unittest discover -s tools/sensor -p 'test_*.py' -v
python -B -m unittest discover -s tools/rendering -p 'test_*.py' -v
python -B tools/coordination/test_milestone_compatibility.py
```

CLI outputs from this check are local ignored artifacts under `docs/evidence/2026-11-22/build/interim-compatibility/`: timing sweep files, `sensor.json`, and `rendering.json`. Prior committed track evidence was preserved. The test source and this report are deliberately retained; no new sustained-performance measurements were made.

No GPU check was rerun: the combined milestone changes only offline CPU tooling/docs, and the runtime/launcher diff against the shared base is empty. Runtime integration still requires the real-context GPU checks and same-input event/count/timing comparisons. Issues #4–#6 remain open. Next step is the coordinator's shared boundary/adapters, with the semantics above settled before any GPU port. This local check does not publish or merge the milestones into the shared integration branch.
