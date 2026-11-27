extends SceneTree
const Crossings = preload("res://acquisition/crossings.gd")
const Config = preload("res://acquisition/run_config.gd")
const Writer = preload("res://acquisition/capture_writer.gd")
const Stage = preload("res://stage/stage_controller.gd")
class ControlsOnlyLab:
	extends "res://main.gd"
	func _ready() -> void: _build_ui()
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
	result = Crossings.expand(PackedFloat32Array([0.638227581977844,0.443717420101166,0.438228875398636,-1]),Vector2i(1,1),308333321,316666654,PackedFloat32Array([0.2])[0],PackedFloat32Array([0.2])[0])
	check("unreached threshold from real camera counterexample rejected",result.has("error"))
	check("nonfinite threshold rejected", Crossings.expand(PackedFloat32Array([0,0,0,0]),Vector2i(1,1),0,1,NAN,0.2).has("error"))
	check("invalid dimensions rejected", Crossings.expand(PackedFloat32Array(),Vector2i(0,1),0,1,0.2,0.2).has("error"))
	check("default named profile", Config.parse({}).config.profile_name == "gpu-ideal-log-linear-v1")
	for override in [{"sensor":"generic-nonideal"},{"trajectory":"held"},{"intensity_floor":0},{"unknown":1},{"width":true},{"on_threshold":NAN},{"epoch_ns":"9223372036854775808"},{"reset_times_ns":[5,4]},{"sample_period_ns":1}]:
		check("incompatible config rejected " + str(override), Config.parse(override).has("error"))
	var config: Dictionary = Config.parse({"width":1,"height":1,"duration_ns":1000,"sample_period_ns":600,"reset_times_ns":[500],"on_threshold":0.25,"off_threshold":0.25,"capture_capacity":2,"epoch_ns":"9000000000000000000"}).config
	check("schedule includes end and reset exactly", Config.schedule(config) == [0,500,600,1000])
	var json_config: Dictionary = Config.parse(JSON.parse_string(JSON.stringify(config))).config
	check("JSON requested reset matches integer acquisition cursor", json_config.reset_times_ns.has(500))
	check("threshold is effective GPU float", Config.parse({"on_threshold":0.2}).config.on_threshold == PackedFloat32Array([0.2])[0])
	var path := ProjectSettings.globalize_path("res://../runs/acquisition-headless-" + str(Time.get_ticks_usec()))
	var writer := Writer.new()
	check("capture begins",writer.begin(path,config))
	var params := Stage.parameters(config,0,0,true)
	result = writer.append(0,true,params,PackedFloat32Array([1]),PackedFloat32Array([0,0,0,0]))
	check("initial sample is silent",result.events.is_empty())
	params = Stage.parameters(config,1000,0,false)
	result = writer.append(1000,false,params,PackedFloat32Array([exp(1.0)]),PackedFloat32Array([0,0,1,4]))
	check("all emissions available despite capture overflow",result.events.size()==4)
	params[2] = 1
	result = writer.append(1000,true,params,PackedFloat32Array([exp(1.0)]),PackedFloat32Array([1,1,1,0]))
	check("same-time reset after interval is silent",result.events.is_empty())
	var manifest := writer.finish("headless contract test; no GPU")
	check("drop-newest separated from generation",manifest.stages.pixel_emitted==4 and manifest.stages.capture_stored==2 and manifest.stages.capture_overflow==2)
	check("overflow completeness false",not manifest.captures.events.complete_relative_to_stage_input)
	var csv := FileAccess.get_file_as_string(path.path_join("events.csv"))
	check("integer epoch exported without float conversion",csv.contains("9000000000000000250") and csv.contains("9000000000000000500"))
	var bounded := Writer.new()
	check("resource probe begins",bounded.begin(path+"-limit",config))
	bounded.append(0,true,Stage.parameters(config,0,0,true),PackedFloat32Array([1]),PackedFloat32Array([0,0,0,0]))
	bounded.generated = 1999999
	result = bounded.append(1000,false,Stage.parameters(config,1000,0,false),PackedFloat32Array([exp(1.0)]),PackedFloat32Array([0,0,1,4]))
	check("total resource guard aborts before float counter precision loss",result.has("error") and not FileAccess.file_exists((path+"-limit").path_join("manifest.json")))
	var transitions := Writer.new()
	check("threshold capture begins",transitions.begin(path+"-threshold",config))
	transitions.append(0,true,Stage.parameters(config,0,0,true),PackedFloat32Array([1]),PackedFloat32Array([0,0,0,0]))
	params = Stage.parameters(config,500,0,false)
	params[4] = 0.125
	transitions.append(500,false,params,PackedFloat32Array([exp(0.3)]),PackedFloat32Array([0,0,0.3,2,0,0,0.125,0.25]))
	params = Stage.parameters(config,1000,500,false)
	params[4] = 0.5
	transitions.append(1000,false,params,PackedFloat32Array([exp(0.3)]),PackedFloat32Array([0,0,0,0,0,0,0.5,0.25]))
	var changed := transitions.finish("headless threshold contract; no GPU")
	check("threshold lifecycle records effective interval start",changed.lifecycle.records.size()==3 and changed.lifecycle.records[1].kind=="threshold-change" and changed.lifecycle.records[1].time_ns==0 and changed.lifecycle.records[1].effective_frame_time_ns==500)
	check("per-frame threshold values remain explicit",changed.optical_input.frames[1].get("sensor_thresholds",{})=={"on":0.125,"off":0.25})
	check("threshold edits preserve already captured events",changed.captures.events.input_count==2 and changed.captures.events.stored_count==2)
	var second := Writer.new()
	check("existing capture never overwritten",not second.begin(path,config))
	var sphere0 := Stage.parameters(config,0,0,false)
	var sphere1 := Stage.parameters(config,1000000000,0,false)
	check("sphere remains fixed while light moves",sphere0.slice(8,12)==sphere1.slice(8,12) and sphere0.slice(24,27)!=sphere1.slice(24,27))
	config.scene = "camera-occlusion"
	var camera1 := Stage.parameters(config,1000000000,0,false)
	check("camera path enables geometric occluder",camera1[8]!=sphere0[8] and camera1[27]==1)
	var lab := ControlsOnlyLab.new()
	lab._build_ui()
	lab.live_config = config
	lab.capture_schedule = [0,1000]
	lab.pause_check.button_pressed = true
	lab.needs_reset = true
	lab._process_acquisition(100.0)
	check("pause freezes cursor and pending reset",lab.capture_index==0 and lab.simulation_time==0 and lab.needs_reset)
	lab.lamp_check.button_pressed = false
	lab.live_config.scene = "interactive"
	params = lab._interactive_capture_parameters(1000,0,false)
	check("paused optical edit reaches next input",params[17]==0 and lab.needs_reset)
	lab.needs_reset = false
	var threshold_slider: HSlider
	for slider in lab.find_children("*","HSlider",true,false):
		if slider.min_value == 0.02 and slider.max_value == 0.6: threshold_slider = slider
	threshold_slider.value = 0.1
	lab._process_acquisition(100.0)
	check("paused threshold edit dispatches nothing and requests no full reset",lab.capture_index==0 and lab.simulation_time==0 and not lab.needs_reset)
	lab.pause_check.button_pressed = false
	params = lab._interactive_capture_parameters(1000,0,false)
	check("resume parameters carry edited asymmetric thresholds",params[4]==PackedFloat32Array([0.1])[0] and params[5]==PackedFloat32Array([0.1*config.off_threshold/config.on_threshold])[0])
	lab.free()
	print("ACQUISITION_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
