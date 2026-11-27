# Slow anchor-return timing investigation

Goal: resolve the observed timing failures without changing the 100,000 ns gate, discarding events, or replacing the failed moving-camera experiment with a different stimulus.

## Actual failure

The archived `runs/stage-matrix-v1` captures identify source `87c568ce73fd4a7afcef065dbd32979b39d657a7`. Four refraction cases have exact count/polarity agreement but fail timestamps against the independent binary64 solver consuming archived FP32 intensities and thresholds.

| Case | Events | Timestamps outside 100 us | Maximum error ns |
| --- | ---: | ---: | ---: |
| Control | 134022 | 1 | 123456 |
| Spatial | 545398 | 30 | 50000001 |
| Temporal | 140277 | 20 | 16666666 |
| Treatment | 137540 | 20 | 16666667 |

The static control has no events. `analyze.py` reproduces the comparisons and saves every affected pixel's complete optical/count trace in `traces.json`. These are full-frame comparisons; no central-region selection enters the sensor parity test.

## First wrong decision

`current_relative = log32(I) - log32(anchor)` loses the small contrast when two nearby intensities have the same rounded absolute logarithm. This changes both the interpolation fraction and, at an equality boundary, the interval that owns an event. It is neither a CSV pairing artifact nor threshold-product cancellation in the representative cases.

Treatment pixel (41,16), frame 11, has crossing level zero. Its binary64 relative endpoint logs are `2.962682201790301e-7` and `-1.4813424180637469e-6`. GPU diagnostics hold `2.384185791015625e-7` and `-1.430511474609375e-6`. The correct timestamp is 169444446 ns; the archived GPU event is 169047622 ns, an error of 396824 ns.

Treatment pixel (42,23) starts at intensity `0.1042657122015953`. At frame 17, intensity `0.10426570475101471` is one FP32 ULP below that anchor. The correct relative log is `-7.145763181171105e-8`, but its rounded absolute GPU log equals the anchor log. GPU emits the return event at 283333339 ns. The actual sampled intensity reaches the anchor only at frame 18, 300000006 ns. The original GPU event is one entire sample interval early.

## Fix and validation

Commit `f80a4df` stores anchor intensity and previous intensity in previously unused lanes of the existing private state vectors. It evaluates near-anchor relative logs directly with `z=(I-A)/(I+A)` and `2*z*(1+z^2/3+z^4/5)`. For `abs(I-A)<=0.01*A`, the exact-arithmetic omitted-series bound is below 2.4e-17. Outside that neighborhood it retains the existing absolute-log difference. Threshold edits reanchor at the previous intensity; resets initialize the current intensity. Public diagnostics, the independent oracle, event expansion, and gates are unchanged.

CPU FP32 emulation retained all 914 events on the 71 affected pixel/case pairs. Count/polarity mismatches are zero, maximum timestamp error is 6 ns, and all 71 formerly failing timestamps differ by at most 1 ns. This is selected-pixel arithmetic evidence, not a whole-camera GPU pass. See `candidate.py`, `candidate-selected-pixel-check.json`, and `stable-relative-candidate.json`.

On exact commit `f80a4df`, actual Godot 4.7.2 Windows/Vulkan Mobile on Intel Iris Plus passed all 24 acquisition GPU checks, including the new archived-pixel regressions, threshold changes and reset semantics, plus all 25 baseline checks. Reports and launch provenance are in `gpu-acquisition/` and `gpu-baseline/`. The new GPU timestamp for (41,16)'s sequence is 169444445 ns versus the independent 169444446 ns. The one-ULP-below-anchor sample emits nothing; the true anchor sample emits at 300000006 ns. The 18 Python reference tests and GDScript parse check passed.

The independent root must regenerate all four old moving-camera cases and validate full-frame parity at the final composed head. The arithmetic fix does not promise a universal timing bound for arbitrary low-slope crossings at nonzero threshold offsets.

## Separate physical-source correction

Commit `24512e1` makes stripe motion affect only the selected station's finite rear emitter. The neighboring emitter stays at zero offset. Both treatment and control use the same physical source. This corrects the simultaneous two-source stimulus found by the root's version-2 task-localization matrix. It does not mask sensor pixels or filter events. Version-2 failed captures remain evidence. Its full stage validation belongs to the root's version-3 matrix.

After merging process/layout fixes `f86763a`, the assigned worktree is clean at `53dcfdce8f48f3a1f1fecab9e20907efcecfdfff`. GPU ownership was released to the root. No final-camera or stage-matrix pass is claimed here.

Fix Root Causes selected an intensity-domain contrast calculation after tracing the first incorrect equality decision. Explain the Number kept the archived full-frame failures separate from selected-pixel emulation and real GPU regression results.

Throughput checkpoint: n/a, numerical correctness investigation.
