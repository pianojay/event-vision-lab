# First rendering milestone: results and handoff

November 22, 2026. Implemented on `codex/fidelity-rendering` from base `7e909179d8a3c5578a2758cd069635cc71655371`. The [JSON report](evidence/2026-11-22-cpu-fixtures.json) records the exact tested source commit and SHA-256 of the Python tools/configurations. The report's subsequent evidence commit is separate from the implementation revision it tests.

## Validation

**18 CPU checks passed.** Coverage includes the closed-form central sphere response, camera orientation, edge area/flux, quadrature error over multiple phases, linear-before-log integration, zero/HDR preservation, static repeatability, invalid inputs, manifest/float32 byte order/hashes, and protection against overwriting previous sequences. The report records Python/OS/CPU identity and execution scope. No graphics context, GPU run, engine performance profile or real-camera comparison was used.

The spatial sweep uses the checked-in [64×48 edge configuration](../../../tools/rendering/fixtures/edge.json), at three explicit sample times. The oracle is an exact float64 box-area integral. Candidate outputs are rounded to the same float32 storage format before comparison.

| Samples per axis | Maximum absolute intensity error | Maximum absolute log-intensity error |
| ---: | ---: | ---: |
| 1 | 0.342000008 | 1.486139702 |
| 2 | 0.116999990 | 0.774727111 |
| 4 | 0.108000003 | 0.403927834 |
| 8 | 0.004500009 | 0.020955296 |
| 16 | 0.004500009 | 0.020955296 |
| 32 | 0.004500009 | 0.020955296 |

These are errors for this fixture and these three phases, not general accuracy guarantees or prescribed production sample counts. The plateau at 8/16/32 reflects the selected phases landing near the same quadrature coverage. The separate phase sweep verifies the analytic midpoint bound `abs(bright-dark)/(2n)` within numerical tolerance. Higher sample counts need not improve every individual phase strictly. The edge is invariant in y, so its second dimension is integrated analytically; sphere quadrature actually evaluates `n²` rays per pixel.

The static 64×48 sphere, fixed camera and fixed light produce identical exported bytes at the three times. This confirms deterministic fixture behavior; it is not a test of renderer stochastic noise or sensor background activity. The report includes diagnostic CPU wall times for the small workloads, including Python/serialization overhead. They are not sustained rendering throughput measurements and should not be compared with the game's GPU timing numbers.

The generation CLI was also exercised for center/exact edge output and a 4×4-sampled sphere. Large generated frame files are left in the ignored output directory, not committed as evidence.

## Interesting observation

A separate edge case moves its projected boundary from `x=1.1` to `x=1.4` over 10 ms. The pixel center at `x=1.5` sees intensity `1.0` at both times. Exact pixel-box integration instead gives `0.91 -> 0.64`, a log change of approximately `-0.351976423`.

This is a spatial point-sampling loss before electronic sensing. Sampling that same center ray at additional times within this displacement still sees no change. It complements the timing track's unseen-pulse problem: **temporal correctness alone cannot compensate for unresolved pixel-area coverage**. Conversely, a box footprint is only an explicit idealization; the finding does not identify a real camera's optical transfer function.

The area average of linear intensities must occur before the sensor logarithm. For a half-covered pixel with levels 0.1 and 1.0, the optical result is `I=0.55`, so `ln(I)≈-0.598`. Averaging the two log values gives approximately `-1.151`, a different signal. Post-event filtering is a third operation and is not a substitute for either.

## Integration handoff

Changed files are confined to `tools/rendering/` and `docs/research/rendering/`. Shared runtime, shaders, launcher, test harness, main documentation index and coordinator documents were not edited.

The first tools and local artifact contract are usable independently. A consuming track can select point/area input, read float32 scalar intensity and then apply its own documented dark floor/logarithm/pixel model. Use the manifest's explicit times and parameters instead of assuming display cadence or inferring physical units. The runtime ABI remains pending; this milestone does not require other agents to adopt the local schema unchanged.

Coordinator's next integration decision: provide an intensity-input path and assign an optical sampling policy that keeps the existing center-ray analytic control available. Do not duplicate unrelated rendering/sensor changes inside the current monolithic shader independently. CPU-to-GPU parity for this fixture and GPU pixel-area sampling remain unimplemented and need a coordinated real-context validation slot.

Further #6 work remains: material/roughness controls, calibrated distortion/PSF and spectral response, indirect/transmitted light, a converged external renderer reference, and numerical comparisons through the shared sensor/event diagnostics. Real-device fidelity and external GPU compatibility are not established. Keep #6 open.
