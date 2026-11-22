# Sensor simulation fidelity: prototype and research pipelines

Research date: **2026-11-22, Asia/Seoul**. Prototype audited at `4c3ce83e6a864e4001c2e86f14c350c1b0d9fd05`. This is a source/paper review and improvement proposal, not a new simulator implementation or a reproduction of external results. Follow-up experiments: [temporal accuracy #4](https://github.com/pianojay/event-vision-lab/issues/4), [sensor behavior #5](https://github.com/pianojay/event-vision-lab/issues/5), [rendering and optics #6](https://github.com/pianojay/event-vision-lab/issues/6). See the [experiment plan](fidelity-experiment-plan.md) for sequencing and acceptance evidence.

## Findings

The user's two dimensions are independently adjustable: **the optical signal reaching a pixel** and **the electronics that turn that signal into events**. Temporal sampling couples them and deserves its own assessment. A realistic renderer can feed an ideal sensor; a detailed sensor can consume simplistic images. Neither combination is automatically a calibrated camera simulator.

The present prototype is useful for controlled illumination and ideal contrast experiments. Its largest immediate gaps are unresolved intensity changes between samples, missing nonideal pixel dynamics, and the absence of a complete event stream for comparison. More complex geometry is a separate improvement. A practical next step is an accurate small experiment with declared limits; a renderer replacement or external GPU is not a prerequisite for that step.

Use this decomposition when discussing fidelity:

```text
geometry/materials/light trajectories
  -> light transport
  -> lens + spectral response + pixel footprint
  -> irradiance/photocurrent over time
  -> pixel dynamics + contrast crossing + reset
  -> readout/timestamps/queues/loss
  -> optional processing
  -> visualization
```

Rendering numerical noise, physical photon/electronic noise, software overload, and display trails are different causes of apparent activity. They must remain distinguishable in experiments.

## 1. What our prototype actually simulates

These are observations from the repository, rather than capabilities inferred from Godot's renderer. The **compute shader itself renders the scene**; using Godot Mobile/Vulkan does not make this scene a full engine PBR scene.

| Layer | Current implementation | Fidelity implication |
| --- | --- | --- |
| Geometry and optics | Analytic spheres, box and planes; pinhole rays, 58-degree vertical FOV, one center ray per pixel | No mesh assets, lens distortion, aperture/defocus, pixel-area integration or optical blur |
| Illumination | One controllable point source, cosine diffuse shading, hard shadow ray, fixed ambient; room adds a simple specular lobe | Physically motivated terms, but no calibrated BRDF, indirect transport, area lights, transmission or refraction |
| Intensity | FP32 linear RGB proxy; `I=max(dot(RGB,(0.2126,0.7152,0.0722)),1e-6)` | Avoids display tone mapping in the measurement path; no physical irradiance units or measured sensor spectral sensitivity |
| Pixel | Persistent log reference, ON/OFF crossings, retained residual, initialization without a flash | A meaningful ideal contrast sensor, not simply an adjacent-frame difference image |
| Thresholds | Shader accepts separate positive/negative values; UI supplies the same global value, initially 0.2 | No per-pixel mismatch or independently adjustable UI polarity thresholds |
| Time | 120 Hz target, at most eight catch-up steps per display frame; interpolated camera pose and fresh analytic lighting per step | 8.33 ms nominal input interval; skipped intervals are counted; no bound on missed within-interval changes |
| Event storage | Latest-step ON/OFF counts and latest timestamp per polarity; decaying and cumulative count histories | No complete ordered `(x,y,t,p)` stream; earlier individual crossing times are not retained |
| Nonidealities/readout | None of the bandwidth, refractory, leak, temporal-noise or readout-queue mechanisms below | No calibrated low-light, latency, event-rate saturation or packet-loss behavior |
| Presentation | Activity counts, time surface, binary raw-window presence, labeled debug intensity | Display history/gain is not a sensor response or intensity reconstruction |

Source anchors: [`scene_radiance` and sensor update](../../prototype/shaders/sensor.glsl), [`_process`, sampling limits and parameters](../../prototype/main.gd), [FP32 textures and dispatch](../../prototype/sensor_gpu.gd), [display shader](../../prototype/shaders/display.gdshader), [existing checks](../../prototype/tests/sensor_tests.gd). The shader's direct attenuation is `6/(distance²+1)`, with ambient `0.035`; the room specular term is an ad hoc exponent-32 lobe. These are controlled approximations, not calibrated radiometry.

For a monotonic sampled interval, the core rule is:

`L=ln(I); n=floor(abs(L-R)/C + 1e-5); R <- R + polarity*n*C`.

The last crossing is timed by linear interpolation **in log intensity** between endpoints. An actual discontinuous flash is not a log-linear ramp. A pulse that begins and ends between equal sampled endpoints produces no signal to interpolate; reversals within an interval can also disappear. The tests explicitly preserve a missed-strobe example. The `1e-6` clamp is numerical protection, not dark current, quantum efficiency, a saturation model or a dynamic-range specification. FP32 timestamps also lose precision with elapsed time; long-duration timing needs separate testing.

The committed [25 GPU checks](../evidence/2026-11-22/active-lighting-tests.json) establish selected ideal semantics and analytic-sphere agreement. The [12-second profile](../evidence/2026-11-22/active-lighting-runtime.json) records Intel Iris Plus, 240×180, 120 Hz target, 16.733 ms p95 display interval, nine skipped intervals overall and zero after warmup. They do not establish sustained performance, full event export, real-camera agreement or fidelity for arbitrary motion/light frequencies. No new performance measurements were made for this research.

## 2. What Event6D uses

Event6D is a tracking method and dataset suite, not a single sensor simulator. Distinguish its three data sources:

| Dataset | Optical source | Event source |
| --- | --- | --- |
| EventBlender6D | BlenderProc with Google Scanned Objects | Synthetic events for training |
| EventHO3D | Recorded HO3D RGB-D sequences | Simulated events for evaluation |
| Event6D | Real synchronized event/RGB-D/motion-capture acquisition | Real-camera events for evaluation |

The method conditions reconstruction on depth as well as events. Its tracking throughput and pose-annotation rate are not a simulated photoreceptor bandwidth. The real dataset uses a Prophesee IMX636; this does not imply that the synthetic pixel model emulates an IMX636. [Official paper, §4 and Figure 3](https://chohoonhee.github.io/Event6D/static/pdfs/paper.pdf).

The [official supplement, §1–2 and reference 20](https://chohoonhee.github.io/Event6D/static/pdfs/supplementary.pdf) specifies 120 rendered frames at 60 FPS per two-second synthetic sequence, randomized roughness/specular reflectance, physics-driven object interactions and camera motion. It then uses the video2events pipeline: **FILM frame interpolation -> ESIM -> contrast sensitivities sampled from U(0.16,0.34)**. EventHO3D follows the same conversion pipeline. Thus the base rendered rate is not the event timestamp grid, and “high-frame-rate rendering” in the main paper needs this qualification.

The inspected public [code tree/README at `e04df06`](https://github.com/mickeykang16/Event6D/tree/e04df0691eca2db1d2651cd21152353d0c1dca9e) exposes training/evaluation and prepared data; a complete original rendering/conversion recipe was not identified in that inspected tree. Exact render samples, sensor-input color transform, interpolation multiplier, ESIM revision, threshold-randomization granularity and detailed pixel-noise settings remain unverified. Do not fill these gaps with upstream defaults. The README describes a Python 3.9/PyTorch 2.1.1/CUDA 11.8 environment with compiled CUDA components; this is not a dependency recipe for our Godot app.

**Interpretation:** this is evidence for the value of varied synthetic scenes and real-data evaluation. It is not evidence that every physical camera effect must be modeled to train a useful tracker, nor that successful tracking validates all simulated sensor behavior. Learned interpolation cannot establish that an unobserved physical flash or occlusion was correctly recovered.

## 3. Established approaches and what they improve

The entries cover complementary mechanisms, not a ranking of overall realism. A feature described in a paper is not proof that every current code path or default enables it.

| System | Optical input and timing | Sensor fidelity / useful lesson |
| --- | --- | --- |
| [ESIM, CoRL 2018](https://proceedings.mlr.press/v87/rebecq18a/rebecq18a.pdf) | Renderer-coupled adaptive sampling; brightness-rate and projected-motion criteria | Log crossings, independent polarity thresholds and basic Gaussian threshold noise. Its sampling derivation has scene/linearity assumptions; finite pixel bandwidth is not supplied by the original model. Relevant to #4. |
| [VID2E / `rpg_vid2e`](https://github.com/uzh-rpg/rpg_vid2e/tree/ecbb11a9345bb9d31b4b691e7d82965da4401345) | Interpolates existing video; Python and CUDA ESIM bindings | Separates video densification from event generation. The inspected [CUDA kernel](https://github.com/uzh-rpg/rpg_vid2e/blob/ecbb11a9345bb9d31b4b691e7d82965da4401345/esim_torch/src/esim_torch/esim_cuda_kernel.cu) supports separate scalar thresholds, per-crossing interpolated timestamps and a refractory parameter. That path is not the complete original renderer-coupled ESIM architecture. |
| [v2e, CVPRW 2021](https://arxiv.org/html/2006.07722v2) | Video/synthetic intensity input; optional Super-SloMo interpolation | Persistent Gaussian pixel threshold mismatch, intensity-dependent photoreceptor low-pass, leak and temporal noise. Addresses slower/noisier low-light response; event cameras need not have negligible blur/latency in every condition. A practical reference for #5. |
| [ICNS, Joubert et al., 2021](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.702765/full) | Image-driven sensor characterization | Characterized pixel latency and alternative bandwidth/row-arbitration models. Dense flashes can cause readout delay and structured artifacts; pixel dead time and readout congestion are distinct. Choose an architecture matched to the intended sensor. |
| [DVS-Voltmeter, ECCV 2022](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136670571.pdf) | High-frame-rate intensity input | Stochastic voltage evolution/first-passage timing with photon-related randomness and leakage effects; calibrated model parameters. An alternative to deterministic crossings plus added random events, not a renderer or automatic calibration of a new sensor. [Code](https://github.com/Lynn0306/DVS-Voltmeter). |
| [AirSim event simulator](https://microsoft.github.io/AirSim/event_sim/) | Two rendered RGB frames converted to grayscale; interpolates intervening events | A useful interactive baseline. Documentation explicitly describes event caps; attractive Unreal scenes do not themselves establish accurate timing/noise. Check upstream limits before treating its output as a reference. |
| [PECS, ECCV 2024](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/06110.pdf) | 3D scene, lens simulation and multispectral rendering to photocurrent | Explicitly connects optics/spectral response to electronics. The public [trial implementation](https://github.com/lanpokn/PECS_trail_version) uses UE/AirSim and ICNS-derived circuitry; it says PBRT was deprecated and requires camera-specific quantum-efficiency handling. Valuable #6 reference, not a verified drop-in integration. |
| [Monte Carlo path tracing and statistical event detection, ICCP 2024](https://arxiv.org/abs/2408.07996) | Physically based path tracing with adaptive path sampling | Uses statistical decisions about log-luminance differences to distinguish events from rendering-estimator uncertainty. Illustrates why path-tracer noise must not silently become simulated sensor noise. |
| [VisionSIM architecture](https://visionsim.readthedocs.io/en/latest/overview.html) and [DVS model](https://visionsim.readthedocs.io/en/stable/sections/sensors/dvs.html) | Separate world rendering, optional interpolation, sensor emulation and data layers | A current integration example of a v2e-based event model with mismatch, bandwidth, refractory, leakage and shot-noise controls. Consider as an offline comparison route; no local install or performance validation was attempted. |

The original [ESIM repository](https://github.com/uzh-rpg/rpg_esim) lists different rendering backends and restricts distortion support to its planar/panoramic renderers. This is another reason to specify backend and code revision rather than say “ESIM has realistic graphics/distortion” without qualification. Its Gaussian threshold-noise statement also should not be conflated with v2e's persistent per-pixel mismatch.

In current [v2e code at `f63ab4c`](https://github.com/SensorsINI/v2e/blob/f63ab4c10d29e39a9d500c47be561e295e429c65/v2ecore/emulator.py), refractory time and photoreceptor-noise options are explicit; constructor defaults include disabled bandwidth and zero refractory time. “Using v2e” does not prove nonidealities are enabled. Its `hdr` argument documents **logarithmic** floating-point grayscale input; the normal input path uses a lin-log mapping. Our linear FP32 radiance must be adapted to the chosen interface deliberately, rather than passed through with an assumed HDR convention. Reference comparisons must pin options and input scale.

## 4. What greater realism would change in our experiments

| Question | Mechanism to isolate | Risk in the current ideal scene |
| --- | --- | --- |
| Does a dark surface respond less? | Absolute irradiance, dark current, response bandwidth and noise, in addition to reflectance | Diffuse albedo cancels from equal fractional log changes; arbitrary suppression of black pixels would be misleading |
| How do highlights/glass appear? | BRDF/roughness, reflected/transmitted light, refraction and occlusion | An albedo slider or added sensor noise cannot reproduce these optical effects |
| Why are edges thick or delayed? | Lens PSF, pixel temporal response, readout delay, then display accumulation separately | Display trails can be mistaken for physical response; deterministic point samples omit optical edge integration |
| What happens during dense strobing? | Optical transition timing, finite pixel response, refractory and readout capacity | Endpoint aliasing or software skipped samples can be mistaken for a camera's saturation behavior |
| Is a result comparable to a specific device? | Intrinsics/lens, spectral/irradiance mapping, bias settings, temperature and readout configuration | A generic noise preset or sensor name establishes none of these |

The [Prophesee bias manual](https://docs.prophesee.ai/stable/hw/manuals/biases.html) describes separate contrast, bandwidth/high-pass and refractory controls and warns that bias scales vary by sensor generation. It also notes an IMX636 low-light OFF-tail effect. This supports choosing a particular sensor/operating condition before calibration; it does not justify transplanting a DAVIS noise preset into an IMX636 profile. Lens distortion belongs before pixel sampling, while event remapping/denoising belongs after generation and must be labeled as processing.

## 5. Rendering fidelity without a misleading RGB benchmark

For this project, define fidelity through **errors in the time-varying signal and resulting events**, not the visual impressiveness of a screenshot. A simple matte scene with correct light trajectories can be a better test fixture than a complex scene with unstable temporal shading.

[BlenderProc's renderer documentation](https://dlr-rm.github.io/BlenderProc/docs/tutorials/renderer.html) exposes samples/noise thresholds, denoiser configuration, depth and normal outputs. Those controls make it a candidate reference generator; they do not guarantee a noise-free or physically calibrated sensor input. Record actual color management, exposure, ray samples, denoiser and light-transport settings. Keep scene-linear HDR data for the sensor and a separate tone-mapped preview. Repeated static renders must be checked for false events, and reference event counts must converge as rendering samples and temporal resolution increase.

Numerical Monte Carlo variation is not physical photon shot noise. Likewise, temporal antialiasing, auto-exposure, cached lighting and denoiser changes can manufacture or erase log-intensity changes. Introducing them needs its own error analysis. Path tracing is particularly useful for testing indirect light and refraction offline; it is not necessary for validating the current direct-light controls.

## 6. Hardware scope and conclusions

**Local first:** keep 240×180 deterministic fixtures; build reference event export, timing tests and independent sensor effects in stages. Added per-pixel state is a small capacity increase at this resolution, but dispatch cost, random generation, substeps and event bursts still require measurement. Proposed features are not covered by the existing performance result.

**External GPU later:** use a richer renderer to generate short converged reference sequences, compare models on identical input, and replay results locally. Offline generation separates physical simulated time from wall-clock execution and remains useful without an interactive remote session. Do not require a complete dataset/training stack merely to compare one scene.

At 240×180×120 the current nominal load is **5.184 million pixel samples/s**. At 640×480×1000 it is **307.2 million**, about **59.3 times** larger before extra rays, optics, sensor dynamics or event export. This arithmetic is not a runtime prediction. A single FP32 intensity plane at the latter rate is about **1.23 GB/s uncompressed** before metadata, another reason to keep rendering and sensor processing together rather than stream raw intensity remotely.

The [existing hardware assessment](../hardware-tiers.md) treats TITAN RTX as a candidate, not a verified host. A future trial must inspect driver, framework support for Turing, available memory, CPU/storage and accelerated graphics access. No connection to `vilab204`, installation, external benchmark or real-camera capture occurred here. More GPU capacity changes the feasible workload, not whether parameters are calibrated or a missed flash can be recovered.

## Source and uncertainty record

Sources were inspected on November 22. Exact implementation pins used for source-level claims are Event6D `e04df0691eca2db1d2651cd21152353d0c1dca9e`, v2e `f63ab4c10d29e39a9d500c47be561e295e429c65`, and VID2E `ecbb11a9345bb9d31b4b691e7d82965da4401345`. Paper/section links above support the other comparisons; their upstream implementations were not executed. The official Event6D main paper/supplement were read from the authors' project site because the CVF PDF endpoint was inaccessible; [arXiv v1](https://arxiv.org/html/2603.28045v1) was also cross-checked.

Unknowns requiring experiments remain: exact Event6D generator settings beyond the published description, camera-specific parameter distributions, complete runtime cost of proposed models, sustained local performance and remote compatibility. There is no single universal “research-grade” setting: each claimed phenomenon needs its own evidence.
