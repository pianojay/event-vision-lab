extends SceneTree
const Runner = preload("res://tests/runtime_scenario.gd")
var checks := 0
var failures := 0
func check(label: String, passed: bool) -> void:
	checks += 1
	if not passed: failures += 1
	print("PASS " if passed else "FAIL ",label)
func _initialize() -> void:
	var effective := {"processing":{"roi":[0,0,80,60],"bin_size":2,"window_capacity":100000,"gain":0.5},"enabled":true}
	var requested: Dictionary = JSON.parse_string(JSON.stringify(effective))
	check("JSON nested settings equal normalized integers",Runner._same_setting(requested,effective))
	var changed := effective.duplicate(true)
	changed.processing.bin_size = 4
	check("different integer setting rejected",not Runner._same_setting(requested,changed))
	changed = effective.duplicate(true)
	changed.processing.gain = 0.5000001
	check("small numeric difference rejected exactly",not Runner._same_setting(requested,changed))
	changed = effective.duplicate(true)
	changed.processing.roi[2] = 79
	check("different nested array value rejected",not Runner._same_setting(requested,changed))
	changed = effective.duplicate(true)
	changed.processing.roi.append(0)
	check("different array shape rejected",not Runner._same_setting(requested,changed))
	changed = effective.duplicate(true)
	changed.processing.erase("gain")
	check("missing setting rejected",not Runner._same_setting(requested,changed))
	changed = effective.duplicate(true)
	changed.processing.extra = 1
	check("unexpected setting rejected",not Runner._same_setting(requested,changed))
	check("boolean cannot match integer",not Runner._same_setting(true,1))
	check("string cannot match number",not Runner._same_setting("2",2))
	check("null setting can match null",Runner._same_setting(null,null))
	print("RUNTIME_ADAPTER_TESTS ",checks-failures,"/",checks)
	quit(1 if failures else 0)
