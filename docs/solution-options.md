# Solution options and dependencies

Assessment date: November 22, 2026. These are implementation options, not installed or validated game stacks. Choose one game runtime; the research packages are optional references or later tools.

**Subsequent scope and implementation:** the target is practical event-vision simulation; a game is optional. Godot was selected and a local shader-only laboratory now works. Its analytic renderer bypasses the stock scene-capture problem described below by computing controlled linear radiance directly. See [Godot prototype](godot-prototype.md). The comparison below is the earlier option assessment; remaining untried integrations are not implied to work.

## Options at a glance

| Route | Required dependencies | Already present | Missing / unverified | Fit for this PC |
| --- | --- | --- | --- | --- |
| Native Godot | Windows x64 standard Godot build, compatible graphics driver, GDScript, custom sensor/render passes | Windows, Git | Engine, actual renderer operation, intensity format and subframe capture | Preferred first trial: compact setup and adequate room-scale features |
| Native Unity | Unity Hub, a supported Unity Editor with Windows build support, C#, render textures, sensor shaders/compute | Windows, Git, MSVC and Windows SDK for an eventual IL2CPP build | Hub/editor/modules, shader path and timing integration | Good alternative; start with a small forward/URP scene |
| Custom browser prototype | WebGL2-capable browser, JavaScript, local static server; optionally Three.js via npm | Edge, Node, npm, Python | Actual GPU/WebGL2 capability, project packages and sensor shader implementation | Useful for fast concept trials; tighter rendering/fidelity constraints |
| Native C++ renderer | MSVC + Windows SDK, CMake, a graphics/windowing library and asset loading | Native compiler/SDK/CMake/Ninja | GLFW/SDL, graphics bindings/loaders, assets and essentially all game infrastructure | Maximum control, substantially more engineering work |
| Unreal-based high-fidelity world | Epic launcher/engine, engine prerequisites, compatible driver, custom linear scene capture/event pipeline | Windows, native tools; launcher prerequisite registration only | Engine and adequate graphics performance | Poor first local choice; consider on a GPU workstation |
| Research simulation / reconstruction | Separate Python environments and selected simulator/model dependencies below | Python 3.14.8, pip, native tools | All CV/ML packages, models, environment tooling; CUDA hardware absent | Offline reference/comparison route, not a ready-made game |

Browser recommendation is conditional: Three.js currently requires WebGL2 through its WebGLRenderer. A browser runtime does not supply a high-fidelity asynchronous sensor automatically. [Three.js WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html)

## Recommended first trial: Godot native

