# Nine-station interaction stage

The default application now opens a bounded 80 by 60 event stream with a 16,666,667 ns target sample period. It displays nine optical interactions in one navigable analytic 3D scene. The host schedules integer sample times. If rendering, readback, event expansion, or processing takes longer than the requested period, simulation slows without skipping intervals. This is not a real-time guarantee or a calibrated camera.

## Run and capture

```powershell
./run-lab.ps1
./run-lab.ps1 -AcquisitionConfig tools/stage/stream-short.json -EventCaptureDirectory runs/stage-short -EvidenceDirectory runs/stage-short-launch -CapturePath runs/stage-short.png -View 3
./run-lab.ps1 -AcquisitionConfig tools/stage/stream-sustained.json -EventCaptureDirectory runs/stage-sustained -EvidenceDirectory runs/stage-sustained-launch -ProfileSeconds 600
```

Use a new capture directory. A stream config permits omission of `EventCaptureDirectory`. Then no event archive is requested, and the report distinguishes that omission from capture overflow. `ProfileSeconds` stops stream acquisition after the requested wall duration; `duration_ns` limits simulation duration. Pausing freezes the active wall pacing clock and simulation state. A pending sample can finish.

The old sphere, orbit-light, and room presets remain on 1, 2, and 3. They disable the interaction stage. The old `-Validate` GPU suite remains available. A legacy `-ProfileSeconds` run without an acquisition config retains its original profile for regression.

## Controls and state

| Control | Result |
| --- | --- |
| J | Enable the interaction stage |
| Station selector, K | Select and focus one of nine stations |
| H | Refocus the selected station |
| Overview button | View all nine stations together |
| X | Compare the selected interaction with its declared control |
| One-factor slider | Change the named material parameter within validated bounds |
| Z | Reset only the selected material preset; the phosphor station also clears its population |
| Object translation slider | Translate the station geometry independently of the camera |
| Stripe slider | Translate the rear emissive pattern for transmission/refraction and rear excitation in the subsurface slab |
| Excitation overlap slider | Split source energy between excitation and emission bands |
| WASD, Q/E, arrows, right drag | Translate and rotate the camera |
| L, azimuth, elevation, strength, B | Control point illumination independently of the camera, except explicit camera-mounted mode |
| R | Finish the interval, then reset the sensor and event-derived state; preserve optical population |
| P | Pause acquisition and material time |
| V | Change observation only; the intensity view is labeled truth |
| O, G, Y, U | Toggle central ROI, bin size, polarity selection, and temporal representation |
| I | Show relative grayscale inference |

Every stage shows parameter names, values, its registry model, and missing physics. Treatment controls are zero absorption, lower diffuse albedo, zero glossy lobe, zero transmission, equal refraction indices, zero fluorescence yield, zero phosphor output, zero opposite-face slab transport, and zero indirect bounces. The control changes only the selected station. It does not reset sensor reference history.

Truth component selection exposes direct/converted fluorescence or absorbed/untraced refractive energy in the RGB truth view. The detector always consumes total intensity from texture alpha. A truth view must not become a new optical stimulus.

The media display has a default reduced-flashes setting and an explicit opt-out. It maps media to grayscale with a maximum linear SDR luminance of 0.08, then applies the sRGB encoding transfer. This display-only remapping preserves optical/sensor values. The earlier encoded-value multiply reached only RGB8 20 (linear luminance 0.007) in an actual recorded raw pane and was overly dim. Actual viewport output must be measured to assess the transfer function and temporal behavior. It is not a safety certification. Strobe remains off by default and is an explicit optical stimulus.

## Geometry and restricted models

