# End-to-end pipeline prototype report

November 28, 2026. This prototype implements one configurable optical-to-event pipeline for [#7](https://github.com/pianojay/event-vision-lab/issues/7) and its timing, sensor, and rendering dependencies. It does not close any issue or make a component's conventions universal.

## Result

The working path is an analytic optical fixture, an explicitly selected trajectory reconstruction, an ideal or generic sensor, stage-labelled event capture, and event-only replay in Godot. CPU acquisition is offline. The existing interactive GPU laboratory remains available and its sensor/shader implementation is unchanged.

The [run guide](../pipeline-prototype.md) provides launch commands. The [profile reference](pipeline-v1.md) defines supported combinations, configuration defaults, lifecycle, coordinates, time, ordering, resource bounds, and capture semantics. The [evidence report](../evidence/2026-11-28/pipeline-prototype/README.md) contains measurements and complete run artifacts.

## Blockers and independent choices

| Issue | Blocker identified | Prototype direction | Remaining evidence or implementation |
| --- | --- | --- | --- |
| [#1](https://github.com/pianojay/event-vision-lab/issues/1) | Active lighting exists, but useful shape/material interpretation is not demonstrated. | Retain the existing matte-sphere/light laboratory and provide event-count replay and quantified fixture comparisons. | Observability evaluation, reconstruction, and richer material experiments. |
| [#2](https://github.com/pianojay/event-vision-lab/issues/2) | Display output has not undergone flash analysis. | Keep strobe-off baseline behavior and use monochrome windowed counts with pause and scrubbing in replay. | Output-flash analysis and accessibility evaluation. No safety certification is claimed. |
| [#4](https://github.com/pianojay/event-vision-lab/issues/4) | Complete CPU event references were isolated from a reproducible end-to-end run. | Integrate the references, full per-event captures, clock conversion, loss reporting, and a viewer that consumes the emitted capture. | Live GPU event-stream export, scene-aware sampling, and a supported real-time stimulus envelope. |
| [#5](https://github.com/pianojay/event-vision-lab/issues/5) | Generic sensor behavior lacked a composed optical input and output path. Real-camera characterization is unavailable. | Expose ideal and seeded generic held-input profiles with finite response, mismatch, dark offset, refractory gating, and separate suppression counters. | Temporal noise, leak, readout arbitration, pinned-upstream parity, and camera calibration. |
| [#6](https://github.com/pianojay/event-vision-lab/issues/6) | Optical fixtures were not connected to event comparisons. | Connect exact-area and midpoint edge inputs and finite-rise pulses to declared sensor/trajectory modes and continuous optical truth. Retain the independent sphere oracle. | Richer scenes/materials, calibrated optics, and an external converged reference. |
| [#7](https://github.com/pianojay/event-vision-lab/issues/7) | Unselected connection semantics prevented shared integration. | Implement named, versioned prototype profiles. Declare exact, log-linear, and causal held reconstruction separately; reject unsupported combinations instead of silently converting them. | Review broader supported profiles, runtime interfaces, and external dataset adapters before claiming general compatibility. |

No human preference is required to run these profiles. An experiment's chosen configuration is recorded rather than promoted to a universal convention. Missing calibration or physical validation cannot be replaced by an agent decision.

## Contract decisions exercised

- Optical data is positive scene-linear relative intensity. Zero is explicitly unsupported in this pipeline version; no hidden floor is inserted. The retained rendering oracle still supports zero independently.
- Exact optical trajectory, log-endpoint interpolation, and left-held sampling have different meanings. Generic nonideal acquisition currently requires held input.
- A new run creates independent sensor state. An in-run reset finishes the preceding interval, initializes the reference without events, and preserves cumulative pipeline counters and the threshold map.
- Integer epochs stay outside floating-point sensor calculations. CSV timestamps are signed int64 nanoseconds, with explicit rounding and stable sequence ordering.
- Sensor candidates, pixel emissions, refractory suppression, and capture loss have separate records or counters. A complete capture does not imply that sampling observed every optical change.
- Resource failure aborts the run. Capture capacity instead drops newest records with explicit completeness metadata, without resetting acquisition.
- Godot reads pixel-emitted events only. It does not use optical truth to construct the displayed event activity.

## Verification

The retained CPU suites pass 60 tests. The new pipeline passes 15 behavioral tests, for 75 total. Fifteen complete experiment runs record same-input comparisons, including the one-event edge discriminator, unseen pulse, spatial sampling, generic sensor sampling, reset, and capacity cases.

Twelve serialized real-context replay cases pass on Godot 4.7.2, Vulkan Mobile, Intel Iris Plus Graphics. Four valid captures check actual loaded/windowed event counts and include sixteen routed keyboard assertions. Eight malformed capture cases are rejected. The original live GPU sensor checks pass 25/25 both before and after implementation. These are functional results, not a performance comparison.

Review found and corrected pre-allocation capacity checking, HDR pulse endpoint cancellation, reset endpoint arithmetic drift, malformed metadata acceptance, and focused-button Space double-toggle. Regression cases exercise the corrected behavior.

Physical UI testing reproduced the original Space defect. Its final manual retest was interrupted when the user stopped Computer Use with Escape. No further manual UI automation occurred. The fixed keyboard behavior is verified through routed Godot input events, not claimed as a completed second physical-input pass.

Source hashes identify the tested implementation even though generation occurred in a dirty integration checkout before publication. Manifests retain effective configuration, exact source hashes, packed optical samples and their hashes, and stage captures. The [decision log](../../.audit/prototype-decisions.tsv) records decisions, fixes, evidence, and the interrupted manual check.

## Next development boundary

This is a complete offline acquisition-to-visualization prototype. It supplies concrete evidence for reviewing #7 without requiring its complete design to be frozen first. The next distinct implementation would connect a selected profile to live GPU acquisition and compare it against these CPU artifacts. That work must preserve the declared trajectory and sensor semantics and requires its own real-context validation.

All issues remain open. No claim of real-camera calibration, upstream simulator parity, rich-optics fidelity, full live GPU export, or sustained real-time performance follows from this prototype.
