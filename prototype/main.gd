extends Control

const SensorKernel = preload("res://sensor_gpu.gd")
const SENSOR_SIZE := Vector2i(240, 180)
const SAMPLE_HZ := 120.0
const MAX_STEPS := 8

var kernel: RefCounted
var event_texture: Texture2DRD
var scene_texture: Texture2DRD
var display_material: ShaderMaterial
var canvas: ColorRect
var status: Label
var threshold_label: Label
var persistence_label: Label
var frequency_label: Label
var mode_select: OptionButton
var motion_check: CheckBox
var lamp_check: CheckBox
var strobe_check: CheckBox
var panel_check: CheckBox
var ready_gpu := false
var needs_reset := true
var simulation_time := 0.0
var last_sample_time := 0.0
var accumulator := 0.0
var motion_phase := 0.0
var panel_phase := 0.0
var skipped := 0
var skipped_after_warmup := 0
var sample_count := 0
var threshold := 0.2
var persistence := 0.18
var frequency := 2.0
var strength := 5.0
var camera_position := Vector3(0, 1.55, 5.1)
var previous_camera := Vector3(0, 1.55, 5.1)
var yaw := 0.0
var pitch := -0.10
var previous_yaw := 0.0
var previous_pitch := -0.10
var elapsed := 0.0
var elapsed_wall := 0.0
var wall_start_usec := 0
var previous_frame_usec := 0
var report_after := 0.0
var report_path := ""
var capture_path := ""
var initial_view := 0
var frame_times: Array[float] = []

func _ready() -> void:
	Engine.max_fps = 60
	_build_ui()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--duration="):
			report_after = arg.trim_prefix("--duration=").to_float()
		elif arg.begins_with("--report="):
			report_path = arg.trim_prefix("--report=")
		elif arg.begins_with("--capture="):
			capture_path = arg.trim_prefix("--capture=")
		elif arg.begins_with("--view="):
			initial_view = clampi(arg.trim_prefix("--view=").to_int(), 0, 2)
	mode_select.select(initial_view)
	_set_mode(initial_view)
	RenderingServer.call_on_render_thread(_initialize_gpu)

func _initialize_gpu() -> void:
	var device := RenderingServer.get_rendering_device()
	if device == null:
		call_deferred("_gpu_failed", "RenderingDevice unavailable. Use the Mobile renderer with Vulkan or D3D12.")
		return
	kernel = SensorKernel.new()
	if not kernel.initialize(device, SENSOR_SIZE):
		call_deferred("_gpu_failed", kernel.error)
		return
	event_texture = Texture2DRD.new()
	event_texture.texture_rd_rid = kernel.events
	scene_texture = Texture2DRD.new()
	scene_texture.texture_rd_rid = kernel.radiance
	call_deferred("_gpu_ready")

func _gpu_failed(message: String) -> void:
	status.text = "GPU setup failed: " + message
	push_error(message)
	if report_after > 0:
		get_tree().quit(1)

func _gpu_ready() -> void:
	display_material.set_shader_parameter("event_texture", event_texture)
	display_material.set_shader_parameter("scene_texture", scene_texture)
	ready_gpu = true
	wall_start_usec = Time.get_ticks_usec()
	previous_frame_usec = wall_start_usec
	print("EVENT_LAB_READY adapter=", RenderingServer.get_video_adapter_name(), " sensor=", SENSOR_SIZE, " target_hz=", SAMPLE_HZ)

func _process(delta: float) -> void:
	if not ready_gpu:
		return
	var now_usec := Time.get_ticks_usec()
	var frame_ms := (now_usec - previous_frame_usec) / 1000.0
	previous_frame_usec = now_usec
	elapsed_wall = (now_usec - wall_start_usec) / 1000000.0
	elapsed += delta
	if elapsed_wall > 2.0:
		frame_times.append(frame_ms)
	_move_camera(delta)
	accumulator += delta
	var due := floori(accumulator * SAMPLE_HZ)
	if due > MAX_STEPS:
		var missed := due - MAX_STEPS
		skipped += missed
		if elapsed_wall > 2.0: skipped_after_warmup += missed
		simulation_time += missed / SAMPLE_HZ
		if motion_check.button_pressed: motion_phase += missed / SAMPLE_HZ
		if panel_check.button_pressed: panel_phase += missed / SAMPLE_HZ
		accumulator -= missed / SAMPLE_HZ
		due = MAX_STEPS
	var parameters: Array = []
	for i in range(due):
		var dt := 1.0 / SAMPLE_HZ
		simulation_time += dt
		accumulator -= dt
		if motion_check.button_pressed:
			motion_phase += dt
		if panel_check.button_pressed:
			panel_phase += dt
		var alpha := float(i + 1) / float(due)
		var position := previous_camera.lerp(camera_position, alpha)
		parameters.append(PackedFloat32Array([
			simulation_time, simulation_time - last_sample_time, float(needs_reset), 0.0,
			threshold, threshold, 0.0, 1.0,
			position.x, position.y, position.z, lerpf(previous_yaw, yaw, alpha),
			lerpf(previous_pitch, pitch, alpha), SENSOR_SIZE.x, SENSOR_SIZE.y, tan(deg_to_rad(58.0) / 2.0),
			motion_phase, float(lamp_check.button_pressed), float(strobe_check.button_pressed), strength,
			frequency, panel_phase, 0.0, 0.0]))
		needs_reset = false
		last_sample_time = simulation_time
		sample_count += 1
	if not parameters.is_empty():
		RenderingServer.call_on_render_thread(_render_samples.bind(parameters))
		previous_camera = camera_position
		previous_yaw = yaw
		previous_pitch = pitch
	display_material.set_shader_parameter("sample_time", simulation_time)
	display_material.set_shader_parameter("display_interval", maxf(delta, 1.0 / SAMPLE_HZ) + 0.001)
	status.text = "%s  |  %d FPS  |  %d x %d / %.0f Hz target  |  skipped %d" % [RenderingServer.get_video_adapter_name(), Engine.get_frames_per_second(), SENSOR_SIZE.x, SENSOR_SIZE.y, SAMPLE_HZ, skipped]
	if report_after > 0.0 and elapsed_wall >= report_after:
		report_after = 0.0
		_finish_profile()

