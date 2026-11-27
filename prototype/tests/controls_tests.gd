extends SceneTree

class ControlsOnlyLab:
	extends "res://main.gd"
	func _ready() -> void:
		_build_ui()

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

func _key(code: Key, physical: bool = true, control: bool = false, echo: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code if physical else 0
	event.pressed = true
	event.ctrl_pressed = control
	event.echo = echo
	Input.parse_input_event(event)
	Input.flush_buffered_events()
	event = event.duplicate()
	event.pressed = false
	event.echo = false
	Input.parse_input_event(event)
	Input.flush_buffered_events()

func _view() -> int:
	return int(lab.display_material.get_shader_parameter("representation"))

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
	print("CONTROL_TESTS ", checks - failures, "/", checks, " passed")
	lab.queue_free()
	await process_frame
	quit(1 if failures else 0)