Station centres are `(x,y,z)` with `x=(-3,0,3)`, `y=(6,3.5,1)`, and `z=-3` metres. Patterned emissive background planes lie at z=-5 and z=4. Two finite 1.8 m square emitters on the rear plane are centred behind transmission and refraction. Their relative linear radiance is `0.44 + 0.36*sin(2*pi*(local_x-stripe_offset)/0.5 m)`, bounded from 0.08 to 0.8. The emitter boundaries stay fixed while the stripe translates. Rays outside the emitters see the fixed checker. The front plane remains fixed. These are prescribed emissive sources, separate from point-lamp illumination. Both treatment and control observe the same sources through their actual ray paths. Navigation changes actual rays and occlusion, not screen-space material labels. All material functions operate before the logarithmic sensor.

| Station | Implemented geometry and optical model |
| --- | --- |
| Absorption | Homogeneous slab observed through a finite aperture; Beer attenuation uses thickness divided by ray cosine |
| Diffuse | Radius 0.8 m sphere, Lambert reflectance, point-light inverse-square irradiance, hard shadows |
| Glossy | Radius 0.8 m sphere, conservative reciprocal cosine-power BRDF plus diffuse term |
| Transmission | Nonbending pane with separate reflected and transmitted background rays; R+T+A=1 |
| Refraction | Adjacent radius 0.43 m sphere and parallel slab; trace each returned exit ray into the patterned background; account for front reflection, primary transmission, absorption, and untraced internal reflection |
| Fluorescence | Point-source excitation coupled to two narrow bands; excitation/emission wavelengths 450/550 nm, detector weights 0.1/1, prompt conversion |
| Phosphorescence | Uniform rear excitation irradiance held over each interval; host-owned stored energy; optical emission persists after excitation ends |
| Subsurface | Infinite lateral diffusion slab viewed through a finite aperture, thickness 0.2 m, absorption 0.1/m, reduced scattering 100/m, rear stripe halfwidth 0.04 m; opposite-face spatial exit |
| Interreflection | Equal horizontal 1 m squares, gap 1.2 m, host geometry-derived view factor with 64 by 64 quadrature, uniform diffuse patch radiosity, 16 bounces |

The subsurface slab satisfies `mu_s_reduced >= 10*mu_a`, `H*(mu_a+mu_s_reduced) >= 10`, and `stripe_halfwidth*(mu_a+mu_s_reduced) >= 3`. It uses the registry's fundamental-depth injection approximation. The visible finite aperture does not imply solved lateral slab boundaries. There is no screen-space blur or temporal diffusion state.

The interreflection source sits at `(0,-0.3,3)` relative to the patch centre. The reflector is at y=-0.6 and the receiver at y=0.6. A baffle at z=1 spans x within 0.8 and y from 0.12 to 0.68. It blocks source-to-receiver paths while leaving the mutual patch volume at absolute local z at most 0.5 clear. The focused camera views from the side. Direct irradiance is evaluated at the reflector centre and treated as uniform. The approximation does not resolve irradiance variation across a patch. Changing the main point-light position does not move this dedicated source. Lamp power and prescribed pulses affect it.

Surface defaults, bounds, and missing physics come from `prototype/materials/registry.json`. The stage validates parameter changes at the host boundary. No lens, exposure integration, volumetric path tracer, caustic solver, calibrated spectral response, or nonideal sensor was added.

## Processing and persistence

The immutable event boundary remains `event_batch(events, cursor_ns)` with `[x,y,t_relative_ns,p]` rows. Processing consumes every completed batch before the next host sample. The raw window and the processed view each use bounded streaming state. ROI, bins, polarity, temporal settings, and capacity clear only the processed view. Gain and normalization retain it.

Forward grayscale integration keeps one binary64 log estimate per raw pixel. It uses a declared constant log prior and actual ON/OFF thresholds from the completed sample. ROI, binning, and polarity controls do not affect it. It retains no event history and cannot warm from an earlier capture point. Sensor reset starts a fresh constant prior. Material reset does not reset inference. The display maps inferred relative intensity with fixed `I/(1+I)`. Silent initial texture and absolute intensity remain unknown.

Saved settings include material parameters, camera, processing, inference prior, and display policy. Loading validates material and processing settings. A changed inference prior starts new inference. Optical population is retained. Processing semantic changes clear processing; gain retains it. Settings are saved at `user://interaction-settings.json`, with the effective path shown in the status label.

