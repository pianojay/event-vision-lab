# Hardware tiers and barriers

November 22, 2026. These are **planning estimates for a scalable implementation**, not measured requirements or product specifications. The user subsequently clarified that a game is optional: practical event-vision simulation, even as a shader, is the target. The laptop now also passes a [Godot shader/GPU trial](godot-prototype.md); that does not validate the richer tiers below. No remote TITAN RTX machine has been inspected. Ubuntu host `vilab204` is deferred until later.

## What sets the requirement

The basic mechanics—lighting changes, shadows, threshold adjustment, event binning, time surfaces and pipeline configuration—do not inherently demand a high-end machine. Cost rises with the complexity of hidden light transport, sensor spatial/temporal resolution, event rate, and simultaneous inference.

There is no defensible final minimum until a representative game exists. For a first room-scale version, use a **provisional development floor of a reasonably recent four-core CPU, 16 GB system RAM, SSD storage, and integrated graphics with a working supported graphics API**. A packaged runtime may eventually fit in 8 GB, but that has not been demonstrated. CPU model/generation, sustained clocks and GPU capability matter more than the core count or graphics-memory number alone.

This laptop exceeds that provisional RAM floor and has usable measured CPU sensor throughput at 240×180. It still needs an actual engine/rendering trial.

## Planning tiers

The CPU/RAM columns describe a sensible whole-machine pairing. They are not conditions that make every GPU in a row equivalent, nor measured minima. Sensor sizes are sensible trial scopes, not guaranteed rates.

| Machine class | CPU / system RAM planning envelope | Plausible scope | Main barrier |
| --- | --- | --- | --- |
| Current Iris Plus laptop / similar integrated graphics | Four reasonably recent cores; 16–24 GB | Small room, roughly 240×180 sensor, raw events/time surfaces, lighting/shadow puzzles, threshold/ROI/binning tools | Rendering speed, transfers, burst events; learned reconstruction is an experiment |
| Modest discrete GPU, roughly 4–8 GB VRAM | Four to six capable cores; 16 GB | More room for GPU sensor passes, a small polished environment, additional lights/materials; trial 240×180–320×240 | GPU generation/API support and scene complexity; little combined inference headroom should be assumed |
| Balanced RTX-class gaming/workstation GPU, roughly 8–12 GB | Six to eight capable cores; 32 GB | Strong candidate for a complete contained game; trial 320×240–640×480, richer dynamic lighting, one optional compact reconstruction/flow module | Rendering and inference share the GPU; target cadence still needs profiling |
| TITAN RTX, 24 GB, in an adequate host | Six to eight capable cores and 32 GB are a useful starting host; 64 GB helps heavy authoring/datasets | Substantial GPU development and experimentation: richer small scenes, GPU sensor generation, reconstruction/flow, larger buffers; trial 320×240 or 640×480 before increasing | Older GPU throughput, host CPU/access, available GPU share, software compatibility, remote latency |
| Faster recent high-end GPU, roughly 16–24+ GB | Eight to twelve capable cores; 32–64 GB | More concurrent visual complexity, higher sampling or more inference; selected ray-traced effects | Still cannot assume arbitrary high-rate, physically exact light transport |

These tiers overlap. A fast 12 GB card can outperform an older 24 GB card when the working set fits. More VRAM primarily expands capacity; it does not establish time per render/sample. A server with many slow CPU cores may run an engine's main thread worse than a desktop with fewer faster cores.

## TITAN RTX specifically

Assuming the user means **NVIDIA TITAN RTX**, the Turing-era card: NVIDIA specifies **24 GB GDDR6**, 672 GB/s memory bandwidth, Tensor Cores and RT Cores. This is a substantial change from the laptop's integrated graphics. It offers the hardware categories needed for GPU rendering and suitable CUDA inference workloads. [NVIDIA TITAN RTX announcement/specifications](https://nvidianews.nvidia.com/news/nvidia-reveals-the-titan-of-turing-titan-rtx)

My assessment: an available TITAN RTX is sufficient hardware to justify building and testing a substantially richer version of this concept. There is no need to assume another GPU purchase before trying it. This is an engineering judgment, not a measured frame-rate claim.

