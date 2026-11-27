# Event Vision Lab documentation

Assessment date: **2026-11-22, Asia/Seoul**.

**Purpose: simulate event vision without a physical event camera, in a practical and physically meaningful setup. A game is an optional medium; a shader or interactive experiment is a sufficient initial artifact.** The user's November 22 clarification supersedes the earlier assumption that a first-person game and an objective were required.

**A Windows Godot prototype now runs on this laptop.** Godot 4.7.2 Mobile/Vulkan drives a shader-rendered room and a persistent FP32 ideal event sensor at 240×180, targeting 120 Hz, with a 60 FPS display cap. The active-lighting extension adds fixed, camera-mounted and orbiting lights, a matte sphere control and per-substep count integration. Twenty-five GPU checks passed; see the prototype guide for current measurements. Strobing is off by default. This validates the small analytic scene, not the eventual real-world fidelity target or learned reconstruction.

The November 28 integration adds a [nine-station interaction stage and bounded live processing](development/interaction-stage.md). Its final integrated experiment gates remain under validation.

Start with **[the Godot prototype guide](godot-prototype.md)**. Launch from the workspace with `./run-lab.ps1`, or double-click `Run Event Vision Lab.cmd`.

**A configurable CPU pipeline is also available as of November 28.** It connects controlled optical fixtures, explicit timing choices, ideal or generic nonideal sensor behavior, stage-labelled event export, and Godot event replay. Start with [the pipeline guide](pipeline-prototype.md). This is a separate offline path; the live GPU sensor is unchanged.

| Material | Purpose |
| --- | --- |
| [Godot prototype](godot-prototype.md) | Launch commands, controls, implementation, fidelity limits, and measured results |
| [Configurable CPU pipeline](pipeline-prototype.md) | Reproducible optical-to-event runs and event-only Godot replay |
| [CPU pipeline v1 profiles](development/pipeline-v1.md) | Implemented input, trajectory, sensor, lifecycle, capture, and display choices |
| [Pipeline prototype report](development/pipeline-prototype-report.md) | Issue blockers, independent implementation choices, verification, and remaining scope |
| [Strobe observability and display research](research/strobe-observability-and-display.md) | Issues #1/#2: code diagnosis, photometric stereo/structured light, display accessibility, and proposed experiments |
| [Sensor simulation fidelity](research/sensor-simulation-fidelity.md) | Current source audit; Event6D, ESIM, v2e and other simulator comparisons; rendering/optics, timing and electronics limits |
| [Fidelity experiment plan](research/fidelity-experiment-plan.md) | Issues #4–#6: proposed local and external-GPU experiments, validation criteria and dependency order |
| [Fidelity development coordination](development/fidelity-coordination.md) | Shared integration root, three component tracks, interface milestone, ownership and GPU validation schedule |
| [Contract retrospective](development/contracts-retrospective-2026-11-22.md) | User's preference for flexible, justified contracts; separates unresolved proposals from decisions |
| [Upstream pipeline contract audit](research/pipeline-contract-audit.md) | Six pinned source pipelines: configuration, signal/time/state/readout/output boundaries and dataset adapters |
| [First milestone compatibility check](development/interim-compatibility-2026-11-22.md) | Local combination: 60 CPU tests, cross-component adapters and unresolved contract boundaries |
| [Concept and requirements](concept-and-requirements.md) | Preserves the user's actual goals and distinguishes them from suggestions in the export |
| [Machine readiness](machine-readiness.md) | Hardware, installed tools, measured CPU results, and limits of the conclusion |
| [Hardware tiers and remote TITAN RTX](hardware-tiers.md) | Provisional whole-machine envelopes, feature barriers, and remote execution options |
| [Solution options and dependencies](solution-options.md) | Candidate implementations, required software, and practical blockers |
| [Validation plan](validation-plan.md) | Sensor correctness, practical scene validity, performance, and later fidelity checks |
| [References](references.md) | Primary technical sources and their roles |
| [Machine inventory](evidence/2026-11-22/machine-inventory.json) | Recorded hardware and software observations |
| [Sensor benchmark results](evidence/2026-11-22/sensor-benchmark.json) | Actual measurements, including scope and workload |

Concept source: [ChatGPT export](../ChatGPT-Event%20Vision%20Game-20261122-0816.md), November 21, supplemented by the user's November 22 clarification in this chat. The original export remains unchanged.

The first implementation is deliberately a shader laboratory: geometry, direct illumination, hard shadows, moving objects, and an emissive surface supply controlled optical changes. Practical fidelity still needs richer and validated scene/sensor models. Windows is the active target. A TITAN RTX host on Ubuntu, accessed later as `ssh vilab204`, is a future option; no connection or changes were made there.

The invoked `openai-docs` skill was consulted. This project is an event-sensor/game feasibility task; it does not currently require an OpenAI API integration. Documentation here follows the project requirements and primary engine/simulator documentation.

Work completed: source analysis, machine assessment, CPU and GPU checks, a portable Godot download, and a working shader prototype. No Python libraries, GPU drivers, system services, or remote-host settings were changed. Earlier assessment documents retain their historical evidence and now point to the current implementation.
