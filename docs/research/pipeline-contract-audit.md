# Audit: how established event simulator pipelines connect their stages

**November 22, 2026. Source-level audit, not an upstream execution benchmark.** This extends the [fidelity survey](sensor-simulation-fidelity.md) with actual call paths, configuration precedence, state and output boundaries. It informs the [contract retrospective](../development/contracts-retrospective-2026-11-22.md); it does not select our runtime API.

Design follow-up: [#7 — Configurable pipeline contracts](https://github.com/pianojay/event-vision-lab/issues/7). This audit supplies evidence; its suggested design implications remain proposals.

## Method and scope

Inspected six upstream repositories at pinned commits. The [machine-readable source ledger](pipeline-contract-audit-sources.json) records the commit and Git blob ID for each inspected file. Conclusions below apply to these paths/revisions, not every historical version, backend or example of the named simulator. No external dependencies, simulator environments or datasets were installed, and no upstream simulator was executed. The earlier Event6D findings remain in the fidelity survey; its original full generator recipe has not been reproduced.

| Pipeline | Pinned revision | Main separation observed |
| --- | --- | --- |
| ESIM C++ | `4cf0b8952e9f58f674c3098f1b027a4b6db53427` | Data providers/renderers -> per-camera sensor state -> publisher callbacks |
| VID2E / Torch ESIM | `ecbb11a9345bb9d31b4b691e7d82965da4401345` | Video interpolation/input preparation -> log-image CUDA sensor -> per-batch output |
| v2e | `f63ab4c10d29e39a9d500c47be561e295e429c65` | Video/synthetic input -> optional interpolation -> configurable pixel emulator -> writers and event renderer |
| ICNS / IEBCS | `8fdab5c3d078435d091fa8a94ad657e1fedf0c59` | Radiometric-image update -> pixel/event buffer -> optional readout arbiter -> display/storage |
| AirSim example | `1ca93f6f77e4e8a39b2b241c1fe2764da4d7dd41` | Engine RGB requests -> grayscale -> Python/Numba event approximation -> event image/records |
| DVS-Voltmeter | `9d86353ecfaaa1af82b9eb66b162f0bf80cd4861` | Timestamped grayscale input -> configured stochastic sensor -> sorted event arrays/text |

The architectural observations are evidence. Recommendations labeled as lessons are engineering interpretations for our project.

## 1. ESIM: multiple providers and publishers, stateful sensor in between

The [provider factory](https://github.com/uzh-rpg/rpg_esim/blob/4cf0b8952e9f58f674c3098f1b027a4b6db53427/event_camera_simulator/esim_data_provider/src/data_provider_factory.cpp#L44) selects online rendering, a simple source, folder input or rosbag input. The [simulator callback](https://github.com/uzh-rpg/rpg_esim/blob/4cf0b8952e9f58f674c3098f1b027a4b6db53427/event_camera_simulator/esim/src/simulator.cpp#L17) sends updated intensity images and timestamps to one event simulator per camera. Conventional-camera simulation is a separate call on the same input; exposure-corrupted images are not silently substituted for event-sensor input. [Publisher callbacks](https://github.com/uzh-rpg/rpg_esim/blob/4cf0b8952e9f58f674c3098f1b027a4b6db53427/event_camera_simulator/esim_visualization/include/esim/visualization/publisher_interface.hpp#L16) distinguish events, original/corrupted images, geometry and other ground truth.

The sensor's [Config and update](https://github.com/uzh-rpg/rpg_esim/blob/4cf0b8952e9f58f674c3098f1b027a4b6db53427/event_camera_simulator/esim/src/event_simulator.cpp#L21) include separate thresholds/noise, optional `log(eps+image)` conversion and refractory gating. It initializes from the first input, retains state, interpolates individual crossings, consumes reference crossings even when refractory gating drops them, and sorts output by timestamp. This is the inspected code, not a statement that the original paper modeled every nonideality.

The [online sampler](https://github.com/uzh-rpg/rpg_esim/blob/4cf0b8952e9f58f674c3098f1b027a4b6db53427/event_camera_simulator/esim_data_provider/src/data_provider_online_render.cpp#L251) predicts log-brightness change from gradients/flow or uses flow magnitude; minimum sampling rate and adaptation parameters are separately configured. This motion-derived prediction is not proof that arbitrary stationary-camera light switching is resolved.

**Lesson:** configurable providers, sensor parameters and outputs can coexist with fixed callback meanings. Sampling policy remains part of the signal model; exchanging a data provider does not guarantee equivalent temporal fidelity.

## 2. VID2E: preprocessing is part of the measurement contract

The [generation script](https://github.com/uzh-rpg/rpg_vid2e/blob/ecbb11a9345bb9d31b4b691e7d82965da4401345/esim_torch/scripts/generate_events.py#L16) reads grayscale PNGs, computes `log(image/255+1e-5)`, converts seconds to integer nanoseconds, calls the CUDA wrapper and saves named arrays in NPZ. The normalized scale, log conversion and additive epsilon live outside the sensor wrapper. This is not a raw-linear-image API.

The [wrapper](https://github.com/uzh-rpg/rpg_vid2e/blob/ecbb11a9345bb9d31b4b691e7d82965da4401345/esim_torch/src/esim_torch/esim_torch.py#L16) requires FP32 images/int64 times, carries the last image/time and reference state across batches, and exposes reset. It sorts each output batch by time and filters nonpositive timestamps; its output should therefore not be assumed to preserve arbitrary zero-time events. [The CUDA kernel](https://github.com/uzh-rpg/rpg_vid2e/blob/ecbb11a9345bb9d31b4b691e7d82965da4401345/esim_torch/src/esim_torch/esim_cuda_kernel.cu#L99) uses `delta_t > t_ref` except for its initial-event sentinel. ESIM C++ uses `dt >= refractory_period_ns` with its own sentinel. The same parameter name does not establish exact-boundary parity.

**Lesson:** a loader/adapter must declare preprocessing and time conversion. Batch continuity, zero-time handling and threshold/refractory equality require tests before substituting one backend for another. Choosing NPZ versus CSV does not settle any of those behaviors.

## 3. v2e: model configuration, entry-point defaults and writer conventions differ

The [top-level program](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2e.py#L798) passes resolved options to `EventEmulator`, optionally applies a model preset afterward, and constructs a separate event renderer. Input interpolation and display accumulation are not the same sensor operation. A preset can override individually supplied model values.

There is a concrete default-precedence hazard: [class defaults](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/emulator.py#L86) disable bandwidth/refractory filtering; [CLI defaults](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/v2e_args.py#L138) specify 300 Hz and 0.5 ms respectively, and also differ in noise rates. The mere phrase “v2e defaults” is incomplete without the entry point/preset.

The [emulator](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/emulator.py#L636) accepts image timestamps in seconds. Ordinary input undergoes lin-log conversion; `hdr` means already-logarithmic input, not our linear FP32 optical payload. The response/noise path also uses intensity scaling assumptions, so a log-format adapter alone does not establish matching radiometry. Its inspected event scheduling uses FP32 time slots across each frame interval based on the maximum crossing count, rather than our CPU held-input RC solver. No bit-exact timing parity is claimed.

Internal event rows use `(t,x,y,p)` with signed polarity. The [text writer](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/output/ae_text_output.py#L85) converts polarity to 0/1; [the HDF5 path](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/emulator.py#L970) converts timestamps to unsigned integer microseconds through FP32 storage. Writer choice therefore includes encoding/range/precision decisions, not merely a filename suffix.

**Lesson:** retain effective configuration after presets, not just requested arguments. Keep model/solver identity separate from serialization identity. Validate timestamp rounding/range and polarity mapping for every writer.

## 4. ICNS/IEBCS: a separate readout stage exists, but activation matters

The [example](https://github.com/neuromorphicsystems/IEBCS/blob/8fdab5c3d078435d091fa8a94ad657e1fedf0c59/examples/00_video_2_events/1_example_video_to_events.py#L24) specifies latency, jitter, refractory time and front-end time constant in microseconds. It maps video brightness onto a declared illumination scale, initializes the sensor, and advances it using an explicitly chosen `dt`. That mapping is an example assumption, not calibration evidence for arbitrary source video.

The [sensor update](https://github.com/neuromorphicsystems/IEBCS/blob/8fdab5c3d078435d091fa8a94ad657e1fedf0c59/src/dvs_sensor.py#L299) applies `log(img+1)`, intensity-dependent response, noise and refractory/reset handling. [Arbiters](https://github.com/neuromorphicsystems/IEBCS/blob/8fdab5c3d078435d091fa8a94ad657e1fedf0c59/src/arbiter.py#L5) consume event buffers separately; the bottleneck implementation explicitly describes itself as a mock. Importantly, the inspected example constructs a synchronous arbiter but comments out `ea.process(ev,dt)`. Constructing an object is not evidence the readout stage ran.

The [event buffer](https://github.com/neuromorphicsystems/IEBCS/blob/8fdab5c3d078435d091fa8a94ad657e1fedf0c59/src/event_buffer.py#L204) uses an `add_array(ts,y,x,p)` call convention, stores named arrays, sorts before DAT output, and uses microsecond timestamp storage. This differs from both array-column order and our timing CSV convention.

**Lesson:** record the enabled stage graph, input scale and actual readout call path. An event buffer's function-argument order is a formatting/interface agreement; whether an arbiter modifies delivery is an engineering model choice.

## 5. AirSim: inspect the example's clock and executable parameters

The [example loop](https://github.com/microsoft/AirSim/blob/1ca93f6f77e4e8a39b2b241c1fe2764da4d7dd41/PythonClient/eventcamera_sim/test_event_sim.py#L75) requests engine scene images, converts to grayscale, adds 0.001, and passes elapsed wall-clock microseconds derived from `time.time_ns()` into the simulator. In this example, frame request/scheduling delays affect the supplied timeline. That is not automatically a controlled simulation clock.

The [Numba implementation](https://github.com/microsoft/AirSim/blob/1ca93f6f77e4e8a39b2b241c1fe2764da4d7dd41/PythonClient/eventcamera_sim/event_simulator.py#L6) returns structured event records and a separate presence image. It has a fixed event buffer/cap, converts event time to floating seconds, and uses the module's `TOL` in generation. Listed contrast/noise configuration fields are not passed into that inspected kernel. It also reinitializes crossing values from the previous image on each callback. These observations caution against treating this path as our persistent-reference oracle or assuming every listed setting controls generation. The return interface does not provide a dropped-event total.

**Lesson:** audit the call path rather than copying names/defaults. Separate frame acquisition time, simulated physical time, display cadence and buffer loss. No AirSim runtime failure or measured accuracy claim was established in this read-only audit.

## 6. DVS-Voltmeter: calibrated parameter scales and output limits travel together

The [driver](https://github.com/Lynn0306/DVS-Voltmeter/blob/9d86353ecfaaa1af82b9eb66b162f0bf80cd4861/main.py#L49) loads grayscale images and integer-microsecond timestamps, obtains a configured sensor and saves event arrays as text. [Configuration](https://github.com/Lynn0306/DVS-Voltmeter/blob/9d86353ecfaaa1af82b9eb66b162f0bf80cd4861/src/config.py#L22) selects camera-related parameter vectors; CLI settings can supply another vector.

The [sensor](https://github.com/Lynn0306/DVS-Voltmeter/blob/9d86353ecfaaa1af82b9eb66b162f0bf80cd4861/src/simulator.py#L48) initializes without events, keeps residual stochastic-process state and rejects non-increasing frame timestamps. Input brightness differences and averages determine the distribution parameters; normalizing the images changes that model unless parameters are adjusted appropriately. Output event times are rounded and returned as int32 microseconds; clock origin and supported duration need checking before adopting that encoding for another workload. The [sampling functions](https://github.com/Lynn0306/DVS-Voltmeter/blob/9d86353ecfaaa1af82b9eb66b162f0bf80cd4861/src/simulator_utils.py) implement a stochastic event process, not an interchangeable deterministic endpoint solver.

**Lesson:** sensor profile, intensity scale and stochastic solver belong to the experiment specification. Converting text/field layout is separate from making those model assumptions equivalent.

## 7. KITTI/DSEC: dataset compatibility includes meaning, not just layout

[DSEC's official format](https://dsec.ifi.uzh.ch/data-format/) uses event arrays in HDF5, microsecond timestamps, a time offset to align events with images, and a millisecond-to-index accelerator. Event coordinates are raw/distorted, while its images are rectified; associated maps define the transformation. Exporting fields with matching names without the correct offset, coordinate-space and calibration metadata would not reproduce that convention. A synthetic DSEC-style export must not imply that the data were physically captured or carry DSEC's calibration.

[KITTI raw data](https://www.cvlibs.net/datasets/kitti/raw_data.php) distinguishes unsynchronized/unrectified data from synchronized/rectified data and supplies timestamps/calibration. “KITTI style” should name a particular task/product and convention; it is not a complete event-sensor contract. The user's comparison is useful as an argument for multiple adapters, rather than a reason to force one dataset layout into the internal pipeline.

## 8. Design implications for our three components

These are proposals for review. They do not finalize a common struct, file schema, solver or preset.

| Decision | Evidence/reason needed | Boundary or configurable option to consider |
| --- | --- | --- |
| Input signal and its temporal interpretation | Match the optical experiment; test missed pulses, ramps and response convergence | Declare linear/log encoding, scale and trajectory mode; distinguish model-changing resampling from lossless conversion |
| Clock and lifecycle | Multi-source synchronization, reproducibility and long-run precision | Declare origin/domain, units, range and stream/reset identity; adapter rejects incompatible histories |
| Sensor/solver profile | Intended physics, bias/calibration evidence or controlled ideal comparison | Independent model/solver IDs and parameters; do not encode a sensor model in an output format name |
| Enabled processing/readout | Identify which stage changes timestamps or suppresses events | Record the actual stage graph and candidate/delivered/captured identities; validate enabled calls |
| Numeric boundary behavior | Exact threshold/refractory touches, FP32 payloads and repeated resets | State equality/tolerance/endpoint rules; test each supported backend rather than assuming universal parity |
| Serialization adapter | Consumer conventions and acceptable quantization/range | Named polarity/coordinate mappings, time conversion, completeness/provenance metadata and round-trip/error tests |
| Default configuration | Experiment goal, measured cost or explicit baseline | Persist effective values after defaults/presets and justify them; no arbitrary “realistic” preset |

A useful future connection validator could distinguish direct compatibility, lossless representation conversion, declared approximation and rejection. A timestamp unit conversion can be lossless only within its numeric constraints; endpoint frames converted into held intervals impose a trajectory approximation. Neither a universal optional-fields dictionary nor one fixed dataset format resolves that difference.

The immediate next design discussion should choose supported experimental profiles and evaluate their combinations before specifying a GPU ABI. Keep deterministic fixtures usable independently. Do not add every configuration switch speculatively, and do not accept arbitrary combinations merely because the types match. The local 60-test compatibility result establishes selected CPU composition probes, not runtime parity across the upstream pipelines.

## Limits and follow-up

This audit follows selected source paths and example entry points. It does not exhaust all writers/backends, establish stochastic statistical parity, resolve dependencies/licenses for integration, or validate real-device fidelity/performance. Source-level hazards need executable fixtures before they become runtime failure claims. Further numerical comparisons should pin each effective profile, feed identical declared signals, and separate missing events, time quantization, model differences and software loss.

The earlier survey included PECS and VisionSIM; neither was added as a deep source case here. A previously used VisionSIM documentation URL returned 404 during this pass. That is an access/version limitation, not evidence that its functionality is absent. No remote GPU or camera hardware was accessed. Nothing in this audit resolves issues #4–#6 or authorizes a final contract decision on the user's behalf.
