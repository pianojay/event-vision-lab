extends SceneTree

class ReplayKeyboard extends Node:
	signal pause_requested
	signal restart_requested

	func _input(event: InputEvent) -> void:
		if event is InputEventKey:
			var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
			if key in [KEY_SPACE, KEY_R]:
				if event.pressed and not event.echo:
					if key == KEY_SPACE:
						pause_requested.emit()
					else:
						restart_requested.emit()
				get_viewport().set_input_as_handled()

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
	# Epoch is a JSON string. CSV integer conversion happens before subtraction.
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
	details.text = "%s | %s sensor | %s trajectory\nPixel-emitted capture only. Windowed event counts; no intensity reconstruction.\nStored %d / emitted %d | capture loss %d | refractory suppression %d | readout not modeled" % [config["profile_name"], config["sensor"], config["trajectory"], events.size(), meta["input_count"], meta["overflow_count"], manifest["stages"]["refractory_suppressed"]]
	panel.add_child(details)
	var display := TextureRect.new()
	display.texture = texture
	display.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	display.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	display.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	display.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panel.add_child(display)
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
	root.add_child(keyboard)
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
	var counts := PackedInt32Array()
	var signed_counts := PackedInt32Array()
	counts.resize(image.get_width() * image.get_height())
	signed_counts.resize(counts.size())
	visible_events = 0
	for event in events:
		var event_s: float = event[2] * 1e-9
		if event_s > time_s:
			break
		if event_s > time_s - window_s:
			var index: int = event[1] * image.get_width() + event[0]
			counts[index] += 1
			signed_counts[index] += event[3]
			visible_events += 1
	lit_pixels = 0
	for index in counts.size():
		var gain := 1.0 - exp(-float(counts[index]) * 0.5)
		var color := Color(gain, gain, gain)
		if polarity_color and counts[index] > 0:
			color = Color(gain, gain * 0.55, gain * 0.12) if signed_counts[index] >= 0 else Color(gain * 0.15, gain * 0.65, gain)
		if counts[index] > 0:
			lit_pixels += 1
		image.set_pixel(index % image.get_width(), index / image.get_width(), color)
	texture.update(image)
	scrub.set_value_no_signal(time_s)
	status.text = "%.3f / %.3f ms | %.3fx | %s | %.3f ms window | %d visible events, %d active pixels" % [time_s*1000, duration_s*1000, speed, "playing" if playing else "paused", window_s*1000, visible_events, lit_pixels]
	frame_count += 1
	if verify and frame_count == 5:
		finish_verification.call_deferred()
	return false

func finish_verification() -> void:
	if not await verify_keyboard_controls():
		fail("Routed replay keyboard behavior failed")
		return
	time_s = duration_s * 0.5
	playing = false
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var screenshot_ok := true
	if not capture_path.is_empty():
		screenshot_ok = root.get_texture().get_image().save_png(capture_path) == OK
	var report := {"schema": "event-lab-replay-check-v1", "manifest": manifest_path,
		"stage": "pixel-emitted", "loaded_events": events.size(), "visible_events": visible_events,
		"lit_pixels": lit_pixels, "time_s": time_s, "window_s": window_s,
		"epoch_ns": manifest["captures"]["events"]["epoch_ns"],
		"reads_ground_truth_intensity": false, "screenshot_saved": screenshot_ok,
		"control_checks": control_checks,
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
