extends SceneTree

var lab: Control
var scenario: Dictionary
var directory := ""
var started_usec := 0
var measured_usec := 0
var previous_draw_usec := 0
var frame_usec: Array[float] = []
var batch_interval_usec: Array[float] = []
var sample_service_usec: Array[float] = []
var previous_batch_usec := 0
var event_count := 0
var batch_count := 0
var reset_count := 0
var latest_cursor_ns := 0
var warmup_cursor_ns := 0
var action_index := 0
var actions: Array = []
var acknowledgements: Array = []
var errors: Array = []
var telemetry: FileAccess
var next_telemetry_s := 0.0
var initial_snapshot: Dictionary = {}
var snapshot: Dictionary = {}
var tcp: StreamPeerTCP
var capture_port := 0
var source_revision := ""
var capture_frames := 0
var pending_key: Dictionary = {}
var reset_deadline_usec := 0
var sample_timing_coverage := 0
var measuring := false
var finishing := false
var previous_losses: Dictionary = {}
var observed_losses := {"processing_overflow":0,"raw_display_overflow":0}
var inference_age_usec: Array[float] = []

func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--validation-scenario="):
			scenario = JSON.parse_string(FileAccess.get_file_as_string(arg.trim_prefix("--validation-scenario=")))
		elif arg.begins_with("--validation-output="):
			directory = arg.trim_prefix("--validation-output=")
		elif arg.begins_with("--capture-port="):
			capture_port = arg.trim_prefix("--capture-port=").to_int()
		elif arg.begins_with("--source-revision="):
			source_revision = arg.trim_prefix("--source-revision=")
	call_deferred("_run")

func _run() -> void:
	if scenario.is_empty() or directory.is_empty():
		push_error("Validation requires scenario and output paths")
		quit(1)
		return
	if float(scenario.get("warmup_seconds", -1)) < 0 or float(scenario.get("measure_seconds", 0)) <= 0:
		push_error("Invalid validation duration")
		quit(1)
		return
	telemetry = FileAccess.open(directory.path_join("runtime.jsonl"), FileAccess.WRITE)
	if telemetry == null:
		quit(1)
		return
	lab = load("res://main.gd").new()
	if not lab.has_method("get_validation_snapshot") or not lab.has_method("validation_apply_scenario"):
		_fail("Composed stage validation hooks are absent")
		return
	var acquisition: Dictionary = scenario.get("acquisition", {}).duplicate(true)
	if not source_revision.is_empty(): acquisition["source_revision"] = source_revision
	lab.set("validation_config", acquisition)
	lab.event_batch.connect(_on_batch)
	lab.acquisition_reset.connect(_on_reset)
	if lab.has_signal("validation_sample_completed"):
		lab.connect("validation_sample_completed", _on_sample)
	root.add_child(lab)
	var wait_started := Time.get_ticks_usec()
	while not lab.ready_gpu:
		await process_frame
		if Time.get_ticks_usec() - wait_started > 30000000:
			_fail("GPU readiness timed out")
			return
	if capture_port:
		tcp = StreamPeerTCP.new()
		if tcp.connect_to_host("127.0.0.1", capture_port) != OK:
			_fail("Cannot connect output receiver")
			return
		while tcp.get_status() == StreamPeerTCP.STATUS_CONNECTING:
			tcp.poll()
			await process_frame
		if tcp.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			_fail("Output receiver connection failed")
			return
	if not _apply(scenario.get("initial", {}), "initial"):
		return
	actions = scenario.get("actions", [])
	started_usec = Time.get_ticks_usec()
	RenderingServer.frame_post_draw.connect(_on_draw)
	while not finishing:
		await process_frame
		var now := Time.get_ticks_usec()
		var elapsed := (now - started_usec) * 1e-6
		if not measuring and elapsed >= float(scenario.warmup_seconds):
			measuring = true
			measured_usec = now
			warmup_cursor_ns = latest_cursor_ns
			initial_snapshot = lab.get_validation_snapshot()
			previous_losses = initial_snapshot.duplicate()
			observed_losses = {"processing_overflow":0,"raw_display_overflow":0}
			previous_draw_usec = 0
			previous_batch_usec = 0
			frame_usec.clear()
			batch_interval_usec.clear()
			sample_service_usec.clear()
			sample_timing_coverage = 0
			event_count = 0
			batch_count = 0
			reset_count = 0
		var measured_s := (now - measured_usec) * 1e-6 if measuring else -1.0
		while measuring and action_index < actions.size() and measured_s >= float(actions[action_index].at_s):
			var action: Dictionary = actions[action_index]
			if action.has("apply") and not _apply(action.apply, str(action.get("name", action_index))):
				return
			if action.has("key"):
				_inject_key(str(action.key), str(action.get("name", action_index)))
			action_index += 1
		if reset_deadline_usec and now > reset_deadline_usec:
			_fail("Requested reset did not emit acquisition_reset before deadline")
			return
		if not pending_key.is_empty() and now - int(pending_key.injected_usec) > 5000000:
			_fail("Scripted input did not reach a rendered acknowledgement")
			return
		if measuring and measured_s >= next_telemetry_s:
			snapshot = lab.get_validation_snapshot()
			telemetry.store_line(JSON.stringify({"wall_s":measured_s,"cursor_ns":latest_cursor_ns,"events":event_count,
				"batches":batch_count,"snapshot":snapshot}))
			telemetry.flush()
			print("VALIDATION_PROGRESS ",JSON.stringify({"wall_s":measured_s,"events":event_count,"batches":batch_count}))
			next_telemetry_s = measured_s + 5.0
		if measuring and measured_s >= float(scenario.measure_seconds):
			await RenderingServer.frame_post_draw
			await _finish()
			return

