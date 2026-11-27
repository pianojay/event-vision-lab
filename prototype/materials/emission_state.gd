extends RefCounted

# Optical state only. The acquisition owner calls reset_material on scene reset.
# Sensor reset, display decay changes, and pause do not call reset_material.
var lifetime_s: float = 0.4
var storage_yield: float = 0.6
var radiative_yield: float = 0.8
var stored_energy: float = 0.0

func configure(parameters: Dictionary) -> bool:
	for key in parameters:
		if key not in ["lifetime_s","storage_yield","radiative_yield"]:
			return false
	var tau: float = parameters.get("lifetime_s",0.4)
	var storage: float = parameters.get("storage_yield",0.6)
	var radiative: float = parameters.get("radiative_yield",0.8)
	if not is_finite(tau) or tau < 0.0001 or tau > 1000.0:
		return false
	if not is_finite(storage) or storage < 0.0 or storage > 1.0:
		return false
	if not is_finite(radiative) or radiative < 0.0 or radiative > 1.0:
		return false
	lifetime_s=tau
	storage_yield=storage
	radiative_yield=radiative
	return true

func reset_material(initial_energy: float = 0.0) -> bool:
	if not is_finite(initial_energy) or initial_energy < 0.0 or initial_energy > 1e20:
		return false
	stored_energy=initial_energy
	return true

func emitted_power() -> float:
	return radiative_yield*stored_energy/lifetime_s

func advance(dt_s: float, absorbed_power: float) -> Dictionary:
	if not is_finite(dt_s) or dt_s < 0.0 or dt_s > 10000.0:
		return {"error":"dt_s outside [0,10000]"}
	if not is_finite(absorbed_power) or absorbed_power < 0.0 or absorbed_power > 1e20:
		return {"error":"absorbed_power outside [0,1e20]"}
	var x := dt_s/lifetime_s
	# Stable 1-exp(-x) for very small timesteps, including pause dt=0.
	var uptake := x*(1.0-x*0.5+x*x/6.0) if x < 0.001 else 1.0-exp(-x)
	var previous := stored_energy
	stored_energy=previous*exp(-x)+storage_yield*absorbed_power*lifetime_s*uptake
	var released := maxf(0.0,previous+storage_yield*absorbed_power*dt_s-stored_energy)
	return {"stored_energy":stored_energy,"emitted_power":emitted_power(),
		"emitted_energy":radiative_yield*released,
		"heat_energy":(1.0-storage_yield)*absorbed_power*dt_s+(1.0-radiative_yield)*released}

static func fluorescence(excitation_irradiance: float, emission_band_irradiance: float,
		absorption_fraction: float, quantum_yield: float, excitation_nm: float, emission_nm: float,
		detector_excitation: float, detector_emission: float) -> Dictionary:
	var absorbed := absorption_fraction*excitation_irradiance
	var converted := absorbed*quantum_yield*excitation_nm/emission_nm
	var direct := (detector_excitation*(excitation_irradiance-absorbed)+detector_emission*emission_band_irradiance)/PI
	var emission := detector_emission*converted/PI
	return {"absorbed_power":absorbed,"converted_emission_power":converted,
		"direct_detector_radiance":direct,"converted_detector_radiance":emission,
		"detector_radiance":direct+emission,"heat_power":absorbed-converted}
