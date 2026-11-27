extends SceneTree
const Crossings = preload("res://acquisition/crossings.gd")
var failures := 0
var checks := 0
func check(label: String, passed: bool) -> void:
	checks += 1
	if not passed: failures += 1
	print("PASS " if passed else "FAIL ", label)
func _initialize() -> void:
	var result := Crossings.expand(PackedFloat32Array([0,0,1,4]), Vector2i(1,1), 9000000000000000, 9000000000001000, 0.25, 0.25)
	check("all crossing levels retain large integer interval origin", result.events == [[0,0,9000000000000250,1],[0,0,9000000000000500,1],[0,0,9000000000000750,1],[0,0,9000000000001000,1]])
	result = Crossings.expand(PackedFloat32Array([1,1,0,-4]), Vector2i(1,1), 0,1000,0.25,0.25)
	check("OFF crossings and endpoint", result.events.size() == 4 and result.events[-1] == [0,0,1000,-1])
	result = Crossings.expand(PackedFloat32Array([0,0,1,4]), Vector2i(1,1),0,1000,0.25,0.25,3)
	check("resource guard fails whole interval", result.has("error") and not result.has("events"))
	result = Crossings.expand(PackedFloat32Array([0,0,0,0]), Vector2i(1,1),0,0,0.25,0.25)
	check("reset has no emissions", result.events.is_empty())
	result = Crossings.expand(PackedFloat32Array([0,0,1,1,0,0,1,1]), Vector2i(2,1),0,1,0.25,0.25)
	check("quantized ties retain spatial order", result.events == [[0,0,0,1],[1,0,0,1]])
	check("ties to even", Crossings.round_even(0.5)==0 and Crossings.round_even(1.5)==2 and Crossings.round_even(2.5)==2)
	result = Crossings.expand(PackedFloat32Array([0,0,NAN,1]),Vector2i(1,1),0,1,0.2,0.2)
	check("invalid diagnostics rejected", result.has("error"))
	print("ACQUISITION_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
