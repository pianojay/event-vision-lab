extends SceneTree

class ReplayKeyboard extends Node:
	signal pause_requested
	signal restart_requested
	signal processing_requested(action: String)

	func _input(event: InputEvent) -> void:
		if event is InputEventKey:
			if event.ctrl_pressed or event.alt_pressed or event.meta_pressed or event.shift_pressed:
				return
			if get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is SpinBox:
				return
			if get_viewport().gui_get_focus_owner() is OptionButton and get_viewport().gui_get_focus_owner().get_popup().visible:
				return
			var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
			if key in [KEY_SPACE, KEY_R, KEY_B, KEY_O, KEY_V, KEY_F, KEY_E]:
				if event.pressed and not event.echo:
					if key == KEY_SPACE:
						pause_requested.emit()
					elif key == KEY_R:
						restart_requested.emit()
					else:
						processing_requested.emit({KEY_B: "bin_size", KEY_O: "polarity", KEY_V: "representation", KEY_F: "full", KEY_E: "empty"}[key])
				get_viewport().set_input_as_handled()

const Processor = preload("res://processing/event_processor.gd")

var processor = Processor.new()
var raw_processor = Processor.new()
var raw_image: Image
var raw_texture: ImageTexture
var processing_snapshot: Dictionary
var processing_controls: Dictionary = {}
var roi_controls: Array = []
var settings_path := "user://event-processing.json"
var settings_path_control: LineEdit
var settings_status: Label

var manifest: Dictionary
var events: Array = []
var image: Image
var texture: ImageTexture
var status: Label
var scrub: HSlider
var time_s := 0.0
var duration_s := 0.0
var speed := 0.1
var playing := true
var polarity_color := false
var window_s := 0.04
var verify := false
var capture_path := ""
var report_path := ""
var manifest_path := ""
var frame_count := 0
var visible_events := 0
var lit_pixels := 0
var ready := false
var load_failed := false
var pause_button: Button
var control_checks: Array = []

func toggle_playback() -> void:
	playing = not playing

func restart_playback() -> void:
	time_s = 0.0
	playing = true

func fail(message: String) -> void:
	push_error(message)
	load_failed = true
	quit(1)

