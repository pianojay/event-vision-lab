# Fidelity experiment plan

**Proposed November 22, 2026.** No experiments below have been implemented or run by this research. The [comparison brief](sensor-simulation-fidelity.md) records the current code and primary sources. This plan translates that review into bounded work, without requiring a physical camera or an external GPU to start.

## Ownership and order

| Issue | Outcome | Dependency |
| --- | --- | --- |
| [#4: Temporal accuracy and event reference](https://github.com/pianojay/event-vision-lab/issues/4) | Measurable event count/timing error and a supported stimulus envelope | First diagnostic milestone |
| [#5: Sensor behavior](https://github.com/pianojay/event-vision-lab/issues/5) | Independent, reproducible nonideal effects; later calibrated profiles | Use #4 export for event-level comparisons; pixel tests can start independently |
| [#6: Rendering and optics](https://github.com/pianojay/event-vision-lab/issues/6) | Known optical phenomena compared with analytic/offline references | Define the signal boundary first; reuse #4 and the same sensor for comparisons |

[#1](https://github.com/pianojay/event-vision-lab/issues/1) retains the active-lighting/material observability question and user evaluation. [#2](https://github.com/pianojay/event-vision-lab/issues/2) retains display accessibility. These three new issues supply deeper measurement work; they do not close the existing feedback issues. A document being written is distinct from an experiment passing.

Recommended order: signal contract and diagnostic export -> timing envelope -> generic sensor effects -> selected optical/material controls -> offline richer references -> real-device calibration if evidence becomes available. Source changes should remain incremental on `main`; an environment-specific implementation may justify a development fork later.

## Define the measurement boundary

Keep the current ideal path as an explicit control and introduce replaceable conceptual stages. They can initially remain in the same compute shader; architectural separation does not require CPU readback at every step.

```text
sample_scene(t, camera, lighting) -> scene-linear radiance
apply_optics(...)                -> pixel irradiance proxy
advance_pixel(dt, profile)       -> candidate crossings
apply_readout(...)               -> delivered event stream
process_and_display(...)         -> optional view
```

Every run should record: code/engine/model versions; input encoding and units; resolution/intrinsics; trajectories/light waveforms; timestep/adaptation policy; sensor parameters/seed; readout/filter settings; time origin/units/precision; GPU/driver/CPU; render sample/denoiser settings; dropped samples/events; and elapsed simulated and wall time. Until radiometry is calibrated, label input as relative units rather than lux or photocurrent. Record any conversion to an external simulator's expected scale/log convention.

Maintain independent switches for deterministic ideal pixels, generic nonideal pixels, optical effects, readout limits and post-event processing. Do not silently change the optical signal to make the display easier to read.

## Experiment A — temporal accuracy and export (#4)

First make a bounded diagnostic output of **all** `(x,y,t,p)` crossings, not just the current count/latest-time images. An offline CPU oracle is acceptable initially. Define polarity, integer or relative time representation, interval boundaries, stable tie ordering, reset behavior and overflow reporting. Test reconstruction of ON/OFF totals from the stream against GPU diagnostic counts. Do not claim that event export alone fixes sampling.

| Fixture | Sweep | Required evidence |
| --- | --- | --- |
| `L(t)=L0+a*t` and reversals | Rate, threshold, phase, ON/OFF asymmetry | Oracle crossing counts/times and residual error |
| Finite-rise pulses and sinusoidal light | Frequency, duty, rise time and phase relative to sampler | Missed pulses, count error, timing bias and convergence |
| Moving softened edge | Speed, pixel position, contrast, spatial footprint | Event error against a dense/analytic signal; no invented outline events |
| Stationary scene with varying light/shadow | Source motion and sharp switching | Detect changes with zero camera/object flow; motion-only adaptation must not pass by ignoring light |
| Overload and long session | Forced stalls, burst size, clock duration, batching | Explicit skipped input/event loss, stable reset, clock error and reproducibility |

Compare the existing fixed 120 Hz sampler with known-transition-aware sampling and a candidate adaptive method. For a step, specify pre/post transition values and physical rise time or an ideal-jump convention; merely evaluating at the switch and interpolating over the old interval can still smear timing. Repeatedly halve the reference timestep until event counts/times converge within a declared tolerance. Discontinuous trajectories need explicit transition handling.

Report matched-event timestamp median/p95/max error, unmatched ON/OFF counts, missed-pulse fraction, and sample/runtime cost. Use identical locations/polarities and an explicitly documented matching tolerance; do not hide missing events by considering only matched timestamps. Declare a supported range after the sweep, rather than selecting a universal “sufficient FPS” beforehand. The ideal analytic ramps should match within justified numeric tolerance. Boundaries that fail remain documented failures.

If a real-time fidelity target exceeds budget, choose a visible policy: slow simulation, narrow the supported stimulus range, or report degraded acquisition. A capped catch-up loop must not look like a camera-specific bandwidth limit.

## Experiment B — generic sensor behavior (#5)

Use identical recorded/analytic input for our model and a **pinned reference with explicit settings**, bypassing renderer differences. Start with v2e-inspired components; use ICNS or DVS-Voltmeter as separate comparisons where their mechanisms answer the question. Agreement with a simulator is model agreement; camera fidelity needs real measurements.

| Mechanism | Proposed test | Evidence needed |
| --- | --- | --- |
| Persistent threshold mismatch | Repeat log ramps with seeded per-pixel ON/OFF maps | Threshold distribution, repeatability, asymmetry, difference from resampling thresholds every step |
| Photoreceptor bandwidth | Step/sinusoid at several absolute intensities with equal fractional contrast | Measured lag, event timing/count and frequency response; timestep convergence |
| Refractory/reset | Strong ramps and paired flashes with varied spacing | Minimum inter-event interval and documented reference/reset behavior during dead time |
| Leakage | Constant input across several durations/intensities | Per-pixel background ON rate and rate distribution, independent of display batching |
| Temporal/shot-related noise | Constant and weak modulated input, repeated seeds | ON/OFF balance, rate versus intensity, interval statistics and uncertainty |
| Readout limitation | Spatially broad synchronous stimulus | Queue/latency/ordering/loss versus demand, separated from pixel dead time and software event-buffer overflow |

Add mechanisms one at a time and then in combination. Persistent mismatch is a sensor instance property; temporal noise evolves during acquisition. Prefer a seedable time-based process so changing presentation batching does not change the simulated device. Do not add both an independent random-event model and a photoreceptor-noise model for the same effect without checking for double counting.

An 8.33 ms input step does not resolve arbitrary sub-millisecond response dynamics. Add enough internal temporal resolution, an appropriate solver or a narrower supported bandwidth. Low-pass filtering sampled endpoints cannot restore an unseen optical pulse. Optical sampling and numerical integration convergence need separate tests.

Call this first version **generic nonideal**, with documented units and assumptions. A later named-device profile must record device generation, lens, bias configuration, light conditions, temperature where relevant, calibration procedure and held-out data. Real Event6D sequences can assess downstream transfer; their event statistics alone do not identify every sensor parameter when incident irradiance is unknown.

## Experiment C — rendering, optics and materials (#6)

Retain the matte sphere's analytic direct-light solution as a control. Add a small material/lighting fixture at a time: diffuse plane/sphere, rough versus smooth specular patch, occluder/shadow, indirect-lit patch, then a transparent/refractive object. Keep camera/light trajectories, intensity scale and sensor settings fixed across comparisons. Separate geometric changes from material and illumination changes.

Begin local optics experiments with pixel-footprint integration/blur and configurable distortion; later study vignetting and spectral sensitivity if the research question needs them. Apply optics before thresholding. Warping an event image afterward is processing and is generally not equivalent near edges, where interpolation and nonlinear thresholding do not commute.

Use BlenderProc or another controlled offline renderer for a short reference sequence. Render linear HDR values, ground-truth depth/normals and sufficient spatial/temporal samples; archive settings and asset versions. Compare radiance error, log-change error and resulting event counts/times under the **same sensor**. Repeated static renders expose false activity from estimator noise; a converged reference must improve when sample count increases. Denoiser/temporal-cache changes need separate ablations.

For an absorbing surface, compare equal fractional modulation at several absolute intensities in ideal and nonideal modes. For glass, test reflected and transmitted backgrounds separately. These measurements inform #1; they do not establish that people can infer shape directly from the visualization. That requires its own user evaluation or an estimator with geometric error metrics.

## Hardware and execution tiers

| Tier | Proposed work | What must be measured |
| --- | --- | --- |
| Iris Plus / current Windows setup | 240×180 short fixtures, diagnostic export, simple optics and generic sensor components | Full-loop cost with each added mechanism, substeps, buffer peaks and skipped work |
| Offline local CPU or external GPU | Dense reference signals; short high-quality optical sequences; same-input simulator comparisons | Wall time per simulated second, storage, convergence and dependency versions |
| TITAN RTX candidate | Richer rendering/reference generation and optional learned interpolation/inference | Actual Turing-compatible runtime, graphics access, GPU sharing, VRAM and sustained cost; no current compatibility claim |

Do not equate “offline 1 kHz simulated input” with “renders 1,000 frames per wall second.” Start with a tiny clip instead of downloading full training datasets. Keep data generation beside sensor processing; replay lossless results locally. For raw `(x,y,t,p)` output, record chosen bytes/event and burst peaks separately from average throughput.

No remote host work is part of this research. The first external test, if later requested, should inspect the host and produce one reproducible fixture. Full interactive streaming and training are separate workload decisions.

## Completion evidence

For each issue retain configuration, raw numeric results, reference provenance, plots or small inspection views, supported range and known failures. A useful comparison must show **both fidelity and cost**. Run the existing GPU checks whenever sensor/runtime code changes; new nonideal tests should be statistical or analytical checks of the intended behavior, not assertions that simply mirror implementation. Only close an issue when its stated criteria are met.
