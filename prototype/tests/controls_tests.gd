extends SceneTree

class ControlsOnlyLab:
	extends "res://main.gd"
	func _ready() -> void:
		_build_ui()

class UnhandledKeys:
	extends Node
	var count := 0
	func _unhandled_key_input(_event: InputEvent) -> void:
		count += 1

var lab: ControlsOnlyLab
var failures := 0
var checks := 0

func _initialize() -> void:
	call_deferred("_run")

func _check(label: String, passed: bool, detail: Variant = null) -> void:
	checks += 1
	if not passed:
		failures += 1
	print("PASS " if passed else "FAIL ", label, " ", detail)

func _key(code: Key, physical: bool = true, control: bool = false, echo: bool = false, modifier: String = "") -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code if physical else 0
	event.pressed = true
	event.ctrl_pressed = control
	event.echo = echo
	if not modifier.is_empty():
		event.set(modifier, true)
	Input.parse_input_event(event)
	Input.flush_buffered_events()
	event = event.duplicate()
	event.pressed = false
	event.echo = false
	Input.parse_input_event(event)
	Input.flush_buffered_events()

func _view() -> int:
	return int(lab.display_material.get_shader_parameter("representation"))

func _button(prefix: String) -> Button:
	for child in lab.find_children("*", "Button", true, false):
		if child.text.begins_with(prefix):
			return child
	return null

func _scene() -> Array:
	return [lab.motion_check.button_pressed, lab.lamp_check.button_pressed,
		lab.strobe_check.button_pressed, lab.panel_check.button_pressed,
		lab.sphere_check.button_pressed, lab.light_mode.selected, lab.needs_reset]

func _dirty_scene() -> void:
	lab.motion_check.button_pressed = true
	lab.lamp_check.button_pressed = false
	lab.strobe_check.button_pressed = true
	lab.panel_check.button_pressed = true
	lab.sphere_check.button_pressed = false
	lab.light_mode.select(1)
	lab.needs_reset = false