func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--manifest="):
			manifest_path = arg.trim_prefix("--manifest=")
		elif arg.begins_with("--capture="):
			capture_path = arg.trim_prefix("--capture=")
		elif arg.begins_with("--report="):
			report_path = arg.trim_prefix("--report=")
		elif arg.begins_with("--processing-config="):
			settings_path = arg.trim_prefix("--processing-config=")
		elif arg == "--verify":
			verify = true
	if manifest_path.is_empty():
		fail("Replay requires --manifest=<pipeline manifest.json>")
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not parsed is Dictionary or parsed.get("schema", "") != "event-lab-pipeline-v1":
		fail("Unsupported or invalid pipeline manifest")
		return
	manifest = parsed
	var meta: Dictionary = manifest.get("captures", {}).get("events", {})
	if meta.get("schema", "") != "event-lab-capture-v1" or meta.get("stage", "") != "pixel-emitted":
		fail("Replay accepts only pixel-emitted capture stage")
		return
	var width := int(meta.get("width", 0))
	var height := int(meta.get("height", 0))
	var duration_ns := int(meta.get("duration_ns", 0))
	if width < 1 or height < 1 or width > 256 or height > 256 or duration_ns <= 0:
		fail("Invalid replay dimensions or duration")
		return
	var epoch_text = meta.get("epoch_ns", "")
	if not epoch_text is String or not epoch_text.is_valid_int():
		fail("Epoch must be a decimal integer string")
		return
	for character in epoch_text:
		if character not in "0123456789":
			fail("Epoch must contain only decimal digits")
			return
	var stream_id = meta.get("stream_id")
	var polarity = meta.get("polarity")
	if not stream_id is String or stream_id.strip_edges().is_empty():
		fail("Capture needs a nonempty stream identity")
		return
	if not polarity is Dictionary or polarity.size() != 2 or polarity.get("on") != 1 or polarity.get("off") != -1 or typeof(polarity.get("on")) == TYPE_BOOL or typeof(polarity.get("off")) == TYPE_BOOL:
		fail("Capture requires ON +1 and OFF -1 polarity convention")
		return
	if typeof(meta.get("complete_relative_to_stage_input")) != TYPE_BOOL:
		fail("Capture completeness must be a boolean")
		return
	var epoch: int = epoch_text.to_int()
	if epoch < 0 or epoch > 9223372036854775807 - duration_ns:
		fail("Epoch and duration exceed signed int64 clock")
		return
	var input_count := int(meta.get("input_count", -1))
	var stored_count := int(meta.get("stored_count", -1))
	var overflow_count := int(meta.get("overflow_count", -1))
	var capacity := int(meta.get("capacity", -1))
	if input_count < 0 or stored_count < 0 or overflow_count < 0 or capacity < 0 or stored_count != mini(input_count, capacity) or overflow_count != input_count - stored_count or meta.get("complete_relative_to_stage_input") != (overflow_count == 0):
		fail("Inconsistent capture capacity or completeness metadata")
		return
	if meta.get("file", "") != "events.csv":
		fail("Expected events.csv within run directory")
		return
	var event_path := manifest_path.get_base_dir().path_join(str(meta.get("file", "")))
	if FileAccess.get_sha256(event_path) != meta.get("sha256", ""):
		fail("Event capture hash mismatch")
		return
	var file := FileAccess.open(event_path, FileAccess.READ)
	if file == null or file.get_csv_line() != PackedStringArray(["x", "y", "t_ns", "p", "sequence"]):
		fail("Invalid event CSV header")
		return
	var previous := epoch
	while file.get_position() < file.get_length():
		var row := file.get_csv_line()
		if row.size() != 5:
			fail("Malformed event CSV row")
			return
		for item in row:
			if not item.is_valid_int():
				fail("Event CSV needs integer fields")
				return
		var x := row[0].to_int()
		var y := row[1].to_int()
		var absolute_ns := row[2].to_int()
		var p := row[3].to_int()
		if x < 0 or x >= width or y < 0 or y >= height or p not in [-1, 1] or absolute_ns < previous or absolute_ns - epoch > duration_ns or row[4].to_int() != events.size():
			fail("Invalid event coordinate, polarity, timestamp or sequence")
			return
		events.append([x, y, absolute_ns - epoch, p])
		previous = absolute_ns
	if events.size() != int(meta.get("stored_count", -1)) or int(meta.get("input_count", -1)) != events.size() + int(meta.get("overflow_count", -1)):
		fail("Event count disagrees with capture metadata")
		return
	duration_s = duration_ns * 1e-9
	window_s = min(0.04, duration_s * 0.2)
	processor.configure({"window_ns": maxi(1, roundi(window_s * 1e9))}, Vector2i(width, height))
	processor.consume(events)
	raw_processor.configure(processor.config, Vector2i(width, height))
	raw_processor.consume(events)
	raw_image = Image.create(width, height, false, Image.FORMAT_RGB8)
	raw_image.fill(Color.BLACK)
	raw_texture = ImageTexture.create_from_image(raw_image)
	image = Image.create(width, height, false, Image.FORMAT_RGB8)
	image.fill(Color.BLACK)
	texture = ImageTexture.create_from_image(image)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	root.add_child(margin)
	var panel := VBoxContainer.new()
	panel.add_theme_constant_override("separation", 14)
	margin.add_child(panel)
	var heading := Label.new()
	heading.text = "Event Vision Lab | recorded event replay"
	heading.add_theme_font_size_override("font_size", 28)
	panel.add_child(heading)
	var details := Label.new()
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var config: Dictionary = manifest["effective_config"]
	details.text = "%s | %s sensor | %s trajectory\nPixel-emitted capture. Post-event ROI → binning → polarity → temporal view. Controls retain sensor and raw capture state.\nStored %d / emitted %d | capture loss %d | refractory suppression %d | readout not modeled" % [config["profile_name"], config["sensor"], config["trajectory"], events.size(), meta["input_count"], meta["overflow_count"], manifest["stages"]["refractory_suppressed"]]
	panel.add_child(details)
	build_processing_controls(panel)
	var views := HBoxContainer.new()
	views.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panel.add_child(views)
	add_event_view(views, "Raw full-frame event window", raw_texture)
	add_event_view(views, "Processed events | ROI-local bins", texture)
	status = Label.new()
	panel.add_child(status)
	scrub = HSlider.new()
	scrub.min_value = 0
	scrub.max_value = duration_s
	scrub.step = 0
	scrub.value_changed.connect(func(value): time_s = value; playing = false)
	panel.add_child(scrub)
	var controls := HBoxContainer.new()
	panel.add_child(controls)
	pause_button = Button.new()
	pause_button.text = "Play / pause [Space]"
	pause_button.pressed.connect(toggle_playback)
	controls.add_child(pause_button)
	var restart := Button.new()
	restart.text = "Replay from start [R]"
	restart.pressed.connect(restart_playback)
	controls.add_child(restart)
	var slower := Button.new()
	slower.text = "Slower"
	slower.pressed.connect(func(): speed = max(0.001, speed * 0.5))
	controls.add_child(slower)
	var faster := Button.new()
	faster.text = "Faster"
	faster.pressed.connect(func(): speed = min(10.0, speed * 2.0))
	controls.add_child(faster)
	var colors := CheckBox.new()
	colors.text = "ON / OFF colors"
	colors.toggled.connect(func(value): polarity_color = value)
	controls.add_child(colors)
	var keyboard := ReplayKeyboard.new()
	keyboard.pause_requested.connect(toggle_playback)
	keyboard.restart_requested.connect(restart_playback)
	keyboard.processing_requested.connect(cycle_processing)
	root.add_child(keyboard)
	if FileAccess.file_exists(settings_path):
		load_processing_settings()
	if verify:
		time_s = duration_s * 0.5
		playing = false
	ready = true

