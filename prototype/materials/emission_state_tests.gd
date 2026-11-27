extends SceneTree

const Population = preload("res://materials/emission_state.gd")
var failed := false
var checks := 0

func _check(name: String, passed: bool) -> void:
	checks+=1
	failed=failed or not passed
	print("PASS " if passed else "FAIL ",name)

func _initialize() -> void:
	var population := Population.new()
	_check("Reject invalid tau",not population.configure({"lifetime_s":0.0}))
	_check("Reject unknown key",not population.configure({"sensor_decay":0.2}))
	_check("Configure optical parameters",population.configure({"lifetime_s":0.4,"storage_yield":0.6,"radiative_yield":0.8}))
	var charge: Dictionary = population.advance(0.2,2.0)
	var expected := 0.6*2.0*0.4*(1.0-exp(-0.5))
	_check("Stored energy matches causal convolution",absf(charge.stored_energy-expected)<1e-12)
	_check("Charge energy balance",absf(charge.stored_energy+charge.emitted_energy+charge.heat_energy-0.4)<1e-12)
	population.advance(0.3,0.0)
	_check("Afterglow persists",absf(population.emitted_power()-0.8*expected*exp(-0.75)/0.4)<1e-12)
	var saved: float = population.stored_energy
	population.advance(0.0,100.0)
	_check("Pause preserves energy",population.stored_energy==saved)
	_check("Invalid dt rejected",population.advance(-1.0,1.0).has("error") and population.stored_energy==saved)
	population.reset_material()
	_check("Material reset clears afterglow",population.emitted_power()==0.0)
	population.reset_material(0.6*2.0*0.4)
	for index in range(1000):
		population.advance(0.001,2.0)
	_check("Converged static excitation stable",absf(population.stored_energy-0.48)<1e-12)
	var other := Population.new()
	for power in [1.0,0.0,2.0,0.0]:
		population.reset_material()
		other.reset_material()
		population.advance(0.2,power)
		for index in range(200):
			other.advance(0.001,power)
		_check("Partition invariance power %s" % power,absf(population.stored_energy-other.stored_energy)<1e-12)
	var fluorescence: Dictionary = Population.fluorescence(3.0,0.4,0.8,0.7,405.0,550.0,0.1,0.9)
	_check("Prompt band conversion",absf(fluorescence.converted_emission_power-2.4*0.7*405.0/550.0)<1e-12)
	print("MATERIAL_STATE_RESULT ",JSON.stringify({"passed":not failed,"checks":checks,"scope":"headless GDScript optical state and formulas only"}))
	quit(1 if failed else 0)
