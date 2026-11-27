# Material integration handoff

The goal is nine bounded optical interactions with independent references, ready for the larger 3D stage. The standalone modules are implemented. The stage, capture, sensor, and launcher files remain untouched by this track.

## Runtime files

Include `prototype/shaders/material_models.glsl` after the GLSL version declaration. The include has a guard and no compute layout. Load `prototype/materials/registry.json` for bounds and assumptions. The host must reject inputs outside those bounds before dispatch.

| Effect | Callable | Linear output |
| --- | --- | --- |
| Absorption | `mat_beer(mu_a_m_inv,path_m)` | Transmittance |
| Diffuse | `mat_diffuse(rho_d,irradiance)` | Radiance |
| Glossy | `mat_glossy(rho_s,roughness,n,to_light,to_view)` | BRDF, multiply by incident irradiance |
| Nonbending transmission | `mat_thin_weights(R,T)` | `(R,T,A)` for independent environment/background sampling |
| Refraction | `mat_slab` or `mat_sphere` | Exit ray and accounted energy |
| Fluorescence | `mat_fluorescence` | `(direct detector radiance, converted detector radiance, absorbed excitation)` |
| Phosphorescence | host `emission_state.gd`, then `mat_afterglow_power` if needed | Optical emission power per area, divide by pi for Lambert exit |
| Subsurface | `mat_subsurface_stripe` | Opposite-face radiance in material coordinates |
| Interreflection | host `transport_models.gd` view factor, `mat_indirect_receiver` | Receiver radiance from indirect paths only |

All vectors are unit vectors. Radiometric values share an arbitrary common linear scale, with SI geometry and time. There is no optical floor in these functions. Apply the numerical sensor floor only at the documented sensor boundary.

### Refraction arguments

```text
bool mat_slab(entry, incident, normal_against_ray, thickness_m,
    eta_outside, eta, mu_a_m_inv, out exit_point, out exit_direction, out energy)
bool mat_sphere(origin, incident, center, radius_m,
    eta_outside, eta, mu_a_m_inv, out exit_point, out exit_direction, out energy)
```

`energy` is `(front reflected, primary transmitted, absorbed, untraced internal reflected)`. Its sum is one for a geometric hit. A miss has zero energy. A false return with nonzero energy has no primary transmitted path. Trace the returned exit ray into the actual background. Trace the front reflected ray separately if the stage supports it. Do not relabel the untraced internal-reflection budget as absorption.

### Emission arguments and lifecycle

```text
vec3 mat_fluorescence(E_exc, E_em, absorption_fraction, quantum_yield,
    excitation_nm, emission_nm, detector_excitation, detector_emission)
float mat_population_step(U, absorbed_power, dt_s, lifetime_s, storage_yield)
float mat_afterglow_power(U, lifetime_s, radiative_yield)
```

The preferred persistent state owner is `res://materials/emission_state.gd`. `configure` takes `lifetime_s`, `storage_yield`, and `radiative_yield`. `advance(dt_s, absorbed_power)` takes the excitation held over the interval and returns the new energy and emission. It also returns emitted and heat energy for conservation checks. Use `reset_material()` only for a material/scene reset. A sensor-reference reset and processing changes preserve this state. Pause preserves the simulation time and state.

### Transport arguments and geometry

```text
float mat_subsurface_stripe(x_relative_m, stripe_halfwidth_m,
    deposited_power_per_length, mu_a_m_inv, mu_s_reduced_m_inv, thickness_m)
float mat_square_view_factor(side_m, gap_m, axis_samples)
float mat_indirect_receiver(E_reflector, rho_reflector, rho_receiver,
    F_reflector_to_receiver, F_receiver_to_reflector, bounces)
```

The slab uses the declared fundamental-depth injection approximation. It does not support arbitrary objects. Keep the finite illuminated stripe and opposite-face receiver in the slab's local coordinates. The stripe emits spatially distributed light even with all temporal persistence disabled.

The radiosity scene needs two facing diffuse patches. Only the reflector is directly lit. Put a baffle on the source-to-receiver path while retaining the reflector-to-receiver path. Geometry-derived view factors replace any arbitrary ambient constant. The geometric helper supports equal aligned squares with `gap>=side/2`. Compute the view factor on the host when geometry changes. It is unnecessary to integrate it per pixel.

## Verified standalone scope

Python tests cover optical equations, independent numerical methods, controls, energy, parameter bounds, lifecycle, and ideal events. Surface, emission, and transport JSON reports retain per-effect linear/log/event traces and source hashes. GDScript state and transport tests run headlessly. The coordinator separately runs `res://tests/material_gpu_tests.gd` on a genuine graphics context. Its final source has 36 numerical probes and writes `--report=<path>`.

```powershell
python -m unittest tools.materials.test_surface tools.materials.test_emission tools.materials.test_transport -v
python -m tools.materials.validate_surface --output runs/materials/surface.json
python -m tools.materials.validate_emission --output runs/materials/emission.json
python -m tools.materials.validate_transport --output runs/materials/transport.json
```

The final integrated gate remains open. Record actual stage geometry and camera/light trajectories, spatial sampling convergence, FP32 optical-to-event capture, event-only observations, static-scene behavior, and scoped GPU cost. The isolated CPU single-pixel traces are not substitutes for that run. No issue closes solely on these modules.