func _process(delta: float) -> bool:
	if not ready or load_failed:
		return false
	if playing:
		time_s += delta * speed
		if time_s > duration_s:
			time_s = 0.0
	var cursor_ns := roundi(time_s * 1e9)
	processing_snapshot = processor.snapshot(cursor_ns)
	var dimensions: Array = processing_snapshot.dimensions
	var output_size := Vector2i(maxi(1, dimensions[0]), maxi(1, dimensions[1]))
	if image.get_size() != output_size:
		image = Image.create(output_size.x, output_size.y, false, Image.FORMAT_RGB8)
		texture.set_image(image)
	render_snapshot(processing_snapshot, image, processor.config, polarity_color)
	texture.update(image)
	var raw_config: Dictionary = processor.config.duplicate(true)
	raw_config.roi = [0, 0, raw_image.get_width(), raw_image.get_height()]
	raw_config.bin_size = 1
	raw_config.polarity = "both"
	raw_config.representation = "window"
	raw_config.normalization = "count"
	raw_processor.configure(raw_config, raw_image.get_size())
	render_snapshot(raw_processor.snapshot(cursor_ns), raw_image, raw_config, polarity_color)
	raw_texture.update(raw_image)
	visible_events = processing_snapshot.visible_count
	lit_pixels = 0
	for index in processing_snapshot.on.size():
		if processing_snapshot.on[index] + processing_snapshot.off[index] > 0:
			lit_pixels += 1
	scrub.set_value_no_signal(time_s)
	window_s = processor.config.window_ns * 1e-9
	status.text = "%.3f / %.3f ms | %.3fx | %s | incoming %d → ROI %d → polarity %d | %d contributing events, %d bins\n%s | window %.3f ms | decay tau %.3f ms | origin (%d,%d), bin %d | sensor/capture unchanged" % [time_s*1000, duration_s*1000, speed, "playing" if playing else "paused", processing_snapshot.incoming_count, processing_snapshot.roi_count, processing_snapshot.selected_count, visible_events, lit_pixels, processor.config.representation, window_s*1000, processor.config.tau_ns*1e-6, processing_snapshot.origin[0], processing_snapshot.origin[1], processor.config.bin_size]
	frame_count += 1
	if verify and frame_count == 5:
		finish_verification.call_deferred()
	return false

func finish_verification() -> void:
	if not await verify_keyboard_controls():
		fail("Routed replay keyboard behavior failed")
		return
	if not await verify_processing_controls():
		fail("Replay processing controls failed")
		return
	time_s = duration_s * 0.5
	playing = false
	await process_frame
	await process_frame
	var screenshot_ok := true
	if not capture_path.is_empty():
		await RenderingServer.frame_post_draw
		screenshot_ok = root.get_texture().get_image().save_png(capture_path) == OK
	var report := {"schema": "event-lab-replay-check-v1", "manifest": manifest_path,
		"stage": "pixel-emitted", "loaded_events": events.size(), "visible_events": visible_events,
		"lit_pixels": lit_pixels, "time_s": time_s, "window_s": window_s,
		"epoch_ns": manifest["captures"]["events"]["epoch_ns"],
		"reads_ground_truth_intensity": false, "screenshot_saved": not capture_path.is_empty() and screenshot_ok,
		"control_checks": control_checks, "processing_config": processor.config,
		"processing_snapshot": processing_snapshot,
		"renderer": RenderingServer.get_video_adapter_name(), "godot": Engine.get_version_info()["string"]}
	if not report_path.is_empty():
		var output := FileAccess.open(report_path, FileAccess.WRITE)
		if output == null:
			fail("Cannot write replay report")
			return
		output.store_string(JSON.stringify(report, "  ") + "\n")
	print(JSON.stringify(report))
	quit(0 if screenshot_ok else 1)

