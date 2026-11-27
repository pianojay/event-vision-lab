extends RefCounted

static func parameters(config: Dictionary, t_ns: int, start_ns: int, reset: bool) -> PackedFloat32Array:
	var time := t_ns * 1e-9
	var angle := time * 0.15 * TAU if config.scene == "sphere-light" else 0.0
	var light := Vector3(0,1,-1) + 3.0 * Vector3(sin(angle)*cos(PI/6), sin(PI/6), cos(angle)*cos(PI/6))
	var camera := Vector3(0,1.55,5.1)
	var yaw := 0.0
	if config.scene == "camera-occlusion":
		camera.x = 1.4 * sin(time * 1.5)
		yaw = atan2(-camera.x, 6.1)
	return PackedFloat32Array([
		time, (t_ns-start_ns)*1e-9, float(reset), 0.0,
		config.on_threshold, config.off_threshold, 0.18, 1.0,
		camera.x,camera.y,camera.z,yaw,
		-0.10,config.width,config.height,tan(deg_to_rad(58.0)/2.0),
		0.0,1.0,0.0,5.0,
		2.0,0.0,1.0,0.55,
		light.x,light.y,light.z,float(config.scene == "camera-occlusion")])

static func interaction_parameters(config: Dictionary,t_ns: int,start_ns: int,reset: bool,stage: RefCounted,stimulus: Dictionary = {}) -> PackedFloat32Array:
	var time := t_ns*1e-9
	var focus: int = config.station
	if config.stage_action == "tour": focus = int(time/3.0)%9
	stage.selected = focus
	stage.enabled = true
	stage.treatment = config.treatment
	if config.stage_action == "compare": stage.treatment = config.treatment if time < config.duration_ns*0.5e-9 else not config.treatment
	var c: Vector3 = stage.center(focus)
	var camera := c+(Vector3(2.2,-0.4,2.2) if focus==8 else Vector3(0,0,3.0))
	var yaw := -PI/4.0 if focus==8 else 0.0
	var pitch := 0.0
	if config.stage_action == "camera":
		camera.x += 0.5*sin(time*2.0)
		yaw = atan2(c.x-camera.x,3.0)
	var light := c+Vector3(-1.0,1.5,2.0)
	if config.stage_action == "light": light.x += 1.5*sin(time*3.0)
	var lamp := 0.0 if config.stage_action == "pulse" and time >= config.duration_ns*0.35e-9 else 1.0
	stage.object_offset = 0.25*sin(time*3.0) if config.stage_action == "object" else 0.0
	stage.stripe_offset = 0.2*sin(time*3.0) if config.stage_action == "stripe" else 0.0
	if focus==6 and config.stage_action=="static": lamp=0.0
	if t_ns==0 and config.stage_action=="static": stage.population.reset_material(5.0*lamp*stage.parameters[6][3]*stage.parameters[6][0]*stage.parameters[6][1])
	var excitation := 5.0*lamp if stimulus.get("lamp",true) else 0.0
	if stimulus.get("strobe",false) and fmod(time*float(stimulus.get("frequency",2.0)),1.0)>=0.25: excitation=0.0
	stage.advance(t_ns,excitation)
	var result := PackedFloat32Array([time,(t_ns-start_ns)*1e-9,float(reset),0.0,config.on_threshold,config.off_threshold,0.18,1.0,camera.x,camera.y,camera.z,yaw,pitch,config.width,config.height,tan(deg_to_rad(58.0)/2.0),0.0,lamp,0.0,5.0,2.0,0.0,0.0,0.55,light.x,light.y,light.z,0.0])
	result.append_array(stage.packed())
	return result