Use the **standard Windows x64 build with GDScript**, avoiding a .NET SDK requirement. Add export templates only when producing a standalone build. Use the [official Windows download](https://godotengine.org/download/windows/) and record the selected version in the project. The official baseline supports simple projects on integrated graphics; that does not certify this workload. [System requirements](https://docs.godotengine.org/en/stable/about/system_requirements.html)

Trial **Mobile** first for a small scene and access to RenderingDevice compute. Forward+ offers a higher-precision path at a likely higher cost. Compatibility is the fallback for basic graphics, but its standard color path has lower precision and no RenderingDevice access. It therefore changes the sensor implementation and fidelity budget. [Renderer comparison](https://docs.godotengine.org/en/stable/tutorials/rendering/renderers.html)

Godot compute shaders require Forward+ or Mobile; Compatibility cannot run that compute implementation. An OpenGL fragment-shader ping-pong approach or CPU sensor is a separate fallback implementation. [Compute shader documentation](https://docs.godotengine.org/en/stable/tutorials/shaders/compute_shaders.html)

The decisive integration trial is **capturing controlled linear intensity before display processing into a sufficient-precision texture**, then maintaining sensor reference state between samples. Do not assume an ordinary screenshot or 8-bit viewport output meets this requirement. If Compatibility is used with limited precision/range, document the resulting contrast quantization and dynamic-range limits.

Dependencies for the first playable room:

- Engine, Git, a working graphics driver, and procedural/basic scene assets.
- Custom event sensor and visualization code; no off-the-shelf shader supplies the entire model.
- Explicit render sampling, simulation clock, profiling, bounded event/history storage, and input/collision.
- No Python, CUDA, ROS, physical event camera, LLM, or OpenAI API needed for the core loop.

Start with a **240×180 hidden sensor**, modest output window, raw polarity and time-surface views, one dynamic light/shadow caster, and a few objects. First measure a 60 Hz complete loop, then attempt 120 Hz sensor updates with a roughly 60 Hz presentation target. Try 240 Hz after profiling. These are staged engineering targets, not measured game performance.

Multiple sensor samples per displayed frame require genuinely updated hidden images. Advancing only physics or repeating the same viewport texture cannot simulate faster photometric change. The engine must support the chosen render scheduling, state interpolation, and timestamp convention; otherwise use an explicitly lower-rate sensor model. Do not promise subframe fidelity based on a physics setting alone.

## Unity alternative

Use a supported Unity release, Windows editor/build modules, and a small forward or URP project. Use linear color space, fixed exposure, suitable floating-point render textures, and a custom pass that captures sensor input before display processing. Check compute support and texture-format support on the actual driver; retain a CPU fallback where practical.

Unity documents a Windows/DX-capable baseline, recommends at least 8 GB editor RAM, and lists C++ tools plus a Windows SDK for Windows IL2CPP builds. This machine has those native foundations, but editor and build modules remain missing. That baseline does not guarantee a high-rate sensor scene. [Unity system requirements](https://docs.unity3d.com/6000.0/Documentation/Manual/system-requirements.html)

The engine/editor toolchain provides its own scripting environment; the absent standalone .NET SDK is not by itself a blocker for standard Unity scripting. Advanced learned inference would still require an inference backend, model conversion if applicable, recurrent-state handling, and latency measurements.

## Why Unreal is a later route

Epic's current recommendation includes **32 GB RAM and at least 8 GB graphics memory**. This laptop has less physical RAM and integrated graphics. Those are recommendations rather than a universal launch prohibition; a stripped-down scene may run, but a high-fidelity world sampled repeatedly is a poor local baseline. An engine install would not remove that bottleneck. [Epic hardware/software specifications](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine)

Use a separate GPU machine if Unreal's richer lighting/material features become necessary. For remote play, stream the final **event visualization**, or transfer raw events when local event processing is required. Both can preserve the restricted observation channel. Measure stream artifacts, latency, network jitter and inference delay. Offline rendered sequences support controlled experiments but do not provide freely interactive world exploration. See [hardware tiers and remote execution](hardware-tiers.md).

## Optional research dependencies

### v2e: video/intensity input to events

The live README recommends `uv`; the inspected manifest requires **Python >=3.14,<3.15**. The installed Python is within that declared range. Packages include NumPy, PyTorch/torchvision, OpenCV, Numba, h5py, dv-processing and utilities. Neither uv nor these libraries is currently available in the inspected environment. Resolve and lock a chosen revision in isolation; Windows wheel availability has not been tested. [v2e manifest](https://github.com/SensorsINI/v2e/blob/master/pyproject.toml)

The README describes CPU PyTorch on Windows by default and a pretrained SuperSloMo checkpoint for interpolation. It warns that interpolated conversion can be much slower than real time. Treat v2e as an offline sensor-model reference and comparison tool, rather than assume it can drive this game live. A native high-rate renderer does not inherently need learned frame interpolation. [v2e README](https://github.com/SensorsINI/v2e)

### ESIM / VID2E: simulation references

Original ESIM's installation targets Ubuntu/ROS/catkin and dependencies including GLFW/GLM; its photorealistic option uses UnrealCV. WSL usability is unverified here. That legacy research stack adds substantial integration work for a Windows game. [ESIM installation](https://github.com/uzh-rpg/rpg_esim/wiki/Installation), [ESIM project](https://github.com/uzh-rpg/rpg_esim)

The newer VID2E repository offers ESIM Python and GPU bindings plus interpolation. Its documented stack includes Python 3.9, PyTorch, pybind11, and older CUDA/cuDNN versions for the GPU route. This does **not** mean original ESIM or every CPU binding requires CUDA. Keep any selected legacy environment separate from v2e and the game. [VID2E README](https://github.com/uzh-rpg/rpg_vid2e)

### E2VID-style grayscale reconstruction

The original E2VID lists PyTorch, NumPy, pandas and OpenCV, and provides a pretrained lightweight model. Its historical installation example uses Anaconda and CUDA 10; it is not a validated installation recipe for this Windows/Python environment. A runnable version, checkpoint loading, CPU behavior, event voxelization, recurrent state, and timing must be checked independently. [E2VID repository](https://github.com/uzh-rpg/rpg_e2vid)

There is no NVIDIA GPU in the hardware inventory, and Ice Lake Iris Plus is absent from the current PyTorch XPU validated-device list. Use CPU inference for a conservative first experiment. A separately tested deployment backend may help; no acceleration or real-time rate is established here. [PyTorch Intel GPU prerequisites](https://docs.pytorch.org/docs/2.15/notes/get_start_xpu.html)

Keep reconstruction an optional module: lower its update rate, allow the raw-event display concurrently, and do not hold the movement/input loop waiting for it. A remote model is another option, subject to measured transport latency. No cloud API is conceptually required.

## Setup order

1. Select and record one portable/native game engine version; run a graphics and sensor-capture trial.
2. Build the minimal room and deterministic sensor path, then apply the [validation gates](validation-plan.md).
3. Profile actual rendering, sensor generation, visualization, and strobe bursts before adding fidelity.
4. Add a project-isolated research environment only when an offline comparison or reconstruction trial needs it. Select each repository's supported Python version; do not downgrade the global interpreter speculatively.
5. Install FFmpeg only if video capture/export is needed; add Blender only when asset authoring calls for it. Neither is required for procedural test geometry.

No dependency installation was performed during this assessment.
