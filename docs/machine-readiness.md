# Machine readiness

Initial inspection: November 22, 2026 (Asia/Seoul). The inventory and CPU measurements below are the preimplementation snapshot. **Subsequent result: Godot 4.7.2 Mobile/Vulkan and the shader prototype now run on this Iris Plus GPU; 16 GPU checks passed.** See [current implementation and measurements](godot-prototype.md). The table of installed tools below describes the earlier inspection, not the post-download state.

## Observed machine

Source: [machine-inventory.json](evidence/2026-11-22/machine-inventory.json). Hardware was queried with Windows CIM and `Get-Volume`. The initial sandbox denied hardware queries; the approved read-only query succeeded.

| Component | Observed | Implication |
| --- | --- | --- |
| Computer | LG 17Z90N-VA76K | Laptop thermal/power limits matter during sustained workloads |
| OS | Windows 11 Home x64, build 26300 | Native Windows development is the simplest route |
| CPU | Intel i7-1065G7, 4 cores / 8 threads | Adequate for a small game and modest native sensor processing |
| Physical RAM | 23.72 GiB; 13.25 GiB OS-reported free at inspection | Enough capacity for a compact engine project; availability varies |
| Graphics | Intel Iris Plus integrated graphics; driver 30.0.100.9836 | Main rendering/inference constraint; shares system resources |
| Display mode | 2560×1600 | Run the hidden sensor far below desktop resolution |
| D: free space | 163.45 GiB | Sufficient for a compact prototype and development assets |
| C: free space | 232.72 GiB | Sufficient capacity for optional development environments |
| Physical drives | HFS512GD9TNG-L2A0A and TS512GMTS830S, roughly 512 GB each | Disk throughput was not benchmarked |

Windows reported `AdapterRAM = 1 GiB`; **this is not a trustworthy dedicated-VRAM capacity measurement for this integrated GPU**. Do not compare it directly to a discrete card's VRAM or assume all spare system RAM provides equivalent graphics throughput.

Intel lists this processor as a 15 W mobile part with a 1.3 GHz base and up to 3.9 GHz turbo, plus DirectX 12 / OpenGL 4.6 support. These specifications support trying a lightweight graphics path, but do not verify the installed driver's capabilities or sustained clock behavior. [Intel specifications](https://www.intel.com/content/www/us/en/products/sku/196597/intel-core-i71065g7-processor-8m-cache-up-to-3-90-ghz/specifications.html)

## Installed software

| Item | Status |
| --- | --- |
| Git | 2.56.0.windows.4 |
| Node / npm | 26.13.0 / 11.20.0 |
| Python | 3.14.8, `C:\Python314\python.exe`; only pip 26.2.1 found in that interpreter |
| Visual Studio Build Tools | 2026, 18.11.2; C++ tool component detected by `vswhere` |
| MSVC / Windows SDK | 14.51.36231 / 10.0.26100.0 |
| CMake / Ninja | 4.3.1-msvc1 / 1.13.2 bundled with VS; absent from ordinary PATH |
| Godot / Unity / Unreal | Not found on PATH, in inspected standard engine folders, or registrations; custom/portable installs remain possible |
| .NET | Runtime directories exist; no SDK found at the checked standard SDK path |
| Python CV / ML packages | NumPy, OpenCV, PyTorch, v2e, E2VID not installed in the inspected interpreter |
| uv / FFmpeg / Docker / CUDA toolkit | Not found on PATH; no claim of exhaustive disk-wide absence |
| WSL | Executable exists; sandbox denied distro query. Installed distro and usable WSL status remain unknown |

The MSVC compiler was actually used successfully for the benchmark below. An Epic Games Launcher **prerequisites** registration exists; it does not establish an installed Unreal Engine.

## Measured sensor processing

Built and ran [sensor-benchmark.cpp](../tools/readiness/sensor-benchmark.cpp) with MSVC `/O2 /std:c++17`. Raw output: [sensor-benchmark.json](evidence/2026-11-22/sensor-benchmark.json).

This single-thread benchmark consumes precomputed linear-intensity frames, computes logarithms, maintains contrast references, emits multiple events with interpolated timestamps, and writes 16-byte records to a reused vector. Threshold is 0.25 log units. There are 60 warmup and 600 measured samples per case. Basic residual, polarity, threshold, and static-input checks passed.

Two synthetic workloads: 1/16 of pixels changing, or the entire image changing. Active pixels cycle through log-intensity offsets `0, +0.625, 0, -0.625`. This generates large repeated bursts. The activity fractions describe this benchmark, not a claim about typical gameplay.

