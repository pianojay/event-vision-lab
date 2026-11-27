extends SceneTree

const Layout = preload("res://tests/runtime_layout.gd")
class ControlsOnlyLab:
	extends "res://main.gd"
	func _ready() -> void:
		_build_ui()

var failures := 0
var checks := 0

func check(label: String, passed: bool, detail: Variant = null) -> void:
	checks += 1
	if not passed: failures += 1
	print("PASS " if passed else "FAIL ",label," ",detail)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280,800)
	var lab := Layout.instantiate_lab()
	lab.set_script(ControlsOnlyLab)
	root.add_child(lab)
	for frame in range(4): await process_frame
	var composed: bool = lab.get("raw_panel") != null
	var result := Layout.snapshot(lab,composed)
	check("Configured main scene fills viewport with a visible observation and sidebar",result.valid,result)
	check("Main scene retains its resource identity",lab.scene_file_path == "res://main.tscn")
	if composed:
		lab.raw_panel.hide()
		check("Hidden raw event pane fails layout evidence",not Layout.snapshot(lab).valid)
		lab.raw_panel.show()
		lab.processing_panel.hide()
		check("Hidden processing pane fails layout evidence",not Layout.snapshot(lab).valid)
		lab.processing_panel.show()
		lab.perception.inference_enabled = true
		lab.reconstruction_panel.hide()
		check("Enabled but hidden inference pane fails layout evidence",not Layout.snapshot(lab).valid)
		lab.perception.inference_enabled = false
		check("Disabled inference pane can be hidden",Layout.snapshot(lab).valid)
		lab.reconstruction_panel.show()
	lab.canvas.hide()
	check("Hidden main observation fails layout evidence",not Layout.snapshot(lab,composed).valid)
	lab.canvas.show()
	lab.canvas.size = Vector2.ZERO
	check("Collapsed main observation fails layout evidence",not Layout.snapshot(lab,composed).valid)
	lab.queue_free()
	await process_frame
	var old_lab := ControlsOnlyLab.new()
	root.add_child(old_lab)
	for frame in range(4): await process_frame
	check("Script-only startup without scene anchors fails layout evidence",not Layout.snapshot(old_lab,composed).valid)
	old_lab.queue_free()
	await process_frame
	print("RUNTIME_LAYOUT_TESTS ",checks-failures,"/",checks)
	quit(1 if failures else 0)