In particular, optional event-to-grayscale reconstruction should become a realistic GPU integration experiment. Real-time event reconstruction has been demonstrated in the original E2VID work, but that result does not establish performance for this host, chosen model, sensor size, and concurrent renderer. [E2VID paper](https://rpg.ifi.uzh.ch/docs/TPAMI19_Rebecq.pdf)

Check an actual engine and ML environment on the host. Select driver/framework/model binaries that support its GPU generation. Access to CUDA computation alone does not prove that the environment can create an accelerated Vulkan/DirectX/OpenGL rendering context. Shared GPU use or scheduler restrictions can make nominal specifications misleading.

Do not interpret the 24 GB as a guarantee of all of these simultaneously: photorealistic indirect illumination, many deforming objects, multiple reflections/refractions, hundreds or thousands of fresh intensity renders per second, and several learned modules. Begin with a contained scene and add the expensive effects individually.

## The three clocks

Keep these requirements separate:

| Clock | What it controls | Example planning setting |
| --- | --- | --- |
| Player presentation | Smoothness of the visible event view | Around 60 displayed frames/s |
| Intensity/sensor simulation | Which optical changes can be captured | 120 or 240 true intensity samples/s, if achieved |
| Inference | Age/refresh rate of reconstructed images or flow | Perhaps 15–30 updates/s for an optional view, subject to measurement |

A 60 FPS display does not require inference on every frame. It also does not make a 60 Hz intensity sampler accurate for fast flashes.

At 60 FPS, the frame budget is 16.67 ms. Four complete intensity renders during that interval correspond to 240 Hz and average at most 4.17 ms each **before allowing for other work**. Going from 240×180 at 120 Hz to 640×480 at 1,000 Hz increases pixel-sample work by about 59 times even before richer materials or inference. This is workload arithmetic, not a GPU performance prediction.

Timestamps expressed in microseconds do not require a million whole-scene renders per second. Interpolation/adaptive sampling can estimate crossings more efficiently within their assumptions. They cannot reconstruct an unobserved reversal in intensity from identical endpoints. Fully general high-frequency lighting is a simulator-design challenge on every tier.

## Rendering quality can conflict with temporal correctness

Real-time global illumination often amortizes work across frames. Epic explicitly documents that Lumen lighting updates can propagate gradually and that increasing update speed costs performance. For this project, that can spread a sharp physical light transition into a different event pattern. [Lumen technical details](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-technical-details-in-unreal-engine)

Thus a faster GPU helps, but does not by itself make the renderer an accurate event-sensor input. Stable direct lighting and shadows can be the more faithful choice for a particular experiment. Path tracing introduces another problem: stochastic image noise can generate false events unless convergence and temporal handling are controlled.

Use small deterministic test scenes to establish each supported phenomenon, then improve visual richness without silently changing the sensor model.

## Remote TITAN RTX: useful arrangements

| Arrangement | Local laptop does | Remote machine does | Assessment |
| --- | --- | --- | --- |
| Entire game remote | Input, stream decoding and display | World, rendering, event generation, processing, visualization | Best initial interactive arrangement if latency and graphics access are adequate |
| Offline experiments remote | Development, inspect results | Render/reference simulation, reconstruction, profiling | Valuable even with SSH/job-only access or poor latency |
| Local game, remote reconstruction | World and event simulation, most display | Inference on transmitted events | Useful optional feature; leaves the local rendering bottleneck and adds inference delay |
| Remote renderer, local sensor | Sensor and event display | Send intensity images across network | Usually an unattractive initial split: image transfer and synchronization overhead |

For the first arrangement, stream the **already-produced event visualization**. It preserves the intended restricted view without sending hidden RGB to the player. Keep raw event recordings on the server for evaluation; use a deliberate event transport only when local processing requires it. Lossy streaming can alter tiny flashes, so evaluate visibility and use lossless raw data for sensor validation.

At 16 bytes/event, 1 million events/s is **128 Mbit/s** before protocol overhead or compression. Dense flashes can be much worse. A compressed display stream avoids demanding that the network carry the entire raw event stream; its bitrate depends on scene activity, codec and quality.

The remote interactive barrier is total input-to-visible latency: network round trip, queuing, simulation/render scheduling, encoding, decoding and display. A quick ping does not measure all of this. Measure camera control and strobe interactions through the intended connection. Offline work has much weaker latency requirements.

An interactive desktop is convenient but not strictly required: a supported offscreen graphics setup may work over SSH. It must be tested. A shared/headless server may restrict GUI apps, hardware graphics access or long-running interactive processes independently of its GPU model.

## What to inspect on the remote host

CPU model, allocated cores, system RAM/free RAM, GPU identity/free VRAM and competing processes, OS/driver, accelerated graphics-context creation, storage quota, session/job limits, and the intended remote connection. Then run a representative room plus optional inference and measure actual step latency.

The practical strategy with the currently discussed options is to keep a low-resolution laptop version for immediate interaction/design, and use TITAN RTX access to measure richer rendering and advanced perception. If remote interactive performance is good, it can also host the full playable version. Neither avenue needs every ambitious feature enabled at once.
