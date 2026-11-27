extends SceneTree
const Stage = preload("res://stage/interaction_stage.gd")
const Controller = preload("res://stage/stage_controller.gd")
const Config = preload("res://acquisition/run_config.gd")
const Live = preload("res://stage/live_perception.gd")
const Offline = preload("res://processing/contrast_integrator.gd")
class Controls:
	extends "res://main.gd"
	func _ready() -> void: _build_ui()
var checks := 0
var failed := 0
func check(label: String,ok: bool) -> void:
	checks += 1
	if not ok: failed += 1
	print("PASS " if ok else "FAIL ",label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var stage := Stage.new()
	check("registry accepts all station defaults",stage.valid_parameters(Stage.DEFAULTS))
	for index in 9:
		stage.selected=index
		check("registry accepts parameter endpoints "+str(index),stage.set_primary(Stage.PRIMARY_RANGE[index][0]) and stage.set_primary(Stage.PRIMARY_RANGE[index][1]))
		stage.reset_station(index)
	stage=Stage.new()
	for i in 9:
		check("station registered "+Stage.IDS[i],stage.registry.models.any(func(m): return m.id==Stage.IDS[i]))
		var config: Dictionary = Config.parse({"scene":"interaction-stage","station":i,"stage_action":"static"}).config
		var a := Controller.interaction_parameters(config,0,0,true,stage)
		var b := Controller.interaction_parameters(config,16666667,0,false,stage)
		check("76 parameter stage shape "+str(i),a.size()==76 and b.size()==76)
		stage = Stage.new()
	check("diagnostic ten-minute bound remains",Config.parse({"duration_ns":600000000000}).has("error"))
	check("stream permits ten minutes",not Config.parse({"archive_mode":"stream","duration_ns":600000000000}).has("error"))
	check("unknown station rejected",Config.parse({"station":9}).has("error"))
	stage.advance(100000000,4.0)
	stage.advance(200000000,0.0)
	var energy: float = stage.population.stored_energy
	check("causal population charges",energy>0.0)
	stage.advance(300000000,0.0)
	check("material decays after source off",stage.population.stored_energy<energy and stage.population.stored_energy>0.0)
	stage.reset_station(1)
	check("other station reset preserves phosphor",stage.population.stored_energy>0.0)
	stage.reset_station(6)
	check("phosphor reset clears population",stage.population.stored_energy==0.0)
	var live := Live.new()
	live.configure(Vector2i(4,3),{"roi":[0,0,2,2],"bin_size":2,"polarity":"on"})
	live.on_threshold = 0.21
	live.off_threshold = 0.13
	var offline := Offline.new()
	offline.configure({"on_threshold":0.21,"off_threshold":0.13},Vector2i(4,3))
	var events: Array = [[0,0,10,1],[3,2,20,-1],[0,0,30,-1],[2,1,30,1]]
	for batch in [events.slice(0,2),events.slice(2)]:
		live.consume(batch,batch[-1][2])
		offline.consume(batch)
	var expected: Array = offline.snapshot(30).log_intensity
	check("forward inference matches offline raw contrast",Array(live.log_estimate)==expected)
	check("ROI does not remove inference inputs",live.integrated_count==4 and live.processor.selected_count==1)
	var before := live.log_estimate.duplicate()
	live.processor.configure({"roi":[1,1,4,3],"bin_size":1,"polarity":"off"},Vector2i(4,3))
	check("processing changes preserve inference",live.log_estimate==before)
	live.reset_sensor(30)
	check("sensor reset starts explicit constant prior",live.integrated_count==0 and live.log_estimate[0]==0)
	var lab := Controls.new()
	root.add_child(lab)
	lab.perception.configure(Vector2i(80,60),{"representation":"decay"})
	lab.sensor_size = Vector2i(80,60)
	lab.stage_check.button_pressed = true
	lab._focus_station(7)
	check("focus routes to station geometry",lab.interaction_stage.selected==7 and lab.camera_position==Stage.center(7)+Vector3(0,0,3))
	lab.shortcut_actions[KEY_X].call()
	check("comparison key uses same toggle",not lab.comparison_check.button_pressed and not lab.interaction_stage.treatment)
	lab.perception.consume([[3,2,1,1]],1)
	lab.acquisition_cursor_ns = 1
	lab.shortcut_actions[KEY_G].call()
	check("bin key applies bounded processing",lab.perception.processor.config.bin_size==2)
	lab.shortcut_actions[KEY_Y].call()
	check("polarity key applies processing",lab.perception.processor.config.polarity=="on")
	lab.shortcut_actions[KEY_U].call()
	check("temporal key applies processing",lab.perception.processor.config.representation=="window")
	lab.shortcut_actions[KEY_I].call()
	check("inference key changes optional view",lab.perception.inference_enabled)
	lab.interaction_stage.advance(100000000,4.0)
	lab.interaction_stage.advance(200000000,4.0)
	energy=lab.interaction_stage.population.stored_energy
	lab.shortcut_actions[KEY_R].call()
	check("sensor reset preserves optical population",lab.interaction_stage.population.stored_energy==energy)
	check("default reduced flashes shader enabled",lab.reduced_flashes and bool(lab.display_material.get_shader_parameter("reduced_flashes")))
	check("all preview limiters enabled",[lab.raw_panel,lab.processing_panel,lab.reconstruction_panel].all(func(panel):return bool(panel.material.get_shader_parameter("reduced_flashes"))))
	lab._set_reduced_flashes(false)
	check("display opt-out preserves optical state",not lab.reduced_flashes and lab.interaction_stage.population.stored_energy==energy)
	var saved_reference: bool = lab.needs_reset
	lab._set_mode(3)
	check("V truth view retains sensor/material",lab.needs_reset==saved_reference and lab.interaction_stage.population.stored_energy==energy)
	lab.live_config = {"scene":"interaction-stage"}
	var input := InputEventKey.new()
	input.physical_keycode = KEY_G
	input.pressed = true
	lab._input(input)
	check("prescribed trajectory permits processing shortcut",lab.perception.processor.config.bin_size==4)
	input.physical_keycode = KEY_I
	lab._input(input)
	check("prescribed trajectory permits inference shortcut",not lab.perception.inference_enabled)
	check("post-event scalar controls remain separately marked",lab.get_tree().get_nodes_in_group("post_event_control").size()==4)
	lab.queue_free()
	print("INTERACTION_STAGE_TESTS ",checks-failed,"/",checks)
	quit(1 if failed else 0)
