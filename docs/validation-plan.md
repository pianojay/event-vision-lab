# Validation plan for an operable prototype

This plan separates hardware plausibility, simulator correctness, and practical fidelity. A shipping game is not required. The CPU benchmark and the initial Godot shader/GPU checks have now run; see [current results and limitations](godot-prototype.md). Broader validation below remains future work unless explicitly recorded there.

The [fidelity experiment plan](research/fidelity-experiment-plan.md) adds concrete proposals for temporal convergence and complete event output (#4), sensor dynamics/noise/readout (#5), and optical/material comparisons (#6). It defines the evidence needed beyond the existing 25 ideal-model GPU checks; none of those new experiments has run yet. See the [research comparison](research/sensor-simulation-fidelity.md) for source provenance and calibration limits.

## Gate 1: graphics and intensity capture

Run the chosen engine on this actual Iris Plus driver. Record engine version, graphics API, adapter, viewport formats, power mode, and sensor/display resolutions. Test both the preferred renderer and fallback where relevant.

Render a stationary test patch at controlled linear intensities. Verify the sensor input numerically, including values in dark regions and changes below display-level contrast. Check fixed exposure and the absence of display postprocessing in the sensor path. Repeated identical world/camera state should produce identical input within a documented tolerance.

Pass condition: a stable hidden intensity path with known precision/range, not merely an editor that launches.

## Gate 2: correct event behavior

| Controlled experiment | Required result |
| --- | --- |
| Stationary camera, objects, and lights | No events in the deterministic ideal model after initialization |
| Stationary camera and object, toggle a light | Events occur despite no motion |
| Slow monotonic intensity ramp | Correct polarity, multiple crossings, retained subthreshold residual |
| Moving textured edge | Event pattern follows projected contrast change |
| Uniform object moving within uniform appearance | No artificial motion mask or semantic outline |
| Light pulse entirely between regular samples | Demonstrate the endpoint sampler's miss; extra transition sampling should recover it |
| Controlled strobe with swept phase/frequency | Report missed transitions and timing error within the declared supported regime |
| Sensor threshold / ROI / post-event binning | Behavior agrees with where the module acts in the pipeline |
| Reconstruction enabled/disabled | Raw-event access remains; inference receives no undeclared RGB/geometry inputs |

For sample interpolation, compare against densely sampled analytic intensity trajectories and quantify event count, polarity, and timestamp errors. Timestamp units alone do not establish accuracy. Introduce noise and refractory behavior only after deterministic behavior is verified.

## Gate 3: complete-loop performance

Use a controllable scene with a moving object, a shadow, a changing emissive surface, and a strobe. Collision and other game systems are optional. Measure the simulator runtime separately from the editor.

Initial engineering targets:

- Sensor resolution: 240×180; presentation window around 1280×800 or smaller, adjustable.
- Establish 60 Hz complete operation first; then try 120 Hz true intensity/sensor sampling. A 240 Hz sensor is a stretch target.
- At each setting, measure total frame/sensor-step median, p95 and p99; GPU rendering, transfer/waiting, sensor processing, display, and any inference separately.
- At 60 Hz the frame budget is 16.67 ms; at 120/240 Hz the sensor interval is 8.33/4.17 ms. Include burst work and concurrent rendering, not only average sensor time.
- Record input-to-visible response and inference observation age. A provisional playability target is p95 response below 50 ms; choose the final target through playtesting.
- Run at least 10 minutes on AC power after warmup, including dense strobe activity. Record dropped events, buffer peaks, memory growth, and thermal/power-related degradation.

Pass condition: the declared cadence remains stable, interactions are usable, and overload is visible in counters. If it fails, lower resolution, scene complexity, or supported stimulus speed and repeat the affected gate. Silently capping events or skipping samples would change the sensor; expose that behavior.

## Gate 4: practical observation experiments

Make experiments repeatable: change camera pose, object movement, illumination and surface appearance independently. Compare event output with controlled input/ground truth. Supply a reset, parameter readouts and clear controls. If a game is later useful as the medium, an objective can be added separately.

Check that accumulation, sensitivity and active illumination expose their actual trade-offs. A reference intensity view is useful for evaluation and must be explicitly distinguished from event-derived reconstruction. Progress toward practical scenes/materials and compare against published sensor behavior or recorded real event data; visually plausible output alone does not establish fidelity.

## Gate 5: optional advanced perception

Run a pretrained reconstruction model first against a recorded event sequence. Confirm supported dependencies and correct preprocessing; record model/input size, update rate, median/p95 inference latency, recurrent-state reset behavior, memory usage and output artifacts.

Then measure it concurrently with the game, including event batching and transfers. If it stalls rendering or falls behind, use a worker with bounded history, lower-rate updates, or offline/remote operation. Optical flow and motion compensation need equivalent method-specific trials.

The full high-fidelity concept remains open until representative world effects and these advanced modules pass together on the intended runtime machine.
