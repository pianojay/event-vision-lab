# Bounded material model reference

These modules implement isolated optical interactions for #17 through #25 under #6. They do not establish camera calibration or complete the larger-stage acceptance criteria.

`prototype/materials/registry.json` owns the model names, parameter units, bounds, and missing physics. Python APIs live in `tools/materials`. GPU-compatible pure functions live in `prototype/shaders/material_models.glsl`. The caller validates the registry bounds before dispatch and supplies unit vectors. Each output is linear radiance before any logarithm, numerical floor, sensor response, or display processing.

## Surface and transmission

`surface.py` has immutable `Surface(rho_d, rho_s, roughness)`, `Medium(mu_a_m_inv, eta, eta_outside)`, and `ThinPane(reflection, transmission)` inputs. Lengths are metres. The common radiometric scale is arbitrary, with consistent energy ratios. `point_irradiance` uses cosine divided by squared distance, without ambient or softened distance. `diffuse` returns `rho_d*E/pi`.

`glossy` returns a reciprocal cosine-power BRDF. The exponent is `s=2/roughness^2-2`. The normalization `(s+1)/(2*pi)` is conservative because the projected hemisphere integral cannot exceed the complete unprojected lobe integral. `rho_d+rho_s<=1` bounds the combined reflection. Roughness is a lobe-width control, not measured microgeometry. There is no glossy Fresnel factor or exact mirror delta. Narrow highlights need temporal and spatial convergence checks.

Beer-Lambert attenuation is `exp(-mu_a*path)`. The absorption coefficient is separate from opaque diffuse reflectance. `ThinPane` has nonbending optical transmission, with `R+T+A=1`. Its output combines background and reflected-environment radiance, rather than display alpha.

`slab` and `sphere` trace the primary transmitted ray with Snell directions, unpolarized Fresnel reflection, and absorption along the interior path. The slab input is a point on its front plane and a normal against the incoming ray. Its rear plane is displaced by `-normal*thickness`. The sphere requires an external ray origin. Returned `RayPath` includes the exit point and direction, path length, front reflection, primary transmission, absorption, and internal-reflected energy. The last component is accounted but not traced. It is not called absorption. Total internal reflection terminates the primary path. Geometric misses return `None` in Python and zero energy in GLSL. Caustics, dispersion, polarization state, and internal reflection paths are unsupported.

The GLSL names are `mat_beer`, `mat_diffuse`, `mat_glossy`, `mat_thin_weights`, `mat_fresnel`, `mat_refract`, `mat_slab`, and `mat_sphere`. `mat_slab` and `mat_sphere` return a Boolean and write exit point, exit direction, and `vec4` energy in the order `(front reflected, primary transmitted, absorbed, internal reflected)`. A false return with nonzero energy is a terminated optical path. Sample the actual background along the returned ray, then apply primary transmission. A reflected environment can be evaluated separately with the front-reflection weight.

## Evidence commands

Run from the repository root.

```powershell
python -m unittest tools.materials.test_surface -v
python -m tools.materials.validate_surface --output docs/research/materials/evidence/surface.json
```

The report retains optical FP32 samples, log values and differences, timestamped ideal events, controls, independent reference traces, temporal sampling sweeps, static-event counts, and source SHA-256 hashes. Event calculations use the existing `SampledPixel` without changing it. The sensor alone clamps at `1e-6`; optical zero remains zero. Exact multiplicative albedo cancels in ideal log contrast. An additive background changes that result. No expectation requires darker materials to emit fewer ideal events.

Independent checks include numerical integration of attenuation, scalar trigonometric ray geometry, hemisphere BRDF quadrature, energy balance, controls, and ideal-event comparisons. The runtime GLSL requires a separate genuine-GPU execution check. A headless import does not satisfy that check. CPU timings cover only model calls and carry no claim about integrated stage speed.

## Pinned primary references

The equation and terminology references were accessed on 2026-11-28. They are edition-pinned chapters or stable term identifiers. Local implementation hashes are recorded in every evidence report. No copied reference implementation is used.

