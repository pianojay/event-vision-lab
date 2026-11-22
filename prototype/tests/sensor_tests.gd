extends SceneTree

const SensorKernel = preload("res://sensor_gpu.gd")
var device: RenderingDevice
var kernel: RefCounted
var checks: Array = []
var failed := false

func _initialize() -> void:
	call_deferred("_run")

func _parameters(time: float, intensity: float, reset: bool = false, world: bool = false, lamp: bool = true, strobe: bool = false, motion: float = 0.0) -> PackedFloat32Array:
	return PackedFloat32Array([
		time, 1.0, float(reset), 0.0 if world else 1.0,
		0.25, 0.25, 0.2, intensity,
		0.0, 1.55, 5.1, 0.0,
		-0.10, kernel.size.x, kernel.size.y, tan(deg_to_rad(58.0) / 2.0),
		motion, float(lamp), float(strobe), 5.0,
		2.0, 0.0, 0.0, 0.55,
		1.6, 3.0, 1.2, 0.0])

func _step(parameters: PackedFloat32Array) -> PackedFloat32Array:
	kernel.dispatch([parameters])
	device.submit()
	device.sync()
	return kernel.read_events()

func _check(name: String, passed: bool, details: Variant = null) -> void:
	checks.append({"name": name, "passed": passed, "details": details})
	if not passed: failed = true
	print("PASS " if passed else "FAIL ", name, " ", details)

func _sum(values: PackedFloat32Array) -> float:
	var total := 0.0
	for i in range(0, values.size(), 4):
		total += values[i] + values[i + 1]
	return total

func _active_parameters(time: float, light: Vector3, albedo: float = 0.55, reset: bool = false) -> PackedFloat32Array:
	var params := _parameters(time, 1.0, reset, true)
	params[22] = 1.0
	params[23] = albedo
	params[24] = light.x
	params[25] = light.y
	params[26] = light.z
	return params

func _active_lighting_checks() -> void:
	var left := Vector3(-2, 3, 2)
	var right := Vector3(2, 3, 2)
	_step(_active_parameters(0, left, 0.55, true))
	var first: PackedFloat32Array = kernel.read_radiance()
	var events := _step(_active_parameters(0.01, left))
	_check("static matte sphere and fixed light are silent", _sum(events) == 0)
	events = _step(_active_parameters(0.02, right))
	var on_sum := 0.0
	var off_sum := 0.0
	var min_count := 1e9
	var max_count := 0.0
	for i in range(0, events.size(), 4):
		on_sum += events[i]
		off_sum += events[i + 1]
		if events[i] + events[i + 1] > 0:
			min_count = minf(min_count, events[i] + events[i + 1])
			max_count = maxf(max_count, events[i] + events[i + 1])
	_check("changing light direction generates both polarities", on_sum > 100 and off_sum > 100, [on_sum, off_sum])
	_check("surface response varies spatially", max_count > min_count, [min_count, max_count])
	# Independently predict irradiance at a known camera ray on the sphere.
	var x := 120
	var y := 90
	var pitch := -0.10
	var forward := Vector3(0, sin(pitch), -cos(pitch))
	var up := Vector3(0, cos(pitch), sin(pitch))
	var sx := (x + 0.5) / 240.0 * 2.0 - 1.0
	var sy := 1.0 - (y + 0.5) / 180.0 * 2.0
	var ray := (forward + Vector3.RIGHT * sx * (4.0 / 3.0) * tan(deg_to_rad(29.0)) + up * sy * tan(deg_to_rad(29.0))).normalized()
	var origin := Vector3(0, 1.55, 5.1)
	var oc := origin - Vector3(0, 1, -1)
	var b := oc.dot(ray)
	var distance := -b - sqrt(b * b - (oc.length_squared() - 1.0))
	var hit := origin + ray * distance
	var normal := (hit - Vector3(0, 1, -1)).normalized()
	var to_light := left - hit
	var expected := 0.55 * (0.035 + 5.0 * maxf(normal.dot(to_light.normalized()), 0.0) * 6.0 / (to_light.length_squared() + 1.0))
	var measured := first[(y * 240 + x) * 4]
	_check("matte irradiance matches analytic cosine and distance", absf(measured - expected) < 0.0001, {"expected": expected, "measured": measured})
	# Ideal diffuse albedo cancellation is a prediction, not a black-material heuristic.
	_step(_active_parameters(0, left, 0.1, true))
	var dark_events := _step(_active_parameters(0.01, right, 0.1))
	_step(_active_parameters(0, left, 0.8, true))
	var bright_events := _step(_active_parameters(0.01, right, 0.8))
	var mismatches := 0
	for i in range(0, bright_events.size(), 4):
		if bright_events[i] != dark_events[i] or bright_events[i + 1] != dark_events[i + 1]: mismatches += 1
	_check("ideal diffuse event counts are albedo invariant", mismatches == 0, mismatches)
	var dt := 1.0 / 120.0
	var reset := _parameters(0, 1, true)
	var batch := [_parameters(dt, exp(0.625)), _parameters(2 * dt, exp(0.625)), _parameters(3 * dt, exp(0.875)), _parameters(4 * dt, exp(0.875))]
	for params: PackedFloat32Array in batch: params[1] = dt
	_step(reset)
	kernel.dispatch(batch)
	device.submit()
	device.sync()
	var grouped: PackedFloat32Array = kernel.read_activity()
	var expected_history := 2.0 * exp(-3.0 * dt / 0.2) + exp(-dt / 0.2)
	_check("activity retains bursts before final zero-event substep", absf(grouped[0] - expected_history) < 0.0001 and grouped[2] == 3, {"expected": expected_history, "measured": grouped[0], "total_ON": grouped[2]})
	_step(reset)
	for params: PackedFloat32Array in batch: _step(params)
	var serial: PackedFloat32Array = kernel.read_activity()
	_check("activity independent of display batching", absf(serial[0] - grouped[0]) < 0.0001 and serial[2] == grouped[2])
	var off_params := _parameters(5 * dt, 1)
	off_params[1] = dt
	_step(off_params)
	off_params[0] = 6 * dt
	_step(off_params)
	var off_history: PackedFloat32Array = kernel.read_activity()
	_check("OFF history survives later silent substep", absf(off_history[1] - 3.0 * exp(-dt / 0.2)) < 0.0001 and off_history[3] == 3)
	_step(reset)
	var cleared: PackedFloat32Array = kernel.read_activity()
	_check("reset clears activity and diagnostic totals", cleared[0] == 0 and cleared[1] == 0 and cleared[2] == 0 and cleared[3] == 0)