## Bounded stream versus diagnostic archive

`archive_mode=diagnostic` retains the previous ten-million-pixel-value, ten-thousand-frame, two-million-generated-event limits and full optical/8-float diagnostics. Use it for independent CPU parity. `archive_mode=stream` reads the current GPU diagnostics, expands the current event batch, and discards diagnostics after processing. It keeps no optical frames or historical parameter arrays. Optional CSV output stores at most `capture_capacity` events and reports drop-newest overflow separately from generated events. No-output streaming reports `capture_not_requested`.

Both profiles abort an interval on invalid diagnostics or an excessive candidate batch. Stream mode aborts before any per-pixel anchored count reaches eight million, below FP32's exact-integer limit. This is an explicit failure, not an automatic sensor reset. The host retains only the next sample time in stream mode. Recent frame timing retains at most 4,096 entries. Raw and processed event windows each default to 100,000 rows; exponential modes retain only per-bin state.

Reports include elapsed wall and simulated time, sample count, skips, stage/sensor/expansion/capture/processing loss, bounded buffer residency, readback time, processing time, recent frame timing, and dispatch-to-host callback latency. Static allocator memory excludes GPU, driver, and full process memory. It is a measurement hook, not a total-memory claim. GPU optical phase and the legacy main event-view timestamps remain FP32. Integer event timestamps do not establish long-run optical phase accuracy.

## Integrated experiment matrix

```powershell
python -B tools/stage/experiment.py prepare runs/stage-matrix-v2
./tools/stage/run-matrix.ps1 -Protocol runs/stage-matrix-v2/protocol.json
python -B tools/stage/experiment.py analyze runs/stage-matrix-v2
```

Version 2 changes the transmission and refraction stimuli to `stripe`, with offset `0.2*sin(3*t)` metres and fixed camera, geometry, and point lamp. The original moving-pane and camera trials generated peripheral activity; the old `stripe` action did not affect either station's optical input. The finite rear emitters fix that missing stimulus. This is a new physical experiment. The original protocol, captures, failures, central region, and numerical gates remain unchanged. New captures must use a separate directory. GPU results are required before claiming that the revised task passes. This source change supports issues #9, #20, #21, and #1 without establishing user comprehension.

The protocol is written before captures and refuses an existing output directory. It specifies 45 actual stage runs, with treatment, paired control, static control, twice the temporal sampling, and twice each spatial dimension for every station. Prescribed trajectories disable scene edits. A static trial initializes phosphor population at its steady state, except its explicit dark control; pulse trials start at zero population.

Analysis retains FP32 optical traces, mean log intensity, emitted events, source hashes, separate count/polarity task statistics, independent recorded-input sensor results, and scoped runtime metrics. The event-only task locates activity in a fixed central region and compares spatial histograms. It does not read optical truth. The optical evaluation separately compares the paired archive. Tolerances are declared in `protocol.json`, and failures remain in `results.json`. Count-density convergence is a scoped test, not proof of full radiometric accuracy.

The parent GPU coordinator runs captures serially. Headless checks validate control/state behavior and cannot certify shader execution. Before the full matrix, the first shader smoke capture and a 61-sample stream completed on real Vulkan; the latter emitted 14,752 events with no loss and took about 2.39 wall seconds for one simulated second. Those measurements preceded the paired slab addition and final station UI changes. They do not validate the final matrix or sustained behavior.

```powershell
python -B -m unittest tools.stage.test_experiment -v
& 'C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --headless --path prototype --script res://tests/interaction_stage_tests.gd
```

At the initial integration checkpoint, three runner tests and fifty stage/state checks pass. The existing 69 controls and 43 acquisition checks also pass. Full stage GPU, spatial/temporal, sustained operation, and actual output analysis must be recorded separately before claiming their criteria complete. No material or parent issue closes solely on these results.
