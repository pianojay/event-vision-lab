# Concept and requirements

Source: [exported conversation](../ChatGPT-Event%20Vision%20Game-20261122-0816.md), November 21, 2026. This is a requirements interpretation, not a claim that every proposed feature was accepted.

**Current scope, clarified by the user on November 22:** simulate event vision without a physical event camera, in a practical setup. High fidelity means representing relevant real-world optical/sensor behavior, not necessarily elaborate game graphics. A shader or mod can be sufficient; Minecraft was an example of trading scene practicality for development simplicity. A shipping game, level progression, collisions and gameplay objectives are not requirements. Godot on this Windows machine is the selected first trial; Ubuntu/TITAN RTX (`ssh vilab204`) is deferred.

## User-established direction

The original proposed game had two purposes: enjoyment and developing intuition by experiencing the world through event vision. The broader project is a simulator; a game is one possible medium. The user's correction is central: **motion is only one cause of intensity change**. Lighting, shadows, occlusion, changing surfaces, reflections, and displays can also produce observable changes.

The hidden simulator may be much richer than the restricted observation channel. The goal is compatible with high-fidelity rendering; hiding RGB does not eliminate the cost of producing the optical signal. The user also proposed obtainable/togglable perception tools, including binning, strobe illumination, sensitivity/dynamic-range controls where meaningful, and advanced grayscale reconstruction.

The export's assistant proposed first-person exploration, named game concepts, a room progression, processing budgets, and several later perception algorithms. These are **candidates**, not settled product decisions. Godot was subsequently selected for a local trial; photorealism at every stage was not required.

## Functional decomposition

```text
World state + controls + physical lighting
                 |
                 v
Hidden photometric rendering: linear intensity over time
                 |
                 v
Stateful event sensor: (x, y, timestamp, polarity)
                 |
                 v
Selectable processing and inference modules
                 |
                 v
Player-visible representation
```

| Function | Conceptual requirement | First operable scope |
| --- | --- | --- |
| World simulation | Relevant geometry, materials, lighting, moving objects, controllable conditions | Controlled shader-rendered scene; game systems optional |
| Non-motion changes | Stationary camera and geometry must still respond to illumination or appearance changes | Toggle light, controlled strobe, animated emissive surface, moving shadow |
| Sensor | Persistent contrast reference, positive/negative thresholds, multiple crossings, timestamps | Ideal deterministic model first; explicit sampled-time approximation |
| Visualization | Present information derived from events | Raw polarity, decaying time surface, temporal accumulation |
| Pipeline engineering | Tools operate at identifiable places in the chain | Thresholds, ROI, polarity selection, post-event spatial binning, accumulation window |
| Active sensing | Change physical light entering the sensor | A light/strobe illuminating the room |
| Advanced inference | Infer appearance/motion from events | Optional later reconstruction module; retain access to raw events |
| Interaction | Change conditions and develop sensor intuition | Repeatable experiments; gameplay objectives optional |

## Sensor semantics that must survive simplification

For an ideal pixel, let `L = log(max(I, epsilon))` and let `R` be its stored contrast reference. Emit an ON event when `L - R >= C_on`, or an OFF event when `L - R <= -C_off`. Advance `R` by the threshold per event, retaining subthreshold residuals. A single rendered interval can contain several crossings. This basic model is consistent with the [AirSim event-simulation description](https://microsoft.github.io/AirSim/event_sim/).

At startup, initialize the reference from the first sample rather than treating an arbitrary zero reference as an observed flash. An explicit simulated sensor startup transient could be added separately.

Interpolating crossing times between samples assumes intensity evolution between those samples. It cannot discover a flash or oscillation that starts and ends between identical endpoints. A 240 Hz simulation gives 4.17 ms samples; microsecond-valued timestamps do not make it a microsecond-fidelity simulator.

Render into a controlled intensity path. Avoid feeding exposure adaptation, tone mapping, temporal anti-aliasing, denoising history, film grain, or other display effects into the sensor unless deliberately modeling an optical/sensor effect. Otherwise, the renderer can manufacture or suppress events. Fix exposure and define linear luminance conversion and dark-floor behavior. Distinguish display contrast, sensor contrast threshold, and actual sensor dynamic range.

Strobe timing must reach world/render sampling, rather than merely flash the final event display. Slower sampling can support a bounded family of slower stimuli, but that fidelity envelope must be declared. Known light-transition times can trigger extra samples; this costs rendering work. Analytic relighting is valid only where its lighting assumptions hold.

## Meaning of the proposed tools

| Tool | Where it acts | Important limitation |
| --- | --- | --- |
| Strobe / projected pattern | World illumination | Creates new observations; fast modulation can alias |
| Contrast thresholds | Sensor generation | Greater sensitivity also raises noise/activity; not a direct displacement gain |
| Refractory period | Sensor generation | Suppresses closely spaced events and changes the measurement |
| Sensor ROI | Generation/transmission | Can reduce capture/transmission work if implemented there |
| Post-event ROI | Processing | Cannot reduce already-completed full-image rendering or sensor work |
| Post-event spatial binning | Processing/display | Merges existing events; differs from binning intensity before thresholding |
| Accumulation / time surface | Representation | Trades persistence against trails and ambiguity |
| Motion magnification / compensation | Inference | Needs an estimate; cannot reveal motion absent from captured evidence |
| Grayscale reconstruction | Inference | Uses priors/initialization; absolute appearance is not uniquely measured by events |

Keep hidden RGB, depth, and object labels available for development comparisons. Player-facing inference must declare any use of ground truth; using it silently would change the observation task. Ordinary collision and audio can remain game systems.

## Fidelity beyond the first version

Photometric consistency matters before sheer visual complexity. A small scene can demonstrate lighting, reflectance, and occlusion without path tracing. General transparent materials, multiple reflections, indirect lighting changes, deformables, and high-speed phenomena expand the rendering and sampling workload substantially.

Noise, bandwidth limits, threshold mismatch, finite photoreceptor response, and refractory behavior are later sensor-model additions. Optical flow, depth, semantics, SLAM, and predictive world models were discussed as extensions; none is required for the initial shader simulator. Reconstruction was explicitly requested as an advanced tool and should remain on the roadmap.