func _apply(config: Dictionary, name: String) -> bool:
	if config.is_empty(): return true
	if measuring: _observe_losses(lab.get_validation_snapshot())
	var result: Dictionary = lab.validation_apply_scenario(config)
	acknowledgements.append({"name":name,"requested":config,"result":result,"wall_usec":Time.get_ticks_usec()})
	if not result.get("applied", false):
		_fail("Scenario was rejected: " + name + ": " + str(result.get("error", "No rejection reason supplied")))
		return false
	var effective: Dictionary = result.get("effective", {})
	for key in config:
		if not effective.has(key) or not _same_setting(config[key], effective[key]):
			_fail("Scenario intent differs from effective value: " + name + "/" + str(key))
			return false
	return true

static func _same_setting(requested: Variant, effective: Variant) -> bool:
	if requested is Dictionary and effective is Dictionary:
		if requested.size() != effective.size(): return false
		for key in requested:
			if not effective.has(key) or not _same_setting(requested[key], effective[key]): return false
		return true
	if requested is Array and effective is Array:
		if requested.size() != effective.size(): return false
		for index in requested.size():
			if not _same_setting(requested[index], effective[index]): return false
		return true
	if typeof(requested) != typeof(effective):
		if typeof(requested) not in [TYPE_INT, TYPE_FLOAT] or typeof(effective) not in [TYPE_INT, TYPE_FLOAT]: return false
	return requested == effective

func _inject_key(key: String, name: String) -> void:
	if not pending_key.is_empty():
		_fail("Overlapping scripted input acknowledgement")
		return
	var event := InputEventKey.new()
	event.physical_keycode = OS.find_keycode_from_string(key)
	event.pressed = true
	pending_key = {"name":name,"key":key,"injected_usec":Time.get_ticks_usec(),
		"before_mode":lab.mode_select.selected,"before_reset_count":reset_count}
	Input.parse_input_event(event)
	event = event.duplicate()
	event.pressed = false
	Input.parse_input_event(event)
	if key == "R": reset_deadline_usec = Time.get_ticks_usec() + 5000000

func _on_batch(events: Array, cursor_ns: int) -> void:
	latest_cursor_ns = cursor_ns
	if not measuring: return
	var now := Time.get_ticks_usec()
	if previous_batch_usec: batch_interval_usec.append(float(now-previous_batch_usec))
	previous_batch_usec = now
	event_count += events.size()
	batch_count += 1

func _on_reset(_cursor_ns: int) -> void:
	if measuring: _observe_losses(lab.get_validation_snapshot())
	reset_count += 1
	reset_deadline_usec = 0

func _on_sample(duration_usec: float, _sequence: int) -> void:
	if measuring:
		sample_service_usec.append(duration_usec)
		sample_timing_coverage += 1
		var state: Dictionary = lab.get_validation_snapshot()
		_observe_losses(state)
		if state.get("inference_cursor_ns") != null:
			inference_age_usec.append((int(state.cursor_ns)-int(state.inference_cursor_ns))*0.001)

func _observe_losses(state: Dictionary) -> void:
	for key in observed_losses:
		var current := int(state.get(key,0))
		var previous := int(previous_losses.get(key,0))
		observed_losses[key] += current-previous if current>=previous else current
		previous_losses[key] = current

