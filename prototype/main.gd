extends Control

const SensorKernel = preload("res://sensor_gpu.gd")
const RunConfig = preload("res://acquisition/run_config.gd")
const StreamWriter = preload("res://acquisition/stream_writer.gd")
const LivePerception = preload("res://stage/live_perception.gd")
var perception = LivePerception.new()
var processing_panel: TextureRect
var reconstruction_panel: TextureRect
var raw_panel: TextureRect
var perception_status: Label
var station_select: OptionButton
var station_readout: Label
var station_parameter: HSlider
var station_parameter_label: Label
var stage_check: CheckBox
var comparison_check: CheckBox
var inference_check: CheckBox
var processing_bin: OptionButton
var processing_polarity: OptionButton
var processing_mode: OptionButton
var processing_roi: CheckBox
var processing_gain := 0.5
var processing_window_ms := 100.0
var settings_path := "user://interaction-settings.json"
var acquisition_cursor_ns := 0
var active_wall_seconds := 0.0
var frame_time_total := 0.0
var frame_time_count := 0
var frame_time_max := 0.0
var maximum_memory_bytes := 0
var last_step_start_usec := 0
var maximum_step_latency_usec := 0
const CaptureWriter = preload("res://acquisition/capture_writer.gd")
const InteractionStage = preload("res://stage/interaction_stage.gd")
var interaction_stage = InteractionStage.new()
const StageController = preload("res://stage/stage_controller.gd")
signal event_batch(events: Array, cursor_ns: int)
signal acquisition_reset(cursor_ns: int)
signal validation_sample_completed(duration_usec: float, sequence: int)
const SENSOR_SIZE := Vector2i(240, 180)
const SAMPLE_HZ := 120.0
const MAX_STEPS := 8

var sensor_size := SENSOR_SIZE
var live_config: Dictionary = {}
var capture_writer: RefCounted
var capture_schedule: Array = []
var capture_index := 0
var capture_busy := false
var event_capture_directory := ""
var acquisition_config_path := ""
var latest_event_batch: Array = []
var kernel: RefCounted
var event_texture: Texture2DRD
var scene_texture: Texture2DRD
var activity_texture: Texture2DRD
var light_mode: OptionButton
var azimuth_slider: HSlider
var elevation_slider: HSlider
var sphere_check: CheckBox
var pause_check: CheckBox
var light_azimuth := 0.0
var light_elevation := 30.0
var light_speed := 0.15
var control_albedo := 0.55
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
var colors_check: CheckBox
var shortcut_actions: Dictionary[Key, Callable] = {}
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
		elif arg.begins_with("--acquisition-config="):
			acquisition_config_path = arg.trim_prefix("--acquisition-config=")
		elif arg.begins_with("--event-capture="):
			event_capture_directory = arg.trim_prefix("--event-capture=")
		elif arg.begins_with("--view="):
			initial_view = clampi(arg.trim_prefix("--view=").to_int(), 0, 3)
	_set_mode(initial_view)
	if not validation_config.is_empty():
		var parsed := RunConfig.parse(validation_config)
		if parsed.has("error"):
			_gpu_failed(parsed.error)
			return
		live_config = parsed.config
		if not _start_acquisition(): return
	elif acquisition_config_path.is_empty() and event_capture_directory.is_empty() and report_after <= 0.0:
		live_config = RunConfig.parse({"archive_mode":"stream","scene":"interactive","duration_ns":3600000000000,"sample_period_ns":16666667,"wall_paced":true}).config
		interaction_stage.enabled = true
		stage_check.button_pressed = true
		_focus_station(0)
		if not _start_acquisition(): return
	if not acquisition_config_path.is_empty() or not event_capture_directory.is_empty():
		if not _configure_acquisition(): return
	RenderingServer.call_on_render_thread(_initialize_gpu)

func _configure_acquisition() -> bool:
	var overrides: Variant = {}
	if not acquisition_config_path.is_empty():
		overrides = JSON.parse_string(FileAccess.get_file_as_string(acquisition_config_path))
	if not overrides is Dictionary:
		_gpu_failed("Live acquisition requires a JSON config object")
		get_tree().quit(1)
		return false
	var parsed := RunConfig.parse(overrides)
	if parsed.has("error"):
		_gpu_failed(parsed.error)
		get_tree().quit(1)
		return false
	live_config = parsed.config
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--source-revision="):
			live_config.source_revision = arg.trim_prefix("--source-revision=")
	return _start_acquisition()

func _start_acquisition() -> bool:
	sensor_size = Vector2i(live_config.width,live_config.height)
	threshold = live_config.on_threshold
	if live_config.archive_mode == "diagnostic" and event_capture_directory.is_empty():
		_gpu_failed("Diagnostic mode requires --event-capture directory")
		get_tree().quit(1)
		return false
	capture_schedule = RunConfig.schedule(live_config) if live_config.archive_mode == "diagnostic" else []
	capture_writer = CaptureWriter.new() if live_config.archive_mode == "diagnostic" else StreamWriter.new()
	if live_config.scene == "interaction-stage":
		stage_check.button_pressed = true
		_focus_station(live_config.station)
	perception.configure(sensor_size,{"representation":"decay","tau_ns":100000000,"window_ns":100000000})
	perception.on_threshold = live_config.on_threshold
	perception.off_threshold = live_config.off_threshold
	perception.inference_enabled = live_config.reconstruction_enabled
	inference_check.button_pressed = perception.inference_enabled
	if not capture_writer.begin(event_capture_directory,live_config):
		_gpu_failed(capture_writer.error)
		get_tree().quit(1)
		return false
	if live_config.scene != "interactive":
		# Prescribed trajectories own scene parameters; observation, pause, and reset remain available.
		for control in find_children("*","BaseButton",true,false):
			if control not in [mode_select,colors_check,pause_check,inference_check,processing_bin,processing_polarity,processing_mode,processing_roi]: control.disabled = true
		for control in find_children("*","HSlider",true,false): control.editable = false
	return true

