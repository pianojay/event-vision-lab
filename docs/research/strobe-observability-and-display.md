# Strobe observability and display research

November 22, 2026. Addresses [issue #1](https://github.com/pianojay/event-vision-lab/issues/1), its material/light-source comment, and [issue #2](https://github.com/pianojay/event-vision-lab/issues/2). Research and implementation diagnosis only: no runtime behavior was changed, no flashing demonstration was launched, and neither issue is resolved by this note.

## Assessment

The user expects active illumination to expose geometry and material differences. The present whole-view flashing is not adequate evidence for evaluating that idea. We need to examine the measurement and its visualization independently before increasing rendering complexity or changing hardware.

The strongest first experiment is a stationary matte sphere under a moving or switched-direction light, with numerical event-count maps and known normals. A uniform strobe is a useful control, but is not by itself equivalent to structured-light triangulation or photometric stereo.

## What the implementation actually does

- `prototype/shaders/sensor.glsl` already includes a Lambertian cosine term, distance attenuation, hard shadows, a simple specular term and a 25%-duty square-wave lamp. The source is fixed at `(1.6, 3.0, 1.2)`; it is not camera-mounted or movable.
- The ideal sensor computes multiple ON/OFF threshold crossings, but retains only counts for the latest sensor sample and each polarity's latest crossing time.
- `prototype/shaders/display.gdshader` samples those counts but never uses the red/green count channels in its displayed value. Time-surface brightness is based on the most recent ON/OFF times. The raw-window view is also binary presence per polarity, not a count image.
- Consequently, pixels with different burst counts can appear almost identical when their latest events occurred within the same recent time interval. Both polarity histories can coexist and their colors add.
- Reading only the final substep's count image would not fix this: counts must be accumulated across all sensor substeps belonging to the visualization window.
- The default enables strobing, and its slider spans 0.5–30 Hz. The current display can turn scene-wide event bursts into broad bright/dark changes. No flash-threshold evaluation has been performed.

These are source-code observations. Their contribution to the reported perceptual problem needs the proposed quantitative experiments below; source inspection alone does not establish that all useful geometry information survives sensing.

## Why darker material is not automatically fewer events

For a simplified diffuse patch under the current style of lighting, write

`I_off = rho * A`, `I_on = rho * (A + S)`,

where `rho > 0` is diffuse albedo, `A` is ambient contribution, and `S` contains source strength, visibility, normal/light cosine and distance factors. Then

`delta log I = log(I_on / I_off) = log((A + S) / A)`.

Albedo cancels when it scales both terms equally. Surface orientation can still influence `S`. A uniform *multiplicative* gain applied to the entire image is an even stronger control: its log change is spatially constant. Thus ordinary RGB shading intuition does not transfer directly to event output.

Illustration with `A=0.035`, contrast threshold `C=0.2`, and a reset reference before the jump:

| Direct contribution S | Ideal ON crossing count |
| ---: | ---: |
| 0.05 | 4 |
| 0.25 | 10 |
| 0.80 | 15 |

These are analytic examples, not measured scene values. A latest-event display can render all three at nearly the same brightness despite their different counts.

The cancellation assumes nonzero intensity and a pure diffuse scaling model. Real dark surfaces can encounter noise floors and reduced temporal response; specular terms, distinct ambient lighting, additive sensor offsets and shadows change the situation. Do not impose a heuristic that black material must emit few events. The existing logarithm clamp is a numerical guard, not a calibrated low-light camera model.

## Relevant research

| Primary source | Finding relevant here | How to use it |
| --- | --- | --- |
| [EventPS, CVPR 2024](https://ieeexplore.ieee.org/abstract/document/10655016) | Event-based photometric stereo estimates normals from radiance changes under varying illumination | Closest starting point for the surface-orientation hypothesis; abstract inspected, full paper not retrieved in this pass |
| [EventPSR, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/papers/Yu_EventPSR_Surface_Normal_and_Reflectance_Estimation_from_Photometric_Stereo_Using_CVPR_2025_paper.pdf) | Designed illumination scanning supports joint normal/reflectance estimation; the method considers diffuse sensitivity and specular coverage | Guide a later diffuse-to-specular material experiment; this is evidence for a designed capture-and-inference pipeline, not for direct shape visibility from any blinking lamp |
| [ESL, 3DV 2021](https://rpg.ifi.uzh.ch/docs/3DV21_Muglikar_ESL.pdf) | A scanning projector and event camera establish spatiotemporal correspondence for depth estimation | Distinguish spatially coded/scanned light and camera-projector geometry from global flashing |
| [v2e, CVPRW 2021](https://arxiv.org/abs/2006.07722v2) | Models threshold mismatch and intensity-dependent bandwidth/noise | Reference for a later calibrated sensor mode and low-light comparisons |
| [W3C flash guidance](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html) | Both general luminance flashes and saturated-red transitions matter; rate, amplitude and affected area enter the criteria | Use as an engineering reference for display analysis. It is not a safety certification for this native app |

The papers support active illumination as a real event-vision research direction. They do not establish that the current scene or sensor reproduces their acquisition conditions. Transparency/refraction remain a separate renderer and validation task; changing albedo or specular strength is not a substitute.

## Suggested sequence

| Stage | Experiment/change | Evidence to collect |
| --- | --- | --- |
| 1. Display controls (#2) | Default strobe off; restrained monochrome option; stable count/rate view with explicit temporal integration and bounded display gain; pause/static inspection | Recorded display luminance transitions and affected area, rather than subjective color comfort alone |
| 2. Preserve the signal (#1) | Accumulate ON/OFF counts over a defined window covering every substep; retain numerical output independently of display mapping | Compare input log changes, crossing counts and display values at selected pixels |
| 3. Diffuse control (#1) | Matte sphere/tilted patches; sweep uniform lamp strength, then change light direction independently of camera | Compare event measurements with analytic predictions and ground-truth normals; separate albedo and orientation sweeps |
| 4. Active illumination (#1) | Compare fixed strobe, camera-mounted light and independently movable light; later add a swept stripe/projector with a defined baseline | Determine which changes improve observability; separate direct human interpretation from estimated normals/depth |
| 5. Fidelity extensions (#1) | Controlled roughness/specularity, calibrated sensor bandwidth/noise, and later transparent/refractive scenes | Compare against a reference simulator or recorded real sensor data before calling the behavior physically validated |

For an inference experiment, surface-normal angular error is a relevant endpoint. Before inference exists, use event counts, polarity, crossing times, phase dependence and spatial variation—not a normal-reconstruction accuracy claim.

The square-wave strobe deserves event-aware sampling at known transition times, or an explicit finite rise/fall-time model. Current endpoint interpolation spreads inferred crossings across the sampling interval; it cannot recover an unseen pulse and should not be treated as physically accurate jump timing. Establish slow, resolved controls before attempting faster stimuli. This work is feasible to start on the laptop; no TITAN requirement follows from these hypotheses.

## Display accessibility and sensor fidelity

A high-rate simulated light does not require reproducing its flashes on the monitor. We can retain the same generated events while offering a slower, aggregated visualization. If common-mode suppression or other event filtering is offered, label it as processing and retain access to the unfiltered measurements.

Monochrome or reduced saturation alone does not remove general luminance flashing. W3C SC 2.3.1 addresses more than three flashes in a one-second interval unless below defined thresholds, including area and luminance/red-transition conditions. Use this as a reference rather than declaring any palette or frequency universally safe. Evaluate the actual rendered output, including worst-case size and aliasing. Do not use user exposure as the first test method.

Static inspection and offline numerical diagnostics should precede another strobe demonstration. The raw flashing view should be optional. Temporal integration changes the visualization and its time resolution; document that transformation rather than silently altering the sensor to produce a pleasing image.

## Status

Recommendations remain unimplemented. The existing 16 tests establish limited sensor semantics, not surface-information usefulness, material realism or display accessibility. Keep #1 and #2 open while separate acquisition and display criteria are defined and tested.
