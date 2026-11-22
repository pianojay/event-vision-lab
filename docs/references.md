# References and evidence

Consulted November 22, 2026. Links to live documentation and default branches can change. Record engine versions and repository revisions before implementation; no full dependency installation was validated here.

| Source | What it supports |
| --- | --- |
| [Original ChatGPT export](../ChatGPT-Event%20Vision%20Game-20261122-0816.md) | User intent, intensity-change correction, hidden-world scope, pipeline tools, reconstruction |
| [Machine inventory](evidence/2026-11-22/machine-inventory.json) | Actual local hardware and inspected software |
| [Sensor benchmark output](evidence/2026-11-22/sensor-benchmark.json) and [source](../tools/readiness/sensor-benchmark.cpp) | Measured CPU-only sensor costs and reproducible workload |
| [Intel i7-1065G7 specifications](https://www.intel.com/content/www/us/en/products/sku/196597/intel-core-i71065g7-processor-8m-cache-up-to-3-90-ghz/specifications.html) | Processor class, cores, power, integrated graphics and advertised APIs |
| [Godot system requirements](https://docs.godotengine.org/en/stable/about/system_requirements.html) | Simple-project baseline; not proof of workload performance |
| [Godot renderer comparison](https://docs.godotengine.org/en/stable/tutorials/rendering/renderers.html) | Renderer capabilities, color precision, RenderingDevice availability |
| [Godot compute shaders](https://docs.godotengine.org/en/stable/tutorials/shaders/compute_shaders.html) | Compute requires a RenderingDevice-based renderer |
| [Unity system requirements](https://docs.unity3d.com/6000.0/Documentation/Manual/system-requirements.html) | Windows/editor baseline and Windows IL2CPP native tools |
| [Three.js WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html) | Browser renderer's WebGL2 dependency |
| [Unreal hardware/software specifications](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine) | Recommended RAM/graphics resources and development tools |
| [AirSim event simulation](https://microsoft.github.io/AirSim/event_sim/) | Log-intensity threshold model and adjacent-frame simulation approach |
| [v2e README](https://github.com/SensorsINI/v2e) | CPU/GPU setup behavior, interpolation checkpoint, conversion-cost caution |
| [v2e project manifest](https://github.com/SensorsINI/v2e/blob/master/pyproject.toml) | Python version constraint and package dependencies as inspected |
| [ESIM](https://github.com/uzh-rpg/rpg_esim) and [installation wiki](https://github.com/uzh-rpg/rpg_esim/wiki/Installation) | Research simulator features and legacy ROS/Linux environment |
| [VID2E](https://github.com/uzh-rpg/rpg_vid2e) | ESIM bindings, interpolation, documented research dependencies |
| [E2VID](https://github.com/uzh-rpg/rpg_e2vid) | Reconstruction implementation, dependencies and pretrained lightweight model |
| [PyTorch Intel GPU prerequisites](https://docs.pytorch.org/docs/2.15/notes/get_start_xpu.html) | Validated Intel GPU families; this Iris Plus is not listed |
| [NVIDIA TITAN RTX specifications/announcement](https://nvidianews.nvidia.com/news/nvidia-reveals-the-titan-of-turing-titan-rtx) | Turing architecture, 24 GB memory, RT/Tensor hardware |
| [E2VID paper](https://rpg.ifi.uzh.ch/docs/TPAMI19_Rebecq.pdf) | Published real-time reconstruction feasibility, not a benchmark for the proposed combined game |
| [Lumen technical details](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-technical-details-in-unreal-engine) | Amortized lighting updates and delayed response to lighting changes |
| [Godot RenderingDevice](https://docs.godotengine.org/en/stable/classes/class_renderingdevice.html), [Texture2DRD](https://docs.godotengine.org/en/stable/classes/class_texture2drd.html), [RDShaderSource](https://docs.godotengine.org/en/stable/classes/class_rdshadersource.html) | Actual GPU kernel, texture sharing and runtime shader compilation APIs |
| [Godot data paths](https://docs.godotengine.org/en/stable/tutorials/io/data_paths.html) | Self-contained editor marker and normal per-user cache/data paths |
| [Godot GPU prototype results](evidence/2026-11-22/godot-sensor-tests.json) and [final runtime profile](evidence/2026-11-22/godot-runtime-final.json) | Current implementation evidence; separate from the initial CPU benchmark |

The requirement interpretation comes from the supplied export. Resolution choices, implementation preference, performance gates, and capability judgments are engineering proposals/inferences based on that source, the local evidence, and the documented tool constraints. They are not vendor performance guarantees.
