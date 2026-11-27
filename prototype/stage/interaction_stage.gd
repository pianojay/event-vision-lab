extends RefCounted
const Emission = preload("res://materials/emission_state.gd")
const Transport = preload("res://materials/transport_models.gd")
const IDS = ["absorption", "diffuse", "glossy", "transmission", "refraction", "fluorescence", "phosphorescence", "subsurface", "interreflection"]
# Each station has four optical parameters. Positions are fixed metre-valued geometry.
const DEFAULTS = [[2.0,0.3,0.0,0.0],[0.55,0.0,0.0,0.0],[0.15,0.65,0.3,0.0],[0.15,0.7,0.0,0.0],[1.5,0.2,0.1,0.0],[0.8,0.7,450.0,550.0],[0.4,0.6,0.8,0.8],[0.1,100.0,0.2,0.04],[0.7,0.6,1.2,16.0]]
const KEYS = [["mu_a_m_inv","path_m"],["rho_d"],["rho_d","rho_s","roughness"],["reflection","transmission"],["eta","thickness_m","mu_a_m_inv"],["absorption_fraction","quantum_yield","excitation_nm","emission_nm"],["lifetime_s","storage_yield","radiative_yield","absorption_fraction"],["mu_a_m_inv","mu_s_reduced_m_inv","thickness_m","stripe_halfwidth_m"],["reflectance","reflectance","gap_m","bounce_count"]]
const PRIMARY_INDEX = [0,0,2,1,0,1,0,2,0]
const PRIMARY_RANGE = [[0.0,8.0],[0.05,0.95],[0.1,1.0],[0.0,0.85],[0.8,2.5],[0.0,1.0],[0.05,2.0],[0.1,0.5],[0.0,0.95]]
var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://materials/registry.json"))
var parameters: Array = DEFAULTS.duplicate(true)
var population = Emission.new()
var enabled := false
var selected := 0
var treatment := true
var object_offset := 0.0
var stripe_offset := 0.0
var excitation_band := 1.0
var truth_component := 0
var previous_absorbed_power := 0.0
var material_clock_ns := 0
var view_factor := Transport.square_view_factor(1.0,1.2,64)

static func center(index: int) -> Vector3:
	return Vector3((index % 3 - 1)*3.0, 6.0-floori(float(index)/3.0)*2.5, -3.0)

func focus(index: int) -> Vector3:
	selected = clampi(index,0,8)
	return center(selected)+(Vector3(2.2,-0.4,2.2) if selected==8 else Vector3(0,0,3.0))

func reset_material() -> void:
	parameters = DEFAULTS.duplicate(true)
	population.configure({"lifetime_s":parameters[6][0],"storage_yield":parameters[6][1],"radiative_yield":parameters[6][2]})
	population.reset_material()
	previous_absorbed_power = 0.0
	object_offset = 0.0
	stripe_offset = 0.0
	treatment = true

func advance(t_ns: int, lamp_power: float) -> void:
	assert(t_ns >= material_clock_ns)
	population.advance((t_ns-material_clock_ns)*1e-9,previous_absorbed_power)
	material_clock_ns = t_ns
	# The phosphor uses a uniform rear excitation source, held over each interval.
	previous_absorbed_power = lamp_power*parameters[6][3]*excitation_band

func packed() -> PackedFloat32Array:
	var result := PackedFloat32Array([float(enabled),float(selected),float(treatment),float(truth_component),object_offset,stripe_offset,population.emitted_power(),excitation_band,view_factor,1.0,1.2,0.0])
	for station in parameters: result.append_array(PackedFloat32Array(station))
	return result

func metadata() -> Dictionary:
	return {"schema":"event-lab-interaction-stage-v1","station":IDS[selected],"enabled":enabled,"treatment":treatment,"parameters":parameters.duplicate(true),"object_offset_m":object_offset,"stripe_offset_m":stripe_offset,"excitation_overlap":excitation_band,"truth_component":truth_component,"population_energy":population.stored_energy,"material_clock_ns":material_clock_ns,"view_factor":view_factor,"registry":registry,"reset_policy":"sensor reset preserves material; material reset clears population and restores station parameters","geometry":"3 by 3 stations, centres x=(-3,0,3), y=(6,3.5,1), z=-3 metres; background z=-5; interreflection equal horizontal 1m squares gap1.2m"}

func reset_station(index: int) -> void:
	parameters[index] = DEFAULTS[index].duplicate()
	if index==6:
		population.configure({"lifetime_s":parameters[6][0],"storage_yield":parameters[6][1],"radiative_yield":parameters[6][2]})
		population.reset_material()
		previous_absorbed_power = 0.0
	treatment = true

func restore(settings: Dictionary) -> bool:
	if not settings.has_all(["station","parameters","treatment"]): return false
	var index := IDS.find(settings.station)
	if index<0 or not settings.parameters is Array or settings.parameters.size()!=9: return false
	# Validate each named optical parameter against its registry and coupled constraints.
	for i in 9:
		if not settings.parameters[i] is Array or settings.parameters[i].size()!=4: return false
	if not valid_parameters(settings.parameters): return false
	parameters = settings.parameters.duplicate(true)
	population.configure({"lifetime_s":parameters[6][0],"storage_yield":parameters[6][1],"radiative_yield":parameters[6][2]})
	selected = index
	treatment = bool(settings.treatment)
	enabled = bool(settings.get("enabled",true))
	object_offset = clampf(float(settings.get("object_offset_m",0)),-0.5,0.5)
	stripe_offset = clampf(float(settings.get("stripe_offset_m",0)),-0.5,0.5)
	excitation_band = clampf(float(settings.get("excitation_overlap",1)),0,1)
	return true

func valid_parameters(values: Array) -> bool:
	if values.size()!=9: return false
	for i in 9:
		if not values[i] is Array or values[i].size()!=4: return false
		var model: Dictionary = {}
		for candidate in registry.models:
			if candidate.id==IDS[i]: model=candidate
		for j in 4:
			if typeof(values[i][j]) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(values[i][j]): return false
			if j>=KEYS[i].size(): continue
			var key: String = KEYS[i][j]
			var bounds: Array = model.parameters.get(key,[0.0,1.0])
			if key=="gap_m": bounds=[1.2,1.2]
			if values[i][j]<bounds[0] or values[i][j]>bounds[1]: return false
	if values[2][0]+values[2][1]>1 or values[3][0]+values[3][1]>1: return false
	if values[5][3]<values[5][2]: return false
	var slab: Array = values[7]
	if slab[1]<10*slab[0] or slab[2]*(slab[0]+slab[1])<10 or slab[3]*(slab[0]+slab[1])<3: return false
	if values[8][3]!=int(values[8][3]): return false
	return true

func set_primary(value: float) -> bool:
	var next := parameters.duplicate(true)
	next[selected][PRIMARY_INDEX[selected]] = value
	if not valid_parameters(next): return false
	parameters = next
	if selected==6: population.configure({"lifetime_s":parameters[6][0],"storage_yield":parameters[6][1],"radiative_yield":parameters[6][2]})
	return true
