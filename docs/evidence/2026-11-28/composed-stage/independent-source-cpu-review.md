# PR33 independent source and CPU review

Goal: verify PR33 event-stage behavior independently before shipping the composed stack.

Reviewed head: `446417c4007bffe8ddf87157e12778403a42a6e9` against PR32 `faeefebb`.
Immutable run source: `runs/composed-final-source`.

## Completed checks

- Godot official 4.7.2 headless stage checks 69/69, controls 69/69, acquisition 43/43.
- CPU checks 198 passed: acquisition 18, coordination 5, materials 23, pipeline 15, processing 23, reconstruction 16, rendering 18, sensor 37, stage 3, timing 16, validation/engine ownership 24.
- Python 3.14 initially lacked NumPy for validation; that failed import is retained in cpu-validation.log. Repeated validation under runs/reference-env/Scripts/python.exe passed all 24 checks. This is an environment issue, not a failing source test.
- GODOT environment selected the existing official 4.7.2 console engine. No GPU execution, source edits, remote writes, or CUA were performed by this verifier.

## Source findings

No concrete user-facing blocker found in the reviewed diff and owning contracts.

The optical shader preserves detector total intensity in alpha before selecting a truth RGB component. Event inference reads raw event batches and actual dispatched thresholds, independently of ROI/bin/polarity processing. Raw and processed windows have separate bounded state; reconstruction retains one binary64 log estimate per sensor pixel. Stream mode retains no historical optical or diagnostic arrays and no full schedule. It reports capture omission separately from overflow. The anchored two-counter shader uses a local stable log ratio near its anchor; its eight-million counter abort avoids claiming indefinite FP32 integer exactness. FP32 optical phase and legacy display timestamps remain explicit limits.

Reset processing follows completed interval events and preserves optical population. Material reset targets the selected station; the phosphor population clears only for its station. Stage source motion is selected-source controlled, before optical transport, and is independent of camera/point lamp and treatment/control selection. Headless checks establish routing and state behavior only.

## Outstanding proof

This is not a PASS verdict. The root's final 45-run matrix, actual output analysis, paired 600-wall-second plugged-in profiles, and exact final-head guard remain required by the assigned bar. Review those before posting a shipping verdict. Earlier failed matrix versions must remain retained.

Applied principle: Prove It Works. Checks run against the actual archived PR head, and the final verdict waits for composed GPU evidence rather than treating headless checks as rendered validation.
