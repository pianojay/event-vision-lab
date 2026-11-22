# Fidelity component coordination

Established November 22, 2026. This document records the shared development root and coordination rules for issues [#4](https://github.com/pianojay/event-vision-lab/issues/4), [#5](https://github.com/pianojay/event-vision-lab/issues/5) and [#6](https://github.com/pianojay/event-vision-lab/issues/6). The [research](../research/sensor-simulation-fidelity.md) and [experiment plan](../research/fidelity-experiment-plan.md) define their technical scope.

## Root and status

- Shared integration branch: `codex/fidelity-integration`.
- Starting baseline: `24c6a4766b69762bade47de63d3e72834a02e48b` on `main` (research plus the existing analytic prototype).
- This coordination commit establishes the development root. Use its exact commit SHA when creating component worktrees; record the SHA in each handoff. A moving branch name alone is not a reproducible starting point.
- Component worktrees now exist on `codex/fidelity-timing`, `codex/fidelity-sensor` and `codex/fidelity-rendering`. Runtime interfaces have not yet been extracted or implemented. The rules below describe the intended boundary, not an existing API.

Keep this checkout for coordination and integration. Give each component its own worktree and branch when starting it. The integration branch collects compatible milestones; validated integration can subsequently be merged into `main`. Ordinary unrelated incremental development continues to follow the repository's normal `main` workflow. No mandatory PR policy is introduced.

All worktrees can use the shared Godot 4.7.2 directory `C:\Godot_v4.7.2-stable_win64.exe\` through `run-lab.ps1`; no checkout-local engine copy is required. Use `-EvidenceDirectory` with a distinct track output path for validation/profiling. See [launcher setup](../godot-prototype.md#run-on-windows) for overrides and version checks.

## Work allocation

| Track | Planned branch | Owns | First independent deliverable |
| --- | --- | --- | --- |
| Timing / #4 | `codex/fidelity-timing` | Sampling policy, clock/event format, diagnostic export and temporal comparisons | Analytic signal oracle and event count/time checks |
| Sensor / #5 | `codex/fidelity-sensor` | Pixel state, thresholds, finite response, refractory/noise and later readout models | Seeded generic nonideal model against controlled input, with ideal mode retained |
| Rendering / #6 | `codex/fidelity-rendering` | Scene radiance, optics, material/lighting fixtures and offline reference configuration | Small deterministic optical fixture with documented input conventions |
| Coordinator | `codex/fidelity-integration` | Shared interfaces, runtime wiring, common docs, integration and GPU validation schedule | A minimal shared code boundary before competing edits to runtime files |

Ownership denotes responsibility, not permission to edit another checkout. Component agents commit only in their own worktrees. Shared-file changes should be proposed to the coordinator, who implements/integrates them once. In particular, `prototype/main.gd`, `prototype/sensor_gpu.gd`, `prototype/shaders/sensor.glsl`, the launcher, and the common test harness currently span responsibilities. Do not let all three tracks independently refactor them.

## Initial interface decisions

The [November 22 retrospective](contracts-retrospective-2026-11-22.md) clarifies the user's direction: contracts should support independently configurable behavior with explicit reasons, rather than canonizing one daughter's proposal or dataset format. The [upstream source audit](../research/pipeline-contract-audit.md) supplies precedents and caveats. The boundary requirements below remain to be designed; no universal runtime configuration or serialization has been selected.

Before concurrent runtime edits, land one small shared-interface commit here and bring it into all component branches. Record concrete file paths and callable/buffer layouts in this document at that point. Until then, independent oracles, fixtures and research tools can proceed in track-specific directories.

The shared interface must specify:

1. **Optical input:** scene-linear floating-point intensity in declared relative units, dimensions and pixel coordinates; radiance-to-intensity conversion and optics precede sensor dynamics. Display exposure/tone mapping is separate. External input adapters declare their encoding and scaling.
2. **Time:** monotonic simulation time independent of wall/display time; an interval convention, units, storage precision and handling of known discontinuities. The timing track proposes the concrete representation before consumers depend on it.
3. **Sensor state:** persistent state across samples, explicit initialization/reset, separately selectable ideal and generic nonideal behavior, and defined seed/reset behavior. Finite bandwidth integration may require additional internal steps; it must not silently change the renderer's sampling assumptions.
4. **Events:** diagnostic records with `(x,y,t,p)`, polarity convention, ordering/tie rules, capacity and overflow counters. Candidate crossings, delivered readout events and display accumulations remain distinguishable.
5. **Configuration and evidence:** versioned run settings, trajectories, sensor parameters, seed, code revision and hardware; distinct counters for missed optical samples, sensor/readout suppression and software overflow.

These are boundary requirements. Exact signatures, timestamp types, resource bindings and module splits remain the coordinator's first implementation milestone; this document does not assert they already exist. Contract changes affecting another track must be recorded here and in the relevant issue discussion before that track adopts them.

## Integration and validation

Integrate small milestones: shared boundary -> event/reference diagnostics -> independent pixel/optical additions -> combined comparisons. Sensor and rendering fixtures can start independently; full event-level comparison depends on the diagnostic interface. Do not wait for every issue to finish before integrating useful tested pieces.

Fetch and inspect both branches before integration. Merge committed component milestones into this branch, preserving history and resolving conflicts here. Component agents then merge the updated integration branch into their own branches as needed. Never force-push shared history or merge another branch's uncommitted files. A conflict in scientific semantics requires a documented decision, not merely choosing one side of a diff.

Use one GPU validation/benchmark run at a time across all worktrees. Before a run, coordinate with the other active workers and announce its checkout, command and expected duration; release the slot when done. Do not stop another worker's process to obtain the GPU. Record the tested commit, configuration, hardware, command and outcome. Use track-specific evidence paths so the launcher's default historical evidence files are not overwritten by competing worktrees. Functional checks and performance claims remain separate.

Each handoff should include base/head SHAs, changed files, interface changes, checks and results, remaining limits and dependencies. Update the owning GitHub issue with meaningful decisions and evidence. Keep issues open until their resolution criteria are met. Integration must retain the deterministic baseline; runtime changes require the real-context GPU checks plus checks appropriate to the new mechanism. Documentation-only coordination does not require a new GPU run.

No remote host access, additional simulator installation or external-GPU execution is part of this root setup.