- [PBRT fourth edition, transmittance](https://www.pbr-book.org/4ed/Volume_Scattering/Transmittance), homogeneous attenuation differential equation and multiplicativity.
- [PBRT fourth edition, diffuse reflection](https://www.pbr-book.org/4ed/Reflection_Models/Diffuse_Reflection), Lambertian normalization.
- [PBRT fourth edition, specular reflection and transmission](https://www.pbr-book.org/4ed/Reflection_Models/Specular_Reflection_and_Transmission), Snell directions, dielectric Fresnel, and total internal reflection. The bounded glossy lobe here is an explicitly derived approximation, not PBRT's microfacet model.
- [PBRT third edition, subsurface diffusion](https://www.pbr-book.org/3ed-2018/Light_Transport_II_Volume_Rendering/Subsurface_Scattering_Using_the_Diffusion_Equation), diffusion assumptions and reduced scattering. The finite-slab source and boundary solution here differ from PBRT's semi-infinite photon-beam diffusion.
- [PBRT fourth edition, light transport equation](https://www.pbr-book.org/4ed/Light_Transport_I_Surface_Reflection/The_Light_Transport_Equation), energy balance, geometric coupling, and the multiple-reflection series.
- IUPAC stable terms [fluorescence F02453](https://goldbook.iupac.org/terms/view/F02453), [phosphorescence P04569](https://goldbook.iupac.org/terms/view/P04569), and [excitation-emission spectrum E02249](https://goldbook.iupac.org/terms/view/E02249). Direct retrieval returned HTTP 403 in this run. These are issue-supplied terminology pointers, not evidence for fitted material constants.

## Excitation and emission

`Fluorophore` describes two narrow bands, by default 405 nm excitation and 550 nm emission. `evaluate(E_excitation, E_emission_band)` returns separate absorbed, converted, direct, heat, and detector components. Nonabsorbed illumination is reflected diffusely from the one-sided sheet. Conversion uses photon yield times `lambda_excitation/lambda_emission`; the wavelength ratio keeps the radiant-energy budget bounded. The detector has an explicit sensitivity for each band. Emission-band illumination does not excite the material. Response is instantaneous at the simulation cadence. No artificial visible delay or material calibration is implied.

`Population(Phosphor(lifetime_s, storage_yield, radiative_yield))` owns stored energy per area. `advance(dt_s, absorbed_power)` integrates constant absorbed excitation exactly over that interval. Its equation is `dU/dt=storage_yield*P_abs-U/tau`; emitted power is `radiative_yield*U/tau`. The model assumes a metastable reservoir and omits saturation and multistate kinetics. The fluorescence/phosphorescence distinction is an assumed physical mechanism, not a numerical lifetime cutoff.

The GDScript state owner is `res://materials/emission_state.gd`. Its APIs are `configure(Dictionary)->bool`, `advance(dt_s, absorbed_power)->Dictionary`, `emitted_power()->float`, and `reset_material(initial_energy=0)->bool`. Configure preserves energy. A scene reset calls `reset_material`; a sensor reset does not. Pause either skips advancement or uses zero dt. Static-scene evidence uses the equilibrium reservoir under constant excitation. Decaying emission after source shutdown is real model activity.

GLSL exposes `mat_fluorescence(E_exc, E_em, absorption_fraction, quantum_yield, excitation_nm, emission_nm, detector_excitation, detector_emission)->vec3(direct_detector, converted_detector, absorbed_power)`. `mat_population_step(U, P_abs, dt_s, tau, storage_yield)` and `mat_afterglow_power(U,tau,radiative_yield)` are stateless helpers. The host owns persistent energy and passes the emission to the optical stage. Shader inputs obey the registry bounds.

```powershell
python -m unittest tools.materials.test_emission -v
python -m tools.materials.validate_emission --output docs/research/materials/evidence/emission.json
& 'C:/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe' --headless --path prototype --script materials/emission_state_tests.gd
```

The independent references count photons with Planck's relation and integrate the causal excitation convolution with Simpson quadrature. RK4 tests check the population ODE. The report retains separate spectral components, nonexciting-band controls, repeated pulses, lifetime and cadence sweeps, energy budgets, and material-reset checks. `prototype/tests/material_gpu_tests.gd` adds actual GLSL probes for both mechanisms. Its `--report=<path>` or `--output=<path>` user argument exports JSON after a genuine GPU run.
