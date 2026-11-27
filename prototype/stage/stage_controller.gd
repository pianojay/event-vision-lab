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