func _process_acquisition(delta: float) -> void:
	var now_usec := Time.get_ticks_usec()
	elapsed_wall = (now_usec-wall_start_usec)*1e-6
	var frame_ms := (now_usec-previous_frame_usec)*0.001
	previous_frame_usec = now_usec
	frame_time_total += frame_ms
	frame_time_count += 1
	frame_time_max = maxf(frame_time_max,frame_ms)
	if frame_times.size() == 4096: frame_times.pop_front()
	frame_times.append(frame_ms)
	maximum_memory_bytes = maxi(maximum_memory_bytes,OS.get_static_memory_usage())
	if not pause_check.button_pressed: active_wall_seconds += delta
	status.text = "%s | %s | sample %d | sim %.2fs / wall %.2fs | skips 0" % [live_config.archive_mode,live_config.scene,capture_index,acquisition_cursor_ns*1e-9,elapsed_wall]
	if capture_busy or pause_check.button_pressed: return
	var stream: bool = live_config.archive_mode == "stream"
	var finished: bool = acquisition_cursor_ns >= live_config.duration_ns if stream else capture_index >= capture_schedule.size()
	if stream and report_after > 0.0 and elapsed_wall >= report_after: finished = true
	if finished:
		capture_busy = true
		RenderingServer.call_on_render_thread(_finish_acquisition)
		return
	var t_ns := mini(acquisition_cursor_ns+live_config.sample_period_ns,live_config.duration_ns) if stream else int(capture_schedule[capture_index])
	if capture_index == 0: t_ns = 0
	if stream:
		for reset_time in live_config.reset_times_ns:
			if reset_time > acquisition_cursor_ns and reset_time < t_ns: t_ns = reset_time
	if live_config.wall_paced and t_ns*1e-9 > active_wall_seconds: return
	var start_ns := acquisition_cursor_ns
	var initial := capture_index == 0
	var reset_after: bool = not initial and (needs_reset or live_config.reset_times_ns.has(t_ns))
	var parameters: PackedFloat32Array
	if live_config.scene == "interactive":
		_move_camera((t_ns-start_ns)*1e-9)
		parameters = _interactive_capture_parameters(t_ns,start_ns,initial)
	else:
		parameters = StageController.interaction_parameters(live_config,t_ns,start_ns,initial,interaction_stage,{"strobe":strobe_check.button_pressed,"frequency":frequency,"lamp":lamp_check.button_pressed}) if live_config.scene == "interaction-stage" else StageController.parameters(live_config,t_ns,start_ns,initial)
		if live_config.scene == "interaction-stage":
			interaction_stage.enabled = stage_check.button_pressed
			parameters[28] = float(interaction_stage.enabled)
			parameters[18] = float(strobe_check.button_pressed)
			parameters[20] = frequency
			if not lamp_check.button_pressed: parameters[17] = 0.0
	needs_reset = false
	capture_busy = true
	last_step_start_usec = Time.get_ticks_usec()
	simulation_time = t_ns * 1e-9
	display_material.set_shader_parameter("sample_time",simulation_time)
	display_material.set_shader_parameter("display_interval",live_config.sample_period_ns*1e-9+0.001)
	RenderingServer.call_on_render_thread(_capture_sample.bind(t_ns,initial,reset_after,parameters))

func _interactive_capture_parameters(t_ns: int, start_ns: int, reset: bool) -> PackedFloat32Array:
	var dt := (t_ns-start_ns)*1e-9
	if motion_check.button_pressed: motion_phase += dt
	if panel_check.button_pressed: panel_phase += dt
	var light := _light_position(camera_position,yaw,t_ns*1e-9)
	var result := PackedFloat32Array([
		t_ns*1e-9,dt,float(reset),0.0,
		threshold,threshold*live_config.off_threshold/live_config.on_threshold,persistence,1.0,
		camera_position.x,camera_position.y,camera_position.z,yaw,
		pitch,sensor_size.x,sensor_size.y,tan(deg_to_rad(58.0)/2.0),
		motion_phase,float(lamp_check.button_pressed),float(strobe_check.button_pressed),strength,
		frequency,panel_phase,float(sphere_check.button_pressed),control_albedo,
		light.x,light.y,light.z,0.0])
	interaction_stage.enabled = stage_check.button_pressed
	if interaction_stage.enabled:
		interaction_stage.advance(t_ns,strength*float(lamp_check.button_pressed)*(1.0 if not strobe_check.button_pressed or fmod(t_ns*1e-9*frequency,1.0)<0.25 else 0.0))
		if motion_check.button_pressed: interaction_stage.object_offset = 0.25*sin(motion_phase*3.0)
		result.append_array(interaction_stage.packed())
	return result

func _capture_sample(t_ns: int, initial: bool, reset_after: bool, parameters: PackedFloat32Array) -> void:
	kernel.dispatch([parameters])
	var before := Time.get_ticks_usec()
	var intensity: PackedFloat32Array = kernel.read_intensity() if live_config.archive_mode == "diagnostic" else PackedFloat32Array()
	var diagnostics: PackedFloat32Array = kernel.read_diagnostics()
	capture_writer.readback_usec += Time.get_ticks_usec()-before
	var result: Dictionary = capture_writer.append(t_ns,initial,parameters,intensity,diagnostics)
	if not result.has("error") and reset_after:
		var reset_parameters := parameters.duplicate()
		reset_parameters[2] = 1.0
		reset_parameters[1] = 0.0
		kernel.dispatch([reset_parameters])
		var reset_result: Dictionary = capture_writer.append(t_ns,true,reset_parameters,kernel.read_intensity() if live_config.archive_mode == "diagnostic" else PackedFloat32Array(),kernel.read_diagnostics())
		if reset_result.has("error"): result = reset_result
	result.thresholds = [parameters[4],parameters[5]]
	call_deferred("_capture_sample_done",result,t_ns,initial or reset_after)

