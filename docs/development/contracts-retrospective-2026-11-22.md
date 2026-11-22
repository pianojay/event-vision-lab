# Retrospective: the interface is part of the simulator

November 22, 2026. Records the user's response to the first milestone compatibility check and the coordinator's interpretation. This is a discussion record, not a frozen contract or an implementation specification. The [upstream pipeline audit](../research/pipeline-contract-audit.md) investigates precedents for the next design discussion.

## Context

Three independently useful CPU milestones passed a local compatibility check: 55 track tests plus five cross-component probes. They merged without file conflicts, but disagreed at some connection points: log-endpoint interpolation versus held input, reset and interval ownership, zero intensity, event stages and capacity handling. Local compatibility evidence remains on `codex/fidelity-compatibility-2026-11-22`, commit `7dbbfe9`; this memo does not promote that merge to the shared integration branch. No new test result is claimed here.

## User's position

The user emphasized that the interface is substantive work: “Interface and contracts are what makes 1+1=3; the '+' is the '1'.” They questioned whether the contracts must be canonical, using KITTI-style and DSEC-style conventions as examples, and proposed that contracts should be flexible/configurable independently of pipeline integration. They also rejected arbitrary choices: there must be a reason for a chosen behavior or convention. The user is still considering the design.

Preserve these points when continuing development:

- Support flexibility rather than making one component's current local proposal the universal contract by default.
- Separate a configurable scientific/engineering behavior from a file-format agreement.
- Explain a choice through its experiment, target sensor, numerical constraint or consumer requirement.
- Investigate established simulator pipelines as evidence before deciding how components should compose.

No dataset schema, default trajectory, reset policy, clock representation or GPU resource layout was selected by this conversation. The daughter interfaces remain local proposals.

## Coordinator's proposed distinction

This three-layer interpretation was offered for discussion; it is not yet an accepted implementation design:

| Layer | Examples | What changing it does |
| --- | --- | --- |
| Simulation/model choices | Pixel footprint, optical trajectory between samples, sensor bandwidth, dark current, refractory/reset behavior | Changes the modeled signal or measurement; needs model-specific validation |
| Pipeline connection requirements | Time domain/origin, signal encoding, stream identity, event-stage identity, endpoint ownership, completeness and ordering guarantees | Determines whether producers/consumers compose correctly and what an adapter must do |
| Serialization | Field order, array organization, byte order, file/container choice, encoded timestamp units | Can often be adapted without rerunning the simulation; quantization or missing metadata can still lose information |

Suggested principle: configure behavior, declare assumptions, validate connections. Flexibility does not mean that every option combination is supported. A connection may be directly compatible, convertible without loss, convertible with declared error/assumptions, or incompatible. Those categories themselves still need a concrete design.

## Applying the distinction to the observed mismatches

- Held input and log-interpolated endpoints describe different trajectories. An adapter can approximate one with the other, but cannot establish identical event timing by renaming fields.
- A numerical log floor and a physical dark offset have different purposes and effects. They must not be interchangeable unnamed fixes for zero intensity.
- A new run, an in-run contrast-reference reset, an electronics reset and clearing an output buffer are different lifecycle operations. Define them before assigning UI or API calls.
- Interval ownership is primarily a connection agreement once signal/discontinuity semantics are specified. Exact-boundary tests should prevent duplication or loss.
- Generation abort/retry, physical suppression and capture truncation need distinct behavior and counters. Equal record counts do not establish equivalent acquisition.
- Timestamp units/field order are serialization choices; clock identity, rounding, precision and ordering are guarantees behind those choices.

These are reasons to design the connections, not reasons to force every stage into one implementation or to postpone all independent experiments.

## Questions left open

Which experimental profiles should be supported first? Which behaviors need interchangeable implementations? What constitutes a new stream versus an in-run reset? Which conversions can be lossless, and how should approximation/error be recorded? Which clock/duration/precision bounds are necessary for the laptop and later external-GPU workloads? What evidence justifies each default?

The next review should compare options, constraints and validation evidence. It should not treat an upstream default, a familiar dataset name or a passing isolated test as sufficient justification on its own. The [audit](../research/pipeline-contract-audit.md) supplies examples and caveats for that review; no runtime interface is implemented by either document.
