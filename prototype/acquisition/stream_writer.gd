extends RefCounted
const Crossings = preload("res://acquisition/crossings.gd")
const DiagnosticWriter = preload("res://acquisition/capture_writer.gd")
var config: Dictionary
var directory := ""
var event_file: FileAccess
var generated := 0
var stored := 0
var readback_usec := 0
var last_ns := 0
var sample_count := 0
var error := ""
var source: Dictionary = {}
var first_parameters: Array = []
var last_parameters: Array = []
var threshold_changes := 0
var resets := 0
var max_pixel_counter := 0.0
var wall_start_usec := 0

func begin(path: String,settings: Dictionary) -> bool:
	config = settings.duplicate(true)
	directory = path
	wall_start_usec = Time.get_ticks_usec()
	if not path.is_empty():
		if DirAccess.dir_exists_absolute(path):
			error = "Capture output already exists: "+path
			return false
		if DirAccess.make_dir_recursive_absolute(path) != OK:
			error = "Cannot create capture directory"
			return false
		event_file = FileAccess.open(path.path_join("events.csv"),FileAccess.WRITE)
		if event_file == null:
			error = "Cannot open bounded event output"
			return false
		event_file.store_line("x,y,t_ns,p,sequence")
	var hashes := {}
	for file in ["main.gd","sensor_gpu.gd","shaders/optical.glsl","shaders/sensor.glsl","shaders/interaction_stage.glsl","shaders/material_models.glsl","stage/interaction_stage.gd","stage/stage_controller.gd","materials/registry.json","materials/emission_state.gd","acquisition/run_config.gd","acquisition/crossings.gd","acquisition/stream_writer.gd","processing/streaming_processor.gd","stage/live_perception.gd"]:
		hashes[file] = FileAccess.get_sha256("res://"+file)
	source = {"commit":config.source_revision,"source_sha256":hashes,"godot":Engine.get_version_info(),"os":OS.get_name()}
	return true

func append(t_ns: int,reset: bool,parameters: PackedFloat32Array,_intensity: PackedFloat32Array,diagnostics: PackedFloat32Array) -> Dictionary:
	if t_ns < last_ns or t_ns > config.duration_ns or (sample_count==0 and not reset): return fail("Invalid streaming clock or initialization",t_ns)
	# Fail before the anchored FP32 integer counts lose exactness. Do not silently reset the sensor.
	for index in range(0,diagnostics.size(),8):
		max_pixel_counter = maxf(max_pixel_counter,maxf(diagnostics[index+4],diagnostics[index+5])+absf(diagnostics[index+3]))
	if max_pixel_counter >= 8000000: return fail("Per-pixel exact counter safety bound reached",t_ns)
	var result := Crossings.expand(diagnostics,Vector2i(config.width,config.height),t_ns if reset else last_ns,t_ns,parameters[4],parameters[5],config.candidate_limit_per_step)
	if result.has("error"): return fail(result.error,t_ns)
	if reset and result.generated != 0: return fail("Reset emitted events",t_ns)
	if first_parameters.is_empty(): first_parameters = Array(parameters)
	if not last_parameters.is_empty() and (last_parameters[4]!=parameters[4] or last_parameters[5]!=parameters[5]): threshold_changes += 1
	last_parameters = Array(parameters)
	if reset: resets += 1
	for event in result.events:
		if event_file != null and stored < config.capture_capacity:
			event_file.store_line("%d,%d,%d,%d,%d" % [event[0],event[1],int(config.epoch_ns)+event[2],event[3],stored])
			stored += 1
	generated += int(result.generated)
	last_ns = t_ns
	sample_count += 1
	return result

func fail(message: String,t_ns: int) -> Dictionary:
	error = message
	if not directory.is_empty():
		var file := FileAccess.open(directory.path_join("failure.json"),FileAccess.WRITE)
		if file: file.store_string(JSON.stringify({"error":error,"failed_interval":[last_ns,t_ns],"complete":false}))
	return {"error":error}

func finish(adapter: String) -> Dictionary:
	if not error.is_empty(): return {"error":error}
	if event_file: event_file.close()
	var meta := {"schema":"event-lab-capture-v1","stage":"pixel-emitted","file":"events.csv","width":config.width,"height":config.height,"epoch_ns":config.epoch_ns,"duration_ns":last_ns,"stream_id":config.stream_id,"input_count":generated,"stored_count":stored,"capacity":config.capture_capacity,"overflow_count":generated-stored,"complete_relative_to_stage_input":generated==stored,"overflow_policy":"drop-newest; live processor receives all events","polarity":{"on":1,"off":-1},"ordering":"interval then unquantized (fraction,y,x,p); stable sequence"}
	if not directory.is_empty(): meta.sha256 = FileAccess.get_sha256(directory.path_join("events.csv"))
	var wall_s := (Time.get_ticks_usec()-wall_start_usec)*1e-6
	var manifest := {"schema":"event-lab-pipeline-v1","effective_config":config,"source":source,"hardware":{"adapter":adapter},"captures":{"events":meta},"optical_input":{"archived":false,"sample_count":sample_count,"skipped_scheduled_samples":0,"first_parameters":first_parameters,"last_parameters":last_parameters},"lifecycle":{"sensor_resets":resets,"threshold_changes":threshold_changes,"threshold_change_policy":DiagnosticWriter.THRESHOLD_CHANGE_POLICY,"material_reset":false,"overload_policy":"slow simulation without skipping; integer host cursor"},"stages":{"pixel_emitted":generated,"capture_stored":stored,"capture_overflow":generated-stored if not directory.is_empty() else 0,"capture_not_requested":generated if directory.is_empty() else 0,"event_expansion_loss":0,"sensor_model_loss":0,"stage_sample_skips":0,"readout":"not modeled"},"cost":{"synchronous_readback_usec":readback_usec,"elapsed_wall_seconds":wall_s,"elapsed_sim_seconds":last_ns*1e-9,"samples_per_wall_second":sample_count/maxf(wall_s,0.000001),"events_per_wall_second":generated/maxf(wall_s,0.000001),"max_pixel_counter":max_pixel_counter},"limits":["No optical or diagnostic archive; use diagnostic mode for independent parity","FP32 optical phase and legacy GPU display timestamps; host event timestamps are integer","No calibrated camera or real-time promise"]}
	if directory.is_empty(): manifest.captures = {}
	if not directory.is_empty():
		var file := FileAccess.open(directory.path_join("manifest.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify(manifest,"  "))
	return manifest