func _on_draw() -> void:
	if not measuring or finishing: return
	var now := Time.get_ticks_usec()
	if previous_draw_usec: frame_usec.append(float(now - previous_draw_usec))
	previous_draw_usec = now
	if not pending_key.is_empty():
		var key: String = pending_key.key
		var acknowledged: bool = (key == "V" and lab.mode_select.selected != int(pending_key.before_mode)) or (key == "R" and reset_count > int(pending_key.before_reset_count))
		if acknowledged:
			pending_key["render_ack_usec"] = now
			pending_key["latency_usec"] = now - int(pending_key.injected_usec)
			acknowledgements.append(pending_key)
			pending_key = {}
	if tcp:
		var rendered := root.get_texture().get_image()
		rendered.convert(Image.FORMAT_RGB8)
		var header := {"width":rendered.get_width(),"height":rendered.get_height(),
			"draw_frame":Engine.get_frames_drawn(),"wall_s":(now-measured_usec)*1e-6}
		if tcp.put_data((JSON.stringify(header)+"\n").to_utf8_buffer()) != OK or tcp.put_data(rendered.get_data()) != OK:
			_fail("Output frame transfer failed")
			return
		capture_frames += 1

func _stats(values: Array[float]) -> Dictionary:
	if values.is_empty(): return {"count":0}
	var ordered := values.duplicate()
	ordered.sort()
	return {"count":values.size(),"median_usec":ordered[int(ceil(ordered.size()*0.5))-1],
		"p95_usec":ordered[int(ceil(ordered.size()*0.95))-1],"p99_usec":ordered[int(ceil(ordered.size()*0.99))-1],
		"max_usec":ordered[-1]}

func _finish() -> void:
	if finishing: return
	finishing = true
	if action_index != actions.size(): errors.append("Not all scripted actions executed")
	if not pending_key.is_empty() or reset_deadline_usec: errors.append("Pending input or reset acknowledgement")
	if event_count == 0 or batch_count == 0: errors.append("Measured acquisition did no event work")
	if tcp:
		tcp.put_data("{\"end\":true}\n".to_utf8_buffer())
		tcp.disconnect_from_host()
	var finalization := {"finalized":false,"reason":"validation_finish hook absent"}
	if lab.has_method("validation_finish"):
		finalization = await lab.validation_finish()
		if not finalization.get("finalized",false): errors.append("Stream finalization failed")
	var measured_s := (Time.get_ticks_usec()-measured_usec)*1e-6
	var report := {"schema":"event-lab-runtime-validation-v1","scenario":scenario,"errors":errors,
		"termination_reason":"validation wall duration reached","configured_simulation_completed":false,
		"stream_finalization":finalization,"archive_finalized":finalization.get("finalized",false) and not lab.event_capture_directory.is_empty(),
		"capture_scope":"recording disabled in supplied sustained profiles; no CSV throughput claim",
		"measured_wall_seconds":measured_s,"simulated_seconds":(latest_cursor_ns-warmup_cursor_ns)*1e-9,
		"warmup_seconds":scenario.warmup_seconds,"event_count":event_count,"sample_batches":batch_count,"resets":reset_count,
		"frame_intervals":_stats(frame_usec),"event_batch_intervals":_stats(batch_interval_usec),
		"sample_service":_stats(sample_service_usec),"sample_timing_coverage":sample_timing_coverage,
		"inference_observation_age":_stats(inference_age_usec),"observed_processing_losses":observed_losses,
		"initial_snapshot":initial_snapshot,"final_snapshot":lab.get_validation_snapshot(),
		"actions":acknowledgements,"output_capture_frames":capture_frames,"output_capture_instrumented":tcp != null,
		"hardware":{"adapter":RenderingServer.get_video_adapter_name(),"vendor":RenderingServer.get_video_adapter_vendor(),
			"api":RenderingServer.get_current_rendering_driver_name(),"renderer":RenderingServer.get_current_rendering_method(),
			"engine":Engine.get_version_info(),"viewport":Array([root.size.x,root.size.y])},
		"input_latency_scope":"Godot scripted InputEvent to first post-draw after state acknowledgement; excludes OS/device/compositor/display",
		"success":errors.is_empty()}
	var file := FileAccess.open(directory.path_join("runtime-report.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  ")+"\n")
	file.close()
	telemetry.close()
	print("VALIDATION_FINISHED ",JSON.stringify({"success":errors.is_empty(),"wall_seconds":measured_s}))
	quit(0 if errors.is_empty() else 1)

func _fail(message: String) -> void:
	errors.append(message)
	push_error(message)
	if not directory.is_empty():
		var file := FileAccess.open(directory.path_join("validation-failure.json"),FileAccess.WRITE)
		if file: file.store_string(JSON.stringify({"errors":errors,"actions":acknowledgements},"  "))
	finishing = true
	quit(1)