func _capture_sample_done(result: Dictionary, t_ns: int, reset: bool) -> void:
	if result.has("error"):
		_gpu_failed(result.error)
		get_tree().quit(1)
		return
	last_sample_usec = Time.get_ticks_usec()-last_step_start_usec
	maximum_step_latency_usec = maxi(maximum_step_latency_usec,last_sample_usec)
	acquisition_cursor_ns = t_ns
	perception.on_threshold = result.thresholds[0]
	perception.off_threshold = result.thresholds[1]
	latest_event_batch = result.events
	event_batch.emit(latest_event_batch,t_ns)
	if live_config.processing_enabled:
		perception.consume(latest_event_batch,t_ns)
		_update_perception_views()
		peak_resident_events = maxi(peak_resident_events,perception.raw.window_count+perception.processor.window_count)
	if reset:
		acquisition_reset.emit(t_ns)
		perception.reset_sensor(t_ns)
	capture_index += 1
	sample_count += 1
	validation_sample_completed.emit(float(last_sample_usec),sample_count)
	capture_busy = false

func _finish_acquisition() -> void:
	var result: Dictionary = capture_writer.finish(RenderingServer.get_video_adapter_name())
	call_deferred("_acquisition_finished",result)

func _acquisition_finished(result: Dictionary) -> void:
	if result.has("error"):
		_gpu_failed(result.error)
		get_tree().quit(1)
		return
	set_process(false)
	result.interaction_stage = interaction_stage.metadata()
	result.live_perception = perception.metadata()
	frame_times.sort()
	result.runtime = {"elapsed_wall_seconds":elapsed_wall,"elapsed_sim_seconds":acquisition_cursor_ns*1e-9,"active_wall_seconds":active_wall_seconds,"sim_to_wall_ratio":acquisition_cursor_ns*1e-9/maxf(elapsed_wall,0.000001),"samples":sample_count,"skips":0,"frame_count":frame_time_count,"frame_mean_ms":frame_time_total/maxi(1,frame_time_count),"frame_max_ms":frame_time_max,"recent_frame_samples":frame_times.size(),"recent_frame_p95_ms":frame_times[int((frame_times.size()-1)*0.95)] if not frame_times.is_empty() else 0,"maximum_sample_dispatch_to_host_usec":maximum_step_latency_usec,"maximum_godot_static_memory_bytes":maximum_memory_bytes,"memory_scope":"Godot static allocator only; GPU/driver/process working set excluded","latency_scope":"sample dispatch to main-thread batch callback; excludes physical sensor and scanout"}
	if not event_capture_directory.is_empty():
		var file := FileAccess.open(event_capture_directory.path_join("manifest.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify(result,"  "))
	if not report_path.is_empty():
		var file := FileAccess.open(report_path,FileAccess.WRITE)
		file.store_string(JSON.stringify(result,"  "))
	await RenderingServer.frame_post_draw
	if not capture_path.is_empty():
		get_viewport().get_texture().get_image().save_png(capture_path)
	print("EVENT_LAB_ACQUISITION ",event_capture_directory," stored=",result.stages.capture_stored," emitted=",result.stages.pixel_emitted)
	get_tree().quit()

func _initialize_gpu() -> void:
	var device := RenderingServer.get_rendering_device()
	if device == null:
		call_deferred("_gpu_failed", "RenderingDevice unavailable. Use the Mobile renderer with Vulkan or D3D12.")
		return
	kernel = SensorKernel.new()
	if not kernel.initialize(device, sensor_size):
		call_deferred("_gpu_failed", kernel.error)
		return
	event_texture = Texture2DRD.new()
	event_texture.texture_rd_rid = kernel.events
	scene_texture = Texture2DRD.new()
	scene_texture.texture_rd_rid = kernel.radiance
	activity_texture = Texture2DRD.new()
	activity_texture.texture_rd_rid = kernel.activity
	call_deferred("_gpu_ready")

func _gpu_failed(message: String) -> void:
	status.text = "GPU setup failed: " + message
	push_error(message)
	if report_after > 0:
		get_tree().quit(1)

func _gpu_ready() -> void:
	display_material.set_shader_parameter("event_texture", event_texture)
	display_material.set_shader_parameter("scene_texture", scene_texture)
	display_material.set_shader_parameter("activity_texture", activity_texture)
	ready_gpu = true
	wall_start_usec = Time.get_ticks_usec()
	previous_frame_usec = wall_start_usec
	print("EVENT_LAB_READY adapter=", RenderingServer.get_video_adapter_name(), " sensor=", sensor_size, " target_hz=", 1e9/live_config.sample_period_ns if not live_config.is_empty() else SAMPLE_HZ)

func _process(delta: float) -> void:
	if not ready_gpu:
		return
	if not live_config.is_empty():
		_process_acquisition(delta)
		return
	var now_usec := Time.get_ticks_usec()
	var frame_ms := (now_usec - previous_frame_usec) / 1000.0
	previous_frame_usec = now_usec
	elapsed_wall = (now_usec - wall_start_usec) / 1000000.0
	elapsed += delta
	if elapsed_wall > 2.0:
		frame_times.append(frame_ms)
	if not pause_check.button_pressed:
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
		var light_position := _light_position(position, lerpf(previous_yaw, yaw, alpha), simulation_time)
		parameters.append(PackedFloat32Array([
			simulation_time, simulation_time - last_sample_time, float(needs_reset), 0.0,
			threshold, threshold, persistence, 1.0,
			position.x, position.y, position.z, lerpf(previous_yaw, yaw, alpha),
			lerpf(previous_pitch, pitch, alpha), SENSOR_SIZE.x, SENSOR_SIZE.y, tan(deg_to_rad(58.0) / 2.0),
			motion_phase, float(lamp_check.button_pressed), float(strobe_check.button_pressed), strength,
			frequency, panel_phase, float(sphere_check.button_pressed), control_albedo,
			light_position.x, light_position.y, light_position.z, 0.0]))
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
	camera_position.x = clampf(camera_position.x, -8.0 if interaction_stage.enabled else -4.6, 8.0 if interaction_stage.enabled else 4.6)
	camera_position.y = clampf(camera_position.y, 0.3, 8.0 if interaction_stage.enabled else 3.6)
	camera_position.z = clampf(camera_position.z, -4.6, 14.0 if interaction_stage.enabled else 5.5)
	if Input.is_physical_key_pressed(KEY_LEFT): yaw -= delta * 0.7
	if Input.is_physical_key_pressed(KEY_RIGHT): yaw += delta * 0.7
	if Input.is_physical_key_pressed(KEY_UP): pitch = minf(pitch + delta * 0.5, 0.9)
	if Input.is_physical_key_pressed(KEY_DOWN): pitch = maxf(pitch - delta * 0.5, -0.9)

func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		if canvas.get_global_rect().has_point(get_global_mouse_position()):
			yaw += event.relative.x * 0.004
			pitch = clampf(pitch - event.relative.y * 0.004, -0.9, 0.9)
	if event is InputEventKey and not (event.ctrl_pressed or event.alt_pressed or event.shift_pressed or event.meta_pressed):
		var key: Key = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if not live_config.is_empty() and live_config.scene != "interactive" and key not in [KEY_P,KEY_R,KEY_V,KEY_C]: return
		if shortcut_actions.has(key):
			if event.pressed and not event.echo:
				shortcut_actions[key].call()
			get_viewport().set_input_as_handled()

func _preset(which: int) -> void:
	interaction_stage.enabled = false
	stage_check.button_pressed = false
	motion_check.button_pressed = which == 2
	lamp_check.button_pressed = true
	strobe_check.button_pressed = false
	light_mode.select(2 if which == 1 else 0)
	panel_check.button_pressed = false
	sphere_check.button_pressed = which != 2
	needs_reset = true

func _light_position(position: Vector3, camera_yaw: float, time: float) -> Vector3:
	# Vary illumination while the object/camera can stay fixed (EventPS acquisition idea).
	if light_mode.selected == 1:
		return position + Vector3(cos(camera_yaw), 0, sin(camera_yaw)) * 0.35 + Vector3(0, 0.15, 0)
	var angle := deg_to_rad(light_azimuth)
	if light_mode.selected == 2: angle += time * light_speed * TAU
	var elevation := deg_to_rad(light_elevation)
	return (InteractionStage.center(interaction_stage.selected) if interaction_stage.enabled else Vector3(0, 1, -1)) + 3.0 * Vector3(sin(angle) * cos(elevation), sin(elevation), cos(angle) * cos(elevation))

func _light_preset(angle: float, elevation: float) -> void:
	light_mode.select(0)
	light_azimuth = angle
	light_elevation = elevation
	azimuth_slider.value = angle
	elevation_slider.value = elevation

func _set_mode(index: int) -> void:
	mode_select.select(index)
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

func _slider(parent: VBoxContainer, minimum: float, maximum: float, step: float, value: float, changed: Callable) -> HSlider:
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step
	slider.value = value
	slider.custom_minimum_size.y = 26
	slider.value_changed.connect(changed)
	slider.focus_mode = Control.FOCUS_NONE
	parent.add_child(slider)
	return slider

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
	left.add_child(_label("Event-derived activity; intensity reference is debug ground truth", 14, Color("8bdeea")))
	left.add_child(_label("WASD + Q/E move   |   arrows / right-drag look   |   R reset   |   V view   |   P pause", 13))
	var previews := HBoxContainer.new()
	previews.custom_minimum_size.y = 130
	left.add_child(previews)
	for title in ["Raw emitted window", "Post-event processing", "Relative grayscale (inferred)"]:
		var column := VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		previews.add_child(column)
		column.add_child(_label(title,11))
		var texture := TextureRect.new()
		texture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		texture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		texture.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		texture.custom_minimum_size = Vector2(100,100)
		column.add_child(texture)
		if title.begins_with("Raw"): raw_panel = texture
		elif title.begins_with("Post"): processing_panel = texture
		else: reconstruction_panel = texture
	perception_status = _label("Raw stream available in acquisition mode",11)
	left.add_child(perception_status)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.x = 320
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	var sidebar := VBoxContainer.new()
	sidebar.custom_minimum_size.x = 286
	sidebar.add_theme_constant_override("separation", 5)
	scroll.add_child(sidebar)
	sidebar.add_child(_label("OBSERVATION [V] - display only", 13, Color("66c9db")))
	mode_select = OptionButton.new()
	for mode in ["Event activity (decaying counts)", "Time surface", "Raw events (display window)", "Reference intensity [debug]"]:
		mode_select.add_item(mode)
	mode_select.item_selected.connect(_set_mode)
	mode_select.focus_mode = Control.FOCUS_NONE
	sidebar.add_child(mode_select)
	pause_check = _check("Pause acquisition [P]", false)
	sidebar.add_child(pause_check)
	colors_check = _check("Polarity colors [C] (optional)", false)
	colors_check.toggled.connect(func(v: bool): display_material.set_shader_parameter("polarity_color", v))
	sidebar.add_child(colors_check)
	_build_stage_ui(sidebar)
	threshold_label = _label("Contrast threshold  0.20 log units")
	sidebar.add_child(threshold_label)
	_slider(sidebar, 0.02, 0.6, 0.01, threshold, func(v: float):
		threshold = v
		threshold_label.text = "Contrast threshold  %.2f log units" % v)
	persistence_label = _label("Activity / surface decay  180 ms")
	sidebar.add_child(persistence_label)
	_slider(sidebar, 0.02, 0.8, 0.01, persistence, func(v: float):
		persistence = v
		persistence_label.text = "Activity / surface decay  %.0f ms" % (v * 1000.0)
		display_material.set_shader_parameter("persistence", v))
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("ACTIVE LIGHTING [L]", 13, Color("66c9db")))
	light_mode = OptionButton.new()
	for name in ["Fixed world light", "Camera-mounted light", "Orbiting light / fixed target"]: light_mode.add_item(name)
	light_mode.select(2)
	light_mode.focus_mode = Control.FOCUS_NONE
	sidebar.add_child(light_mode)
	sphere_check = _check("Matte sphere control scene [F]", true)
	sidebar.add_child(sphere_check)
	sidebar.add_child(_label("Light azimuth offset (-180 to 180 deg)", 13))
	azimuth_slider = _slider(sidebar, -180, 180, 1, light_azimuth, func(v: float): light_azimuth = v)
	sidebar.add_child(_label("Light elevation (0 to 80 deg)", 13))
	elevation_slider = _slider(sidebar, 0, 80, 1, light_elevation, func(v: float): light_elevation = v)
	sidebar.add_child(_label("Orbit speed (0.02 to 0.5 turns/s)", 13))
	_slider(sidebar, 0.02, 0.5, 0.01, light_speed, func(v: float): light_speed = v)
	sidebar.add_child(_button("Light from left [4]", _light_preset.bind(-60.0, 30.0)))
	sidebar.add_child(_button("Light from right [5]", _light_preset.bind(60.0, 30.0)))
	sidebar.add_child(_button("Light from above [6]", _light_preset.bind(0.0, 75.0)))
	sidebar.add_child(_label("Matte control albedo (0.05 to 0.9)", 13))
	_slider(sidebar, 0.05, 0.9, 0.05, control_albedo, func(v: float): control_albedo = v)
	sidebar.add_child(_label("Lamp strength (0.1 to 10)", 13))
	_slider(sidebar, 0.1, 10, 0.1, strength, func(v: float): strength = v)
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("OTHER STIMULI", 13, Color("66c9db")))
	motion_check = _check("Moving object [M] (room scene)", false)
	lamp_check = _check("Lamp powered [B]", true)
	strobe_check = _check("Strobe illumination [T] (opt-in)", false)
	panel_check = _check("Changing emissive panel [N]", false)
	for check in [motion_check, lamp_check, strobe_check, panel_check]: sidebar.add_child(check)
	frequency_label = _label("Strobe frequency  2.0 Hz")
	sidebar.add_child(frequency_label)
	_slider(sidebar, 0.5, 30.0, 0.5, frequency, func(v: float):
		frequency = v
		frequency_label.text = "Strobe frequency  %.1f Hz" % v)
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("CONTROLLED EXPERIMENTS", 13, Color("66c9db")))
	sidebar.add_child(_button("1   Static scene / constant light", _preset.bind(0)))
	sidebar.add_child(_button("2   Stationary scene / orbit light", _preset.bind(1)))
	sidebar.add_child(_button("3   Moving object / constant light", _preset.bind(2)))
	var note := _label("EventPS-inspired acquisition, not normal reconstruction.\nFixed-step sensor; fast flashes can alias.\nDebug intensity is a reference, not reconstruction.", 12, Color("8192a9"))
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.custom_minimum_size.x = 270
	sidebar.add_child(note)
	shortcut_actions = {
		KEY_J: func(): stage_check.button_pressed = not stage_check.button_pressed,
		KEY_K: func(): _focus_station((interaction_stage.selected+1)%9),
		KEY_H: func(): _focus_station(interaction_stage.selected),
		KEY_X: func(): comparison_check.button_pressed = not comparison_check.button_pressed,
		KEY_Z: _reset_material,
		KEY_I: func(): inference_check.button_pressed = not inference_check.button_pressed,
		KEY_O: func(): processing_roi.button_pressed = not processing_roi.button_pressed,
		KEY_G: _cycle_bins,
		KEY_Y: _cycle_polarity,
		KEY_U: _cycle_processing_mode,
		KEY_1: _preset.bind(0),
		KEY_2: _preset.bind(1),
		KEY_3: _preset.bind(2),
		KEY_4: _light_preset.bind(-60.0, 30.0),
		KEY_5: _light_preset.bind(60.0, 30.0),
		KEY_6: _light_preset.bind(0.0, 75.0),
		KEY_R: func(): needs_reset = true,
		KEY_V: func(): _set_mode((mode_select.selected + 1) % mode_select.item_count),
		KEY_L: func(): light_mode.select((light_mode.selected + 1) % light_mode.item_count),
		KEY_P: func(): pause_check.button_pressed = not pause_check.button_pressed,
		KEY_C: func(): colors_check.button_pressed = not colors_check.button_pressed,
		KEY_F: func(): sphere_check.button_pressed = not sphere_check.button_pressed,
		KEY_M: func(): motion_check.button_pressed = not motion_check.button_pressed,
		KEY_B: func(): lamp_check.button_pressed = not lamp_check.button_pressed,
		KEY_T: func(): strobe_check.button_pressed = not strobe_check.button_pressed,
		KEY_N: func(): panel_check.button_pressed = not panel_check.button_pressed,
	}