func _finish_profile() -> void:
	set_process(false)
	await RenderingServer.frame_post_draw
	if not capture_path.is_empty():
		var result := get_viewport().get_texture().get_image().save_png(capture_path)
		print("EVENT_LAB_CAPTURE ", result, " ", capture_path)
	_write_report()
	get_tree().quit()

func _render_samples(parameters: Array) -> void:
	kernel.dispatch(parameters)

func _move_camera(delta: float) -> void:
	var direction := Vector3.ZERO
	var forward := Vector3(sin(yaw), 0, -cos(yaw))
	var right := Vector3(cos(yaw), 0, sin(yaw))
	if Input.is_physical_key_pressed(KEY_W): direction += forward
	if Input.is_physical_key_pressed(KEY_S): direction -= forward
	if Input.is_physical_key_pressed(KEY_D): direction += right
	if Input.is_physical_key_pressed(KEY_A): direction -= right
	if Input.is_physical_key_pressed(KEY_Q): direction.y -= 1
	if Input.is_physical_key_pressed(KEY_E): direction.y += 1
	camera_position += direction.normalized() * delta * 1.7
	camera_position.x = clampf(camera_position.x, -4.6, 4.6)
	camera_position.y = clampf(camera_position.y, 0.3, 3.6)
	camera_position.z = clampf(camera_position.z, -4.6, 5.5)
	if Input.is_physical_key_pressed(KEY_LEFT): yaw -= delta * 0.7
	if Input.is_physical_key_pressed(KEY_RIGHT): yaw += delta * 0.7
	if Input.is_physical_key_pressed(KEY_UP): pitch = minf(pitch + delta * 0.5, 0.9)
	if Input.is_physical_key_pressed(KEY_DOWN): pitch = maxf(pitch - delta * 0.5, -0.9)

func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		if canvas.get_global_rect().has_point(get_global_mouse_position()):
			yaw += event.relative.x * 0.004
			pitch = clampf(pitch - event.relative.y * 0.004, -0.9, 0.9)
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_1: _preset(0)
			KEY_2: _preset(1)
			KEY_3: _preset(2)
			KEY_R: needs_reset = true
			KEY_V:
				mode_select.select((mode_select.selected + 1) % 3)
				_set_mode(mode_select.selected)
			KEY_T: strobe_check.button_pressed = not strobe_check.button_pressed

func _preset(which: int) -> void:
	motion_check.button_pressed = which == 2
	lamp_check.button_pressed = true
	strobe_check.button_pressed = which == 1
	panel_check.button_pressed = false
	needs_reset = true

func _set_mode(index: int) -> void:
	display_material.set_shader_parameter("representation", index)

func _label(text: String, font_size: int = 15, color: Color = Color("b6c2d4")) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label