func _run() -> void:
	device = RenderingServer.create_local_rendering_device()
	if device == null:
		push_error("GPU device unavailable: tests require a real renderer, not --headless.")
		quit(1)
		return
	kernel = SensorKernel.new()
	if not kernel.initialize(device, Vector2i(8, 8)):
		push_error(kernel.error)
		quit(1)
		return
	var values := _step(_parameters(0, 1, true))
	_check("initialization has no false flash", _sum(values) == 0)
	values = _step(_parameters(1, 1))
	_check("constant intensity produces zero events", _sum(values) == 0)
	values = _step(_parameters(2, exp(0.625)))
	_check("multiple ON crossings", values[0] == 2 and values[1] == 0, values[0])
	_check("last crossing timestamp interpolated", abs(values[2] - 1.8) < 0.0001, values[2])
	var state: PackedFloat32Array = kernel.read_state()
	_check("subthreshold residual retained", abs(state[0] - 0.5) < 0.0001, state[0])
	values = _step(_parameters(3, exp(0.875)))
	_check("residual contributes to next crossing", values[0] == 1, values[0])
	values = _step(_parameters(4, 1))
	_check("multiple OFF crossings", values[1] == 3 and values[0] == 0, values[1])
	_step(_parameters(0, 1, true))
	var asymmetric := _parameters(1, exp(0.55))
	asymmetric[4] = 0.2
	asymmetric[5] = 0.3
	values = _step(asymmetric)
	_check("independent ON threshold", values[0] == 2, values[0])
	asymmetric = _parameters(2, 1)
	asymmetric[4] = 0.2
	asymmetric[5] = 0.3
	values = _step(asymmetric)
	_check("independent OFF threshold", values[1] == 1, values[1])
	_step(_parameters(0, 0.00001, true))
	values = _step(_parameters(1, 0.00001 * exp(0.625)))
	_check("linear low-light input survives FP32 path", values[0] == 2, values[0])
	kernel.cleanup()
	kernel = SensorKernel.new()
	if not kernel.initialize(device, Vector2i(240, 180)):
		push_error(kernel.error)
		quit(1)
		return
	_step(_parameters(0, 1, true, true))
	values = _step(_parameters(1, 1, false, true))
	_check("rendered static world produces zero events", _sum(values) == 0, _sum(values))
	values = _step(_parameters(2, 1, false, true, false))
	_check("stationary world responds to illumination only", _sum(values) > 1000, _sum(values))
	_step(_parameters(0, 1, true, true))
	values = _step(_parameters(1, 1, false, true, true, false, 1.5))
	_check("object motion generates events", _sum(values) > 100, _sum(values))
	_step(_parameters(0, 1, true, true, true, true))
	values = _step(_parameters(0.5, 1, false, true, true, true))
	_check("endpoint sampling misses intervening strobe", _sum(values) == 0, _sum(values))
	values = _step(_parameters(0.75, 1, false, true, true, true))
	_check("sampling during strobe OFF captures change", _sum(values) > 1000, _sum(values))
	values = _step(_parameters(1.0, 1, false, true, true, true))
	_check("sampling next strobe ON captures change", _sum(values) > 1000, _sum(values))
	_active_lighting_checks()
	# Measure the actual analytic-world + sensor kernel, not a CPU surrogate.
	var latencies: Array[float] = []
	for i in range(160):
		var start := Time.get_ticks_usec()
		kernel.dispatch([_parameters(i / 120.0, 1, i == 0, true, true, true, i / 120.0)])
		device.submit()
		device.sync()
		if i >= 40: latencies.append((Time.get_ticks_usec() - start) / 1000.0)
	latencies.sort()
	var report := {
		"godot": Engine.get_version_info().string,
		"adapter": RenderingServer.get_video_adapter_name(),
		"sensor_size": [240, 180],
		"checks": checks,
		"passed": not failed,
		"kernel_sync_median_ms": latencies[latencies.size() / 2],
		"kernel_sync_p95_ms": latencies[floori((latencies.size() - 1) * 0.95)],
		"timing_scope": "Local GPU device, analytic linear scene plus ideal sensor, submit and sync per sample, 40 warmup / 120 timed samples. Includes CPU submission/synchronization. Excludes UI, inference, streaming and packed event output."
	}
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report="):
			var file := FileAccess.open(arg.trim_prefix("--report="), FileAccess.WRITE)
			if file: file.store_string(JSON.stringify(report, "\t"))
	print("EVENT_SENSOR_TEST_REPORT ", JSON.stringify(report))
	kernel.cleanup()
	device.free()
	quit(1 if failed else 0)