func send_key(key: Key, pressed: bool, echo := false) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = key
	event.keycode = key
	event.pressed = pressed
	event.echo = echo
	Input.parse_input_event(event)

func verify_keyboard_controls() -> bool:
	pause_button.grab_focus()
	send_key(KEY_SPACE, true)
	send_key(KEY_SPACE, false)
	await process_frame
	await process_frame
	control_checks.append({"action": "Space resumes with Play button focused", "passed": "| playing |" in status.text})
	send_key(KEY_SPACE, true, true)
	send_key(KEY_SPACE, false)
	await process_frame
	await process_frame
	control_checks.append({"action": "Space autorepeat does not toggle", "passed": "| playing |" in status.text})
	send_key(KEY_SPACE, true)
	send_key(KEY_SPACE, false)
	await process_frame
	await process_frame
	var paused_status := status.text
	await process_frame
	await process_frame
	control_checks.append({"action": "Space pauses once and clock stays fixed", "passed": "| paused |" in status.text and status.text == paused_status})
	var saved_speed := speed
	speed = 0.0
	send_key(KEY_R, true)
	send_key(KEY_R, false)
	await process_frame
	await process_frame
	control_checks.append({"action": "R restarts and resumes paused replay", "passed": "| playing |" in status.text and scrub.value == 0.0})
	speed = saved_speed
	for check in control_checks:
		if not check["passed"]:
			return false
	return true

func add_event_view(parent: Control, title: String, view_texture: ImageTexture) -> void:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(column)
	var label := Label.new()
	label.text = title
	column.add_child(label)
	var view := TextureRect.new()
	view.texture = view_texture
	view.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(view)

func build_processing_controls(panel: VBoxContainer) -> void:
	var roi_row := HBoxContainer.new()
	panel.add_child(roi_row)
	var roi_label := Label.new()
	roi_label.text = "ROI [x0,y0,x1,y1) sensor pixels"
	roi_row.add_child(roi_label)
	for index in 4:
		var spin := SpinBox.new()
		spin.min_value = 0
		spin.max_value = processor.sensor_size.x if index % 2 == 0 else processor.sensor_size.y
		spin.value = processor.config.roi[index]
		spin.value_changed.connect(func(value): set_roi_bound(index, int(value)))
		roi_controls.append(spin)
		roi_row.add_child(spin)
	for action in ["full", "empty"]:
		var button := Button.new()
		button.text = "Full [F]" if action == "full" else "Empty [E]"
		button.pressed.connect(func(): cycle_processing(action))
		processing_controls[action] = button
		roi_row.add_child(button)
	var choices := HBoxContainer.new()
	panel.add_child(choices)
	for spec in [["bin_size", [1, 2, 4], ["1×1 [B]", "2×2 [B]", "4×4 [B]"]],
		["polarity", ["both", "on", "off"], ["Both [O]", "ON only [O]", "OFF only [O]"]],
		["representation", ["window", "decay", "time-surface"], ["Exact window [V]", "Decaying counts [V]", "Time surface [V]"]],
		["normalization", ["count", "per-pixel"], ["Sum per bin", "Divide by bin area"]]]:
		var selector := OptionButton.new()
		for label in spec[2]:
			selector.add_item(label)
		selector.item_selected.connect(func(index): apply_processing(spec[0], spec[1][index]))
		processing_controls[spec[0]] = selector
		choices.add_child(selector)
	var temporal := HBoxContainer.new()
	panel.add_child(temporal)
	for spec in [["window_ns", "Window ms"], ["tau_ns", "Decay tau ms"], ["gain", "Display gain"]]:
		var label := Label.new()
		label.text = spec[1]
		temporal.add_child(label)
		var spin := SpinBox.new()
		spin.min_value = 0.000001 if spec[0] != "gain" else 0.001
		spin.max_value = 1000000
		spin.step = spin.min_value
		spin.custom_minimum_size.x = 125
		spin.value_changed.connect(func(value): apply_processing(spec[0], roundi(value * 1e6) if spec[0] != "gain" else value))
		processing_controls[spec[0]] = spin
		temporal.add_child(spin)
	var save_row := HBoxContainer.new()
	panel.add_child(save_row)
	settings_path_control = LineEdit.new()
	settings_path_control.text = settings_path
	settings_path_control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	save_row.add_child(settings_path_control)
	for action in ["Save settings", "Load settings"]:
		var button := Button.new()
		button.text = action
		button.pressed.connect(save_processing_settings if action == "Save settings" else load_processing_settings)
		save_row.add_child(button)
	settings_status = Label.new()
	settings_status.text = "Changes recompute captured history. Color and gain affect display only."
	panel.add_child(settings_status)
	sync_processing_controls()