func _button(text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 36
	button.pressed.connect(action)
	button.focus_mode = Control.FOCUS_NONE
	return button

func _check(text: String, enabled: bool) -> CheckBox:
	var check := CheckBox.new()
	check.text = text
	check.button_pressed = enabled
	check.focus_mode = Control.FOCUS_NONE
	return check

func _slider(parent: VBoxContainer, minimum: float, maximum: float, step: float, value: float, changed: Callable) -> void:
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step
	slider.value = value
	slider.custom_minimum_size.y = 26
	slider.value_changed.connect(changed)
	slider.focus_mode = Control.FOCUS_NONE
	parent.add_child(slider)

func _build_ui() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 26)
	add_child(margin)
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 12)
	margin.add_child(root)
	root.add_child(_label("EVENT VISION LAB", 29, Color("e8f2ff")))
	root.add_child(_label("A controlled world, observed through changes in light.", 16))
	status = _label("Starting GPU sensor...", 13, Color("66c9db"))
	root.add_child(status)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 24)
	root.add_child(body)
	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(left)
	var aspect := AspectRatioContainer.new()
	aspect.ratio = 4.0 / 3.0
	aspect.size_flags_vertical = Control.SIZE_EXPAND_FILL
	aspect.stretch_mode = AspectRatioContainer.STRETCH_FIT
	left.add_child(aspect)
	canvas = ColorRect.new()
	canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	display_material = ShaderMaterial.new()
	display_material.shader = load("res://shaders/display.gdshader")
	display_material.set_shader_parameter("persistence", persistence)
	canvas.material = display_material
	aspect.add_child(canvas)
	left.add_child(_label("ON / brighter: cyan     OFF / darker: coral", 14, Color("8bdeea")))
	left.add_child(_label("WASD + Q/E move   |   arrows / right-drag look   |   R reset   |   V view", 13))
	var sidebar := VBoxContainer.new()
	sidebar.custom_minimum_size.x = 286
	sidebar.add_theme_constant_override("separation", 5)
	body.add_child(sidebar)
	sidebar.add_child(_label("OBSERVATION", 13, Color("66c9db")))
	mode_select = OptionButton.new()
	for mode in ["Time surface", "Raw events (display window)", "Reference intensity [debug]"]:
		mode_select.add_item(mode)
	mode_select.item_selected.connect(_set_mode)
	mode_select.focus_mode = Control.FOCUS_NONE
	sidebar.add_child(mode_select)
	threshold_label = _label("Contrast threshold  0.20 log units")
	sidebar.add_child(threshold_label)
	_slider(sidebar, 0.02, 0.6, 0.01, threshold, func(v: float):
		threshold = v
		threshold_label.text = "Contrast threshold  %.2f log units" % v)
	persistence_label = _label("Time-surface decay  180 ms")
	sidebar.add_child(persistence_label)
	_slider(sidebar, 0.02, 0.8, 0.01, persistence, func(v: float):
		persistence = v
		persistence_label.text = "Time-surface decay  %.0f ms" % (v * 1000.0)
		display_material.set_shader_parameter("persistence", v))
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("PHYSICAL STIMULI", 13, Color("66c9db")))
	motion_check = _check("Moving object", true)
	lamp_check = _check("Lamp powered", true)
	strobe_check = _check("Strobe illumination [T]", true)
	panel_check = _check("Changing emissive panel", false)
	for check in [motion_check, lamp_check, strobe_check, panel_check]: sidebar.add_child(check)
	frequency_label = _label("Strobe frequency  2.0 Hz")
	sidebar.add_child(frequency_label)
	_slider(sidebar, 0.5, 30.0, 0.5, frequency, func(v: float):
		frequency = v
		frequency_label.text = "Strobe frequency  %.1f Hz" % v)
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("CONTROLLED EXPERIMENTS", 13, Color("66c9db")))
	sidebar.add_child(_button("1   Static scene / constant light", _preset.bind(0)))
	sidebar.add_child(_button("2   Stationary scene / light pulses", _preset.bind(1)))
	sidebar.add_child(_button("3   Moving object / constant light", _preset.bind(2)))
	var note := _label("Fixed-step sampled sensor. Fast flashes can alias.\nDebug intensity is a reference, not reconstruction.", 12, Color("8192a9"))
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.custom_minimum_size.x = 270
	sidebar.add_child(note)

func _write_report() -> void:
	frame_times.sort()
	var report := {
		"godot": Engine.get_version_info().string,
		"adapter": RenderingServer.get_video_adapter_name(),
		"renderer": RenderingServer.get_current_rendering_method(),
		"sensor_size": [SENSOR_SIZE.x, SENSOR_SIZE.y],
		"sensor_target_hz": SAMPLE_HZ,
		"elapsed_seconds": elapsed_wall,
		"engine_delta_sum_seconds": elapsed,
		"submitted_sensor_samples": sample_count,
		"submitted_samples_per_wall_second": sample_count / maxf(elapsed_wall, 0.001),
		"skipped_intervals": skipped,
		"skipped_intervals_after_2s_warmup": skipped_after_warmup,
		"frame_samples_after_2s_warmup": frame_times.size(),
		"frame_median_ms": frame_times[frame_times.size() / 2] if not frame_times.is_empty() else 0,
		"frame_p95_ms": frame_times[floori((frame_times.size() - 1) * 0.95)] if not frame_times.is_empty() else 0,
		"scope": "Full analytic scene + ideal sensor + UI. Frame wall times include VSync/scheduling; not isolated GPU timings. No reconstruction, event tuples, or 3D asset engine scene."
	}
	print("EVENT_LAB_REPORT ", JSON.stringify(report))
	if not report_path.is_empty():
		var file := FileAccess.open(report_path, FileAccess.WRITE)
		if file: file.store_string(JSON.stringify(report, "\t"))

func _exit_tree() -> void:
	ready_gpu = false
	if event_texture: event_texture.texture_rd_rid = RID()
	if scene_texture: scene_texture.texture_rd_rid = RID()
	if kernel: RenderingServer.call_on_render_thread(kernel.cleanup)
