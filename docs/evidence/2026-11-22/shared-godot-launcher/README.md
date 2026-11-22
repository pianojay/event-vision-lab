# Shared Godot launcher smoke check

November 22, 2026, Windows / Intel Iris Plus / Vulkan Mobile. Engine: `4.7.2.stable.official.ed1daf0bf`, resolved automatically from `C:\Godot_v4.7.2-stable_win64.exe\`. Scene/sensor baseline remains `749c238`; only launcher/docs changed for this check.

- `./run-lab.ps1 -Validate -EvidenceDirectory <temporary-output>`: 25/25 GPU checks passed with the shared engine, without elevated execution. Synchronous kernel median 0.881 ms / p95 1.082 ms; this includes submit/sync and is not a sustained performance claim.
- Windows PowerShell 5.1, `./run-lab.ps1 -ProfileSeconds 3 -EvidenceDirectory <temporary-output>`: exit 0, renderer ready, 240×180 / 120 Hz target. Elapsed 3.01451 s; frame median 16.666 ms / p95 16.744 ms; nine skipped intervals overall, zero after the two-second warmup. Only 61 post-warmup frame samples: a launch smoke check, not a sustained benchmark.
- The sandbox blocked Windows PowerShell 5.1's registry-based execution-policy check. The same command succeeded outside the sandbox without changing execution policy. Direct engine execution and the normal PowerShell launcher GPU validation succeeded inside the sandbox.

Output was redirected to temporary directories, preserving the previous committed GPU/profile evidence. This note records the observed results; temporary raw logs are not part of the retained evidence. No sensor-fidelity issue is resolved by this launcher check.