func set_roi_bound(index: int, value: int) -> void:
	var roi: Array = processor.config.roi.duplicate()
	roi[index] = value
	if index < 2:
		roi[index + 2] = maxi(roi[index + 2], value)
	else:
		roi[index - 2] = mini(roi[index - 2], value)
	apply_processing("roi", roi)

func apply_processing(key: String, value: Variant) -> void:
	var settings: Dictionary = processor.config.duplicate(true)
	settings[key] = value
	processor.configure(settings, processor.sensor_size)
	sync_processing_controls()

func cycle_processing(action: String) -> void:
	if action in ["full", "empty"]:
		apply_processing("roi", [0, 0, processor.sensor_size.x, processor.sensor_size.y] if action == "full" else [0, 0, 0, 0])
		return
	var choices: Array = {"bin_size": [1, 2, 4], "polarity": ["both", "on", "off"], "representation": ["window", "decay", "time-surface"]}[action]
	apply_processing(action, choices[(choices.find(processor.config[action]) + 1) % choices.size()])

func sync_processing_controls() -> void:
	for index in roi_controls.size():
		roi_controls[index].set_value_no_signal(processor.config.roi[index])
	for key in ["bin_size", "polarity", "representation", "normalization"]:
		var choices: Array = {"bin_size": [1, 2, 4], "polarity": ["both", "on", "off"], "representation": ["window", "decay", "time-surface"], "normalization": ["count", "per-pixel"]}[key]
		processing_controls[key].select(choices.find(processor.config[key]))
	for key in ["window_ns", "tau_ns", "gain"]:
		processing_controls[key].set_value_no_signal(processor.config[key] * 1e-6 if key != "gain" else processor.config[key])

func save_processing_settings() -> void:
	settings_path = settings_path_control.text
	var file := FileAccess.open(settings_path, FileAccess.WRITE)
	if file == null:
		settings_status.text = "Could not save settings"
		return
	file.store_string(JSON.stringify(processor.config, "  ") + "\n")
	settings_status.text = "Saved processing settings to " + settings_path

func load_processing_settings() -> void:
	settings_path = settings_path_control.text
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(settings_path))
	if not valid_processing_settings(parsed):
		settings_status.text = "Invalid processing settings. Current settings retained."
		return
	processor.configure(parsed, processor.sensor_size)
	sync_processing_controls()
	settings_status.text = "Loaded settings and recomputed captured history"