| Sensor size | Changing pixels | Median ms/sample | p95 ms/sample | Events/s at simulated 240 Hz |
| --- | --- | ---: | ---: | ---: |
| 240×180 | 6.25% | 0.458 | 0.559 | 1.296 million |
| 320×240 | 6.25% | 0.903 | 0.997 | 2.304 million |
| 640×480 | 6.25% | 3.857 | 7.624 | 9.216 million |
| 240×180 | 100% | 1.100 | 2.527 | 20.736 million |
| 320×240 | 100% | 1.829 | 4.315 | 36.864 million |
| 640×480 | 100% | 7.796 | 17.365 | 147.456 million |

A 240 Hz sample has a **4.17 ms total budget**. At 240×180, these results leave some CPU headroom for other work. At 320×240, the dense case already exceeds the budget at p95. At 640×480, even the sparse case does. This supports starting small and measuring strobe bursts explicitly.

These are **sensor timings, not game FPS**. Rendering, GPU readback, event sorting, realistic noise, refractory periods, pipeline filters, display, physics, and inference are excluded. Events are appended in pixel order with per-pixel interpolated times; no globally chronological stream is produced. Buffers are preallocated, no disk recording is timed, and the run is short. Thermal saturation and simultaneous CPU/GPU load were not assessed. A GPU implementation could have a very different profile.

Reproduce from the workspace:

```powershell
.\tools\readiness\run-sensor-benchmark.ps1
```

The runner discovers MSVC, builds into the evidence directory's `build/` subdirectory, checks output JSON, and replaces that directory's benchmark result on rerun. Pass `-OutputDirectory` to keep a separate run.

## Capability assessment

| Function | Local assessment | Basis / remaining condition |
| --- | --- | --- |
| Small interactive 3D room | Plausible | CPU/RAM and engine baselines; actual rendering untested |
| Raw events, time surfaces, accumulation, ROI, polarity | Plausible at low resolution | CPU benchmark supports the sensor core; integration still needed |
| Dynamic lights, shadows, appearance changes | Plausible with a bounded scene | Keep dynamic shadow/light count small; measure GPU cost |
| Threshold changes, sensor noise, refractory behavior | Plausible | Extra implementation and cost beyond benchmark |
| Strobe gameplay | Plausible with defined temporal limits | Burst load and unobserved flashes are explicit risks |
| General reflections/transparency/indirect light | Conditional, costly | Rendering method and sensor capture must preserve effects |
| Classical optical flow / motion compensation | Conditional | Resolution, method, and update rate determine cost; no algorithm benchmark |
| Grayscale reconstruction | Offline/low-rate experiments plausible; interactive rate unknown | No model installed or timed; CPU path or separately validated backend required |
| Large learned perception stack / training | Poor local target | No supported CUDA GPU; CPU and integrated graphics contend with the game |
| Rich photorealistic world + high-rate sampling + reconstruction | Unsuitable as the baseline | Combined rendering, transfer, and inference demand exceeds a prudent budget for this machine |

The GPU inventory contains no NVIDIA adapter. Installing CUDA does not add CUDA hardware. PyTorch's current Intel GPU validation list covers newer Arc/Core Ultra devices, and does **not** list this Ice Lake Iris Plus. Treat CPU as the conservative PyTorch path; other inference backends need their own compatibility and latency trials. [PyTorch Intel GPU documentation](https://docs.pytorch.org/docs/2.15/notes/get_start_xpu.html)

## Resolution and data budgets

At 240 Hz, 240×180 requires 10.37 million pixel samples/s; 320×240 requires 18.43 million; 640×480 requires 73.73 million. Desktop-native 2560×1600 would require 983.04 million, about **95 times** the first option. These are arithmetic sample counts, not measured GPU throughput.

A single R32F image is approximately 0.165 MiB at 240×180 and 0.293 MiB at 320×240. Reading one such image at 240 Hz moves at least 39.55 or 70.31 MiB/s respectively, before transfer overhead. RGBA32F is four times those figures. GPU synchronization latency can dominate these modest byte counts; prefer keeping sensor state and visualization on GPU if the engine supports a sound implementation.

At 16 bytes/event, 1 million events/s is 15.26 MiB/s, about 0.89 GiB/minute uncompressed. The benchmark's 240×180 dense case would produce about 316 MiB/s if serialized at that rate. These are buffer/recording estimates, **not measured disk bandwidth**. Bound live history, expose dropped-event counters, and avoid permanent raw recording by default.

No hardware purchase is needed to establish whether the core interaction is fun. If later work requires the rich local stack, use a separate GPU workstation or remote development machine. Scope and benchmark the target scene/model before choosing hardware; a generic VRAM number alone cannot guarantee performance.