func _write_report() -> void:
	frame_times.sort()
	var report := {
		"godot": Engine.get_version_info().string,
		"adapter": RenderingServer.get_video_adapter_name(),
		"renderer": RenderingServer.get_current_rendering_method(),
		"sensor_size": [SENSOR_SIZE.x, SENSOR_SIZE.y],
		"sensor_target_hz": SAMPLE_HZ,
		"active_lighting": "fixed / camera-mounted / orbit point light; matte control or room",
		"default_strobe": false,
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
	if activity_texture: activity_texture.texture_rd_rid = RID()
	if kernel: RenderingServer.call_on_render_thread(kernel.cleanup)

func _build_stage_ui(sidebar: VBoxContainer) -> void:
	sidebar.add_child(HSeparator.new())
	sidebar.add_child(_label("NINE OPTICAL STATIONS",13,Color("66c9db")))
	stage_check = _check("Interaction stage [J]",false)
	stage_check.toggled.connect(func(v: bool):
		interaction_stage.enabled = v
		if v: _focus_station(interaction_stage.selected))
	sidebar.add_child(stage_check)
	station_select = OptionButton.new()
	for id in InteractionStage.IDS: station_select.add_item(id.capitalize())
	station_select.item_selected.connect(_focus_station)
	sidebar.add_child(station_select)
	sidebar.add_child(_button("Next station [K]",func(): _focus_station((interaction_stage.selected+1)%9)))
	sidebar.add_child(_button("Focus selected station [H]",func(): _focus_station(interaction_stage.selected)))
	sidebar.add_child(_button("Overview of all nine stations",_overview_stage))
	comparison_check = _check("Treatment enabled [X]",true)
	comparison_check.toggled.connect(func(v: bool): interaction_stage.treatment = v; _station_description())
	sidebar.add_child(comparison_check)
	sidebar.add_child(_button("Reset selected material [Z]",_reset_material))
	station_parameter_label = _label("",12)
	sidebar.add_child(station_parameter_label)
	station_parameter = _slider(sidebar,0,8,0.01,2,func(v: float):
		if interaction_stage.set_primary(v): _station_description())
	sidebar.add_child(_label("Object translation (metres), independent of camera",12))
	_slider(sidebar,-0.5,0.5,0.01,0.0,func(v: float): interaction_stage.object_offset=v)
	sidebar.add_child(_label("Rear excitation stripe position (metres)",12))
	_slider(sidebar,-0.5,0.5,0.01,0.0,func(v: float): interaction_stage.stripe_offset=v)
	sidebar.add_child(_label("Excitation band overlap (0 to 1)",12))
	_slider(sidebar,0,1,0.05,1,func(v: float): interaction_stage.excitation_band=v)
	var component := OptionButton.new()
	for label in ["Total detector intensity", "Truth component A: direct / absorption", "Truth component B: converted / untraced"]: component.add_item(label)
	component.item_selected.connect(func(v: int): interaction_stage.truth_component=v)
	sidebar.add_child(component)
	station_readout = _label("",11)
	station_readout.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	station_readout.custom_minimum_size.x = 270
	sidebar.add_child(station_readout)
	_sync_station_parameter()
	_station_description()
	sidebar.add_child(_label("LIVE POST-EVENT TOOLS",13,Color("66c9db")))
	processing_roi = _check("Central half ROI [O]",false)
	processing_roi.toggled.connect(func(_v: bool): _configure_processing())
	sidebar.add_child(processing_roi)
	processing_bin = OptionButton.new()
	for label in ["1 x 1 bins [G]","2 x 2 bins [G]","4 x 4 bins [G]"]: processing_bin.add_item(label)
	processing_bin.item_selected.connect(func(_v: int): _configure_processing())
	sidebar.add_child(processing_bin)
	processing_polarity = OptionButton.new()
	for label in ["Both polarities [Y]","ON only [Y]","OFF only [Y]"]: processing_polarity.add_item(label)
	processing_polarity.item_selected.connect(func(_v: int): _configure_processing())
	sidebar.add_child(processing_polarity)
	processing_mode = OptionButton.new()
	for label in ["Decaying counts [U]","Exact event window [U]","Time surface [U]"]: processing_mode.add_item(label)
	processing_mode.item_selected.connect(func(_v: int): _configure_processing())
	sidebar.add_child(processing_mode)
	sidebar.add_child(_label("Window / decay (10 to 1000 ms)",12))
	_slider(sidebar,10,1000,10,100,func(v: float): processing_window_ms=v; _configure_processing())
	sidebar.add_child(_label("Display gain (retains processing history)",12))
	_slider(sidebar,0.05,2,0.05,0.5,func(v: float): processing_gain=v; _configure_processing())
	inference_check = _check("Infer relative grayscale [I]",false)
	inference_check.toggled.connect(func(v: bool): perception.inference_enabled=v; reconstruction_panel.visible=v)
	sidebar.add_child(inference_check)
	sidebar.add_child(_label("Constant log prior (-4 to 4; starts new inference)",12))
	_slider(sidebar,-4,4,0.1,0,func(v: float): perception.prior=v; perception.reset_prior(acquisition_cursor_ns))
	sidebar.add_child(_button("Reset constant log prior here",func(): perception.reset_prior(acquisition_cursor_ns)))
	sidebar.add_child(_button("Save effective settings",_save_settings))
	sidebar.add_child(_button("Load saved settings",_load_settings))
	var reduced := _check("Reduced flashes (display only)",true)
	reduced.toggled.connect(_set_reduced_flashes)
	sidebar.add_child(reduced)
	_set_reduced_flashes(true)
	sidebar.add_child(_label("Default media RGB cap 0.08. Opt out above.
A display limit, not a safety certification.
ROI/bin/polarity/time changes clear processing only.
Gain retains it. Inference uses raw events.
Silent texture and absolute brightness are unknown.",11))

func _focus_station(index: int) -> void:
	camera_position = interaction_stage.focus(index)
	previous_camera = camera_position
	yaw = -PI/4.0 if index==8 else 0.0
	pitch = 0.0
	previous_yaw = yaw
	previous_pitch = pitch
	station_select.select(index)
	_sync_station_parameter()
	_station_description()

func _overview_stage() -> void:
	camera_position = Vector3(0,3.5,9.0)
	previous_camera = camera_position
	yaw = 0.0
	pitch = 0.0

func _reset_material() -> void:
	interaction_stage.reset_station(interaction_stage.selected)
	comparison_check.button_pressed = true
	_sync_station_parameter()
	_station_description()

func _station_description() -> void:
	if station_readout == null: return
	var id: String = InteractionStage.IDS[interaction_stage.selected]
	var model: Dictionary = {}
	for candidate in interaction_stage.registry.models:
		if candidate.id == id: model = candidate
	station_readout.text = "%s
Parameters %s
%s
Missing: %s
Treatment %s. Sensor reset preserves material state." % [id,_named_station_parameters(),model.get("model",""),model.get("missing",""),str(interaction_stage.treatment)]

func _configure_processing() -> void:
	if perception.processor.config.is_empty(): return
	var roi := [0,0,sensor_size.x,sensor_size.y]
	if processing_roi.button_pressed: roi = [sensor_size.x/4,sensor_size.y/4,sensor_size.x*3/4,sensor_size.y*3/4]
	perception.processor.configure({"roi":roi,"bin_size":[1,2,4][processing_bin.selected],"polarity":["both","on","off"][processing_polarity.selected],"representation":["decay","window","time-surface"][processing_mode.selected],"window_ns":int(processing_window_ms*1000000),"tau_ns":int(processing_window_ms*1000000),"gain":processing_gain},sensor_size)
	# No event or sensor is changed. A paused view can update from current aggregates.
	perception.last_processed = perception.processor.snapshot(acquisition_cursor_ns)
	_update_perception_views()

func _cycle_bins() -> void:
	processing_bin.select((processing_bin.selected+1)%3)
	_configure_processing()

func _cycle_polarity() -> void:
	processing_polarity.select((processing_polarity.selected+1)%3)
	_configure_processing()

func _cycle_processing_mode() -> void:
	processing_mode.select((processing_mode.selected+1)%3)
	_configure_processing()

func _update_perception_views() -> void:
	if not perception.last_processed.is_empty(): processing_panel.texture = ImageTexture.create_from_image(perception.image(perception.last_processed))
	if not perception.last_raw.is_empty(): raw_panel.texture = ImageTexture.create_from_image(perception.image(perception.last_raw))
	reconstruction_panel.visible = perception.inference_enabled
	if perception.inference_enabled: reconstruction_panel.texture = ImageTexture.create_from_image(perception.reconstruction_image())
	perception_status.text = "Raw batch %d | processing loss %d | raw window loss %d | relative prior log %.1f" % [latest_event_batch.size(),perception.processor.window_overflow_count,perception.raw.window_overflow_count,perception.prior]

func _save_settings() -> void:
	var file := FileAccess.open(settings_path,FileAccess.WRITE)
	file.store_string(JSON.stringify({"stage":interaction_stage.metadata(),"processing":perception.processor.config,"inference":perception.metadata().inference,"reduced_flashes":reduced_flashes,"camera":[camera_position.x,camera_position.y,camera_position.z,yaw,pitch],"reset_behavior":"load changes processing semantic state; sensor and material population retained; inference changes start a fresh constant prior"},"  "))
	perception_status.text = "Saved "+settings_path

func _load_settings() -> void:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(settings_path))
	if not value is Dictionary or not value.has_all(["processing","inference","stage","camera"]):
		perception_status.text = "Invalid settings file"
		return
	if not value.processing is Dictionary or not _valid_processing(value.processing):
		perception_status.text = "Invalid processing settings"
		return
	var parsed := interaction_stage.restore(value.stage)
	if not parsed:
		perception_status.text = "Invalid material settings"
		return
	# Settings are emitted by this application. Validate the processing envelope before configure.
	var config: Dictionary = value.processing
	if not _valid_processing(config):
		perception_status.text = "Invalid processing settings"
		return
	perception.processor.configure(config,sensor_size)
	_sync_processing_controls()
	var infer: Dictionary = value.inference
	if not is_finite(float(infer.get("constant_log_prior",0))): return
	perception.prior = float(infer.get("constant_log_prior",0))
	perception.reset_prior(acquisition_cursor_ns)
	inference_check.button_pressed = bool(infer.get("enabled",false))
	_set_reduced_flashes(bool(value.get("reduced_flashes",true)))
	var camera: Array = value.camera
	if camera.size()==5:
		camera_position = Vector3(camera[0],camera[1],camera[2])
		yaw = camera[3]
		pitch = camera[4]
	stage_check.set_pressed_no_signal(interaction_stage.enabled)
	comparison_check.set_pressed_no_signal(interaction_stage.treatment)
	station_select.select(interaction_stage.selected)
	_sync_station_parameter()
	_station_description()

func _valid_processing(config: Dictionary) -> bool:
	if not config.has_all(["roi","bin_size","polarity","representation","window_ns","tau_ns","normalization","gain"]): return false
	for key in config:
		if key not in ["roi","bin_size","polarity","representation","window_ns","tau_ns","normalization","gain","window_capacity"]: return false
	for key in ["bin_size","window_ns","tau_ns","gain","window_capacity"]:
		var value: Variant = config.get(key,100000)
		if typeof(value) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(value): return false
		if key!="gain" and value!=int(value): return false
	if not config.roi is Array or config.roi.size()!=4: return false
	for value in config.roi:
		if typeof(value) not in [TYPE_FLOAT,TYPE_INT] or not is_finite(value) or value != int(value): return false
	var roi: Array = config.roi
	return roi[0]>=0 and roi[1]>=0 and roi[2]>roi[0] and roi[3]>roi[1] and roi[2]<=sensor_size.x and roi[3]<=sensor_size.y and config.bin_size in [1,2,4] and config.polarity in ["both","on","off"] and config.representation in ["decay","window","time-surface"] and config.normalization in ["count","per-pixel"] and config.window_ns>0 and config.tau_ns>0 and is_finite(config.gain) and config.gain>0 and config.get("window_capacity",100000) in range(1,1000001)

func _sync_processing_controls() -> void:
	var config: Dictionary = perception.processor.config
	processing_bin.select([1,2,4].find(config.bin_size))
	processing_polarity.select(["both","on","off"].find(config.polarity))
	processing_mode.select(["decay","window","time-surface"].find(config.representation))
	processing_gain = config.gain
	processing_window_ms = config.window_ns*1e-6

var reduced_flashes := true
var validation_config: Dictionary = {}
var last_sample_usec := 0
var peak_resident_events := 0

func _set_reduced_flashes(value: bool) -> void:
	reduced_flashes = value
	display_material.set_shader_parameter("reduced_flashes",value)
	for panel in [raw_panel,processing_panel,reconstruction_panel]:
		if panel.material == null:
			var material := ShaderMaterial.new()
			material.shader = load("res://shaders/reduced_flashes.gdshader")
			panel.material = material
		panel.material.set_shader_parameter("reduced_flashes",value)

func get_validation_snapshot() -> Dictionary:
	var emitted: int = capture_writer.generated if capture_writer else 0
	var stored: int = capture_writer.stored if capture_writer else 0
	var effective := live_config.duplicate(true)
	effective.merge({"stage_enabled":interaction_stage.enabled,"station":interaction_stage.selected,"treatment":interaction_stage.treatment,"processing":perception.processor.config,"inference_enabled":perception.inference_enabled,"reduced_flashes":reduced_flashes,"frequency":frequency,"strobe_enabled":strobe_check.button_pressed,"lamp_enabled":lamp_check.button_pressed,"backend":RenderingServer.get_current_rendering_method()},true)
	return {"samples":sample_count,"sample_sequence":sample_count,"last_sample_usec":last_sample_usec,"emitted":emitted,"skipped":0,"suppressed":0,"readout_loss":null,"capture_overflow":emitted-stored if not event_capture_directory.is_empty() else 0,"capture_not_requested":emitted if event_capture_directory.is_empty() else 0,"processing_overflow":perception.processor.window_overflow_count,"raw_display_overflow":perception.raw.window_overflow_count,"backlog":int(capture_busy),"buffer_peak":peak_resident_events,"cursor_ns":acquisition_cursor_ns,"inference_cursor_ns":acquisition_cursor_ns if perception.inference_enabled else null,"processing_usec":perception.processing_usec,"maximum_processing_usec":perception.max_processing_usec,"elapsed_wall_seconds":elapsed_wall,"elapsed_sim_seconds":acquisition_cursor_ns*1e-9,"memory_bytes":OS.get_static_memory_usage(),"effective":effective,"stage":interaction_stage.metadata(),"ready":ready_gpu,"error":capture_writer.error if capture_writer else ""}

func validation_apply_scenario(config: Dictionary) -> Dictionary:
	for key in config:
		if key not in ["stage_action","station","treatment","stage_enabled","processing","inference_enabled","reduced_flashes","frequency","strobe_enabled","lamp_enabled","reset_sensor","material_reset"]: return {"applied":false,"error":"Unsupported runtime setting: "+key}
	if config.has("processing") and not _valid_processing(config.processing): return {"applied":false,"error":"Invalid processing settings"}
	if config.has("stage_action"):
		if config.stage_action not in ["static","light","camera","object","pulse","compare","stripe","tour"]: return {"applied":false,"error":"Invalid action"}
		live_config.stage_action = config.stage_action
	if config.has("station"):
		if config.station < 0 or config.station > 8: return {"applied":false,"error":"Invalid station"}
		live_config.station = int(config.station)
		_focus_station(int(config.station))
	if config.has("treatment"):
		live_config.treatment = bool(config.treatment)
		comparison_check.button_pressed = bool(config.treatment)
	if config.has("stage_enabled"): stage_check.button_pressed = bool(config.stage_enabled)
	if config.has("processing"):
		perception.processor.configure(config.processing,sensor_size)
		_sync_processing_controls()
	if config.has("inference_enabled"): inference_check.button_pressed = bool(config.inference_enabled)
	if config.has("reduced_flashes"): _set_reduced_flashes(bool(config.reduced_flashes))
	if config.has("frequency"): frequency = clampf(float(config.frequency),0.5,30)
	if config.has("strobe_enabled"): strobe_check.button_pressed = bool(config.strobe_enabled)
	if config.has("lamp_enabled"): lamp_check.button_pressed = bool(config.lamp_enabled)
	if config.get("reset_sensor",false): needs_reset = true
	if config.get("material_reset",false): _reset_material()
	return {"applied":true,"effective":get_validation_snapshot().effective}

func _named_station_parameters() -> String:
	var names: Array = InteractionStage.KEYS[interaction_stage.selected]
	var values: Array = interaction_stage.parameters[interaction_stage.selected]
	var parts := PackedStringArray()
	for i in names.size(): parts.append("%s=%.4f" % [names[i],values[i]])
	return ", ".join(parts)

func _sync_station_parameter() -> void:
	var index: int = interaction_stage.selected
	station_parameter.set_block_signals(true)
	station_parameter.min_value = InteractionStage.PRIMARY_RANGE[index][0]
	station_parameter.max_value = InteractionStage.PRIMARY_RANGE[index][1]
	station_parameter.value = interaction_stage.parameters[index][InteractionStage.PRIMARY_INDEX[index]]
	station_parameter.set_block_signals(false)
	station_parameter_label.text = InteractionStage.KEYS[index][InteractionStage.PRIMARY_INDEX[index]]+" (one-factor parameter)"

var validation_final_report: Dictionary = {}
func validation_finish() -> Dictionary:
	if not validation_final_report.is_empty(): return validation_final_report
	set_process(false)
	while capture_busy: await get_tree().process_frame
	var report: Dictionary = capture_writer.finish(RenderingServer.get_video_adapter_name()) if capture_writer else {"error":"No acquisition writer"}
	report["termination_reason"] = "validation-wall-duration"
	report["actual_cursor_ns"] = acquisition_cursor_ns
	report["configured_duration_reached"] = acquisition_cursor_ns>=int(live_config.get("duration_ns",0))
	report["finalized"] = not report.has("error")
	report["runtime"] = get_validation_snapshot()
	report["live_perception"] = perception.metadata()
	if not event_capture_directory.is_empty() and not report.has("error"):
		var file := FileAccess.open(event_capture_directory.path_join("manifest.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify(report,"  "))
	validation_final_report = report
	return report