func _run() -> void:
	root.gui_embed_subwindows = true
	lab = ControlsOnlyLab.new()
	root.add_child(lab)
	await process_frame
	for expected in [1, 2, 3, 0]:
		_key(KEY_V)
		_check("V cycles view %d" % expected, lab.mode_select.selected == expected and _view() == expected, [lab.mode_select.selected, _view()])
	_key(KEY_V, false)
	_check("logical V cycles view", lab.mode_select.selected == 1 and _view() == 1, [lab.mode_select.selected, _view()])
	var before := lab.mode_select.selected
	_key(KEY_V, true, true)
	_check("Ctrl+V leaves view unchanged", lab.mode_select.selected == before, lab.mode_select.selected)
	before = lab.mode_select.selected
	_key(KEY_V, true, false, true)
	_check("V autorepeat leaves view unchanged", lab.mode_select.selected == before, lab.mode_select.selected)
	lab.mode_select.get_popup().popup()
	await process_frame
	before = lab.mode_select.selected
	_key(KEY_V)
	_check("open observation popup owns V", lab.mode_select.selected == before and _view() == before, [lab.mode_select.selected, _view()])
	lab.mode_select.get_popup().hide()
	for index in range(4):
		lab.mode_select.get_popup().index_pressed.emit(index)
		_check("observation UI selects view %d" % index, lab.mode_select.selected == index and _view() == index, [lab.mode_select.selected, _view()])
		_key(KEY_V)
		var expected := (index + 1) % 4
		_check("V continues after UI view %d" % index, lab.mode_select.selected == expected and _view() == expected, [lab.mode_select.selected, _view()])
	for index in range(3):
		lab.mode_select.get_popup().index_pressed.emit(3)
		lab.pause_check.button_pressed = true
		_dirty_scene()
		_key(KEY_1 + index)
		var expected := [index == 2, true, false, false, index != 2, 2 if index == 1 else 0, true]
		var keyboard := _scene()
		_check("scene key %d applies every preset flag" % (index + 1), keyboard == expected, keyboard)
		_dirty_scene()
		_button(str(index + 1) + "   ").pressed.emit()
		_check("scene button %d matches keyboard" % (index + 1), _scene() == keyboard, _scene())
		_check("scene preset preserves observation and pause", lab.mode_select.selected == 3 and _view() == 3 and lab.pause_check.button_pressed)
	for index in range(3):
		lab.light_mode.get_popup().index_pressed.emit(index)
		_key(KEY_L)
		_check("L cycles light mode %d" % index, lab.light_mode.selected == (index + 1) % 3, lab.light_mode.selected)
	for fixture in [[KEY_4, "Light from left", -60.0, 30.0], [KEY_5, "Light from right", 60.0, 30.0], [KEY_6, "Light from above", 0.0, 75.0]]:
		lab.light_mode.select(2)
		lab.needs_reset = false
		_key(fixture[0])
		_check("direction key " + fixture[1], lab.light_mode.selected == 0 and lab.light_azimuth == fixture[2] and lab.light_elevation == fixture[3] and lab.azimuth_slider.value == fixture[2] and lab.elevation_slider.value == fixture[3] and not lab.needs_reset)
		lab.light_mode.select(1)
		_button(fixture[1]).pressed.emit()
		_check("direction button matches " + fixture[1], lab.light_mode.selected == 0 and lab.light_azimuth == fixture[2] and lab.light_elevation == fixture[3] and not lab.needs_reset)
	for fixture in [[KEY_P, lab.pause_check], [KEY_T, lab.strobe_check], [KEY_C, _button("Polarity colors")], [KEY_F, lab.sphere_check], [KEY_M, lab.motion_check], [KEY_B, lab.lamp_check], [KEY_N, lab.panel_check]]:
		var checkbox: CheckBox = fixture[1]
		checkbox.button_pressed = false
		lab.needs_reset = false
		_key(fixture[0])
		_check("toggle on " + checkbox.text, checkbox.button_pressed and not lab.needs_reset)
		_key(fixture[0])
		_check("toggle off " + checkbox.text, not checkbox.button_pressed)
		checkbox.button_pressed = true
		_key(fixture[0], true, false, true)
		_check("autorepeat ignored " + checkbox.text, checkbox.button_pressed)
	var colors: CheckBox = _button("Polarity colors")
	colors.button_pressed = false
	_key(KEY_C)
	_check("C updates shader colors", lab.display_material.get_shader_parameter("polarity_color") == true)
	colors.button_pressed = false
	_check("color UI updates shader", lab.display_material.get_shader_parameter("polarity_color") == false)
	lab.pause_check.button_pressed = true
	lab.needs_reset = false
	var time_before := lab.simulation_time
	_key(KEY_R)
	_check("R requests reset without resuming or changing time", lab.needs_reset and lab.pause_check.button_pressed and lab.simulation_time == time_before)
	lab.needs_reset = false
	var scene_before := _scene()
	_key(KEY_V)
	_check("V preserves scene, pause and sensor reference", _scene() == scene_before and lab.pause_check.button_pressed and lab.simulation_time == time_before)
	for modifier in ["ctrl_pressed", "alt_pressed", "shift_pressed", "meta_pressed"]:
		var unchanged := true
		for code in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_R, KEY_V, KEY_L, KEY_P, KEY_T, KEY_C, KEY_F, KEY_M, KEY_B, KEY_N]:
			var state := [_scene(), lab.mode_select.selected, _view(), lab.pause_check.button_pressed, colors.button_pressed, lab.light_azimuth, lab.light_elevation]
			_key(code, true, false, false, modifier)
			unchanged = unchanged and state == [_scene(), lab.mode_select.selected, _view(), lab.pause_check.button_pressed, colors.button_pressed, lab.light_azimuth, lab.light_elevation]
		_check("modified shortcuts ignored " + modifier, unchanged)
	var unhandled := UnhandledKeys.new()
	root.add_child(unhandled)
	_key(KEY_V)
	_check("handled shortcut press and release do not propagate", unhandled.count == 0, unhandled.count)
	_key(KEY_Z)
	_check("unbound keys still propagate", unhandled.count == 2, unhandled.count)
	await process_frame
	for selector in [lab.mode_select, lab.light_mode]:
		selector.get_popup().popup()
		await process_frame
		_check("popup is open before keyboard test", selector.get_popup().visible)
		var state := [_scene(), lab.mode_select.selected, _view()]
		_key(KEY_1)
		_key(KEY_L)
		_key(KEY_V)
		_check("open popup owns scene and mode keys", state == [_scene(), lab.mode_select.selected, _view()])
		selector.get_popup().hide()
	print("CONTROL_TESTS ", checks - failures, "/", checks, " passed")
	lab.queue_free()
	await process_frame
	quit(1 if failures else 0)