func valid_processing_settings(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	for key in value:
		if not processor.config.has(key):
			return false
	var merged: Dictionary = processor.config.duplicate(true)
	merged.merge(value, true)
	var roi = merged.roi
	if not roi is Array or roi.size() != 4:
		return false
	for bound in roi:
		if typeof(bound) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(bound) or floor(bound) != bound:
			return false
	if roi[0] < 0 or roi[1] < 0 or roi[0] > roi[2] or roi[1] > roi[3] or roi[2] > processor.sensor_size.x or roi[3] > processor.sensor_size.y:
		return false
	if typeof(merged.bin_size) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(merged.bin_size) or floor(merged.bin_size) != merged.bin_size:
		return false
	if int(merged.bin_size) not in [1, 2, 4] or merged.polarity not in ["both", "on", "off"] or merged.representation not in ["window", "decay", "time-surface"] or merged.normalization not in ["count", "per-pixel"]:
		return false
	for key in ["window_ns", "tau_ns", "gain"]:
		if typeof(merged[key]) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(merged[key]) or merged[key] <= 0 or merged[key] > 1e15:
			return false
		if key != "gain" and floor(merged[key]) != merged[key]:
			return false
	return true

func render_snapshot(snapshot: Dictionary, target: Image, settings: Dictionary, colors: bool) -> void:
	target.fill(Color.BLACK)
	for index in snapshot.on.size():
		var divisor: float = snapshot.bin_areas[index] if settings.normalization == "per-pixel" else 1.0
		var on: float = snapshot.on[index] / divisor
		var off: float = snapshot.off[index] / divisor
		var gain := 1.0 - exp(-(on + off) * settings.gain)
		var color := Color(gain, gain, gain)
		if colors and on + off > 0:
			color = Color(1.0, 0.55, 0.12).lerp(Color(0.15, 0.65, 1.0), off / (on + off)) * gain
		target.set_pixel(index % target.get_width(), index / target.get_width(), color)

func verify_processing_controls() -> bool:
	playing = false
	var original: Dictionary = processor.config.duplicate(true)
	var raw_rows := events.duplicate(true)
	var count := events.size()
	processing_controls.bin_size.item_selected.emit(1)
	control_checks.append({"action": "Bin selector selects 2x2", "passed": processor.config.bin_size == 2})
	pause_button.grab_focus()
	send_key(KEY_B, true)
	send_key(KEY_B, false)
	await process_frame
	control_checks.append({"action": "B uses same bin configuration route", "passed": processor.config.bin_size == 4})
	processing_controls.polarity.item_selected.emit(1)
	control_checks.append({"action": "ON selector filters events", "passed": processor.config.polarity == "on" and processor.snapshot(roundi(duration_s*1e9)).off.all(func(value): return value == 0)})
	send_key(KEY_O, true)
	send_key(KEY_O, false)
	await process_frame
	control_checks.append({"action": "O selects OFF independently of color", "passed": processor.config.polarity == "off" and not polarity_color})
	processing_controls.representation.item_selected.emit(1)
	send_key(KEY_V, true)
	send_key(KEY_V, false)
	await process_frame
	control_checks.append({"action": "V and selector cycle temporal representation", "passed": processor.config.representation == "time-surface"})
	processing_controls.empty.pressed.emit()
	control_checks.append({"action": "Empty ROI keeps incoming events", "passed": processor.snapshot(roundi(duration_s*1e9)).selected_count == 0 and processor.events.size() == count})
	send_key(KEY_F, true)
	send_key(KEY_F, false)
	await process_frame
	control_checks.append({"action": "F restores full sensor bounds", "passed": processor.config.roi == [0, 0, processor.sensor_size.x, processor.sensor_size.y]})
	roi_controls[0].value = mini(1, processor.sensor_size.x)
	control_checks.append({"action": "ROI spin control changes half-open bounds", "passed": processor.config.roi[0] == mini(1, processor.sensor_size.x)})
	processing_controls.window_ns.value = 12.5
	processing_controls.tau_ns.value = 25.0
	control_checks.append({"action": "Temporal controls convert milliseconds to nanoseconds", "passed": processor.config.window_ns == 12500000 and processor.config.tau_ns == 25000000})
	var reference: Dictionary = processor.snapshot(roundi(duration_s*0.5e9))
	scrub.value = duration_s * 0.75
	scrub.value = duration_s * 0.5
	speed = 4.0
	await process_frame
	control_checks.append({"action": "Scrub pauses and speed preserves event-time snapshot", "passed": not playing and processing_snapshot == reference})
	if not report_path.is_empty():
		var saved_path := settings_path_control.text
		settings_path_control.text = report_path + ".settings.json"
		save_processing_settings()
		cycle_processing("full")
		load_processing_settings()
		control_checks.append({"action": "Saved configuration restores identical event-time result", "passed": processor.snapshot(roundi(duration_s*0.5e9)) == reference})
		settings_path_control.text = saved_path
	control_checks.append({"action": "Processing controls preserve raw capture rows", "passed": events == raw_rows and processor.events == raw_rows and raw_processor.events == raw_rows})
	processor.configure(original, processor.sensor_size)
	sync_processing_controls()
	speed = 0.1
	for check in control_checks:
		if not check.passed:
			return false
	return true
