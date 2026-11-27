extends RefCounted
const Crossings = preload("res://acquisition/crossings.gd")
const THRESHOLD_CHANGE_POLICY := "reinitialize reference from previous sampled log intensity at interval start; discard prior residual; preserve history and optical state"
var config: Dictionary
var directory := ""
var optical_file: FileAccess
var diagnostic_file: FileAccess
var event_file: FileAccess
var frames: Array = []
var lifecycle: Array = []
var generated := 0
var stored := 0
var clamped := 0
var readback_usec := 0
var error := ""
var last_ns := 0
var source: Dictionary = {}

func begin(path: String, settings: Dictionary) -> bool:
	config = settings.duplicate(true)
	directory = path
	if DirAccess.dir_exists_absolute(path):
		error = "Capture output already exists: " + path
		return false
	if DirAccess.make_dir_recursive_absolute(path) != OK:
		error = "Cannot create capture directory"
		return false
	optical_file = FileAccess.open(path.path_join("intensity.f32"), FileAccess.WRITE)
	diagnostic_file = FileAccess.open(path.path_join("diagnostics.f32"), FileAccess.WRITE)
	event_file = FileAccess.open(path.path_join("events.csv"), FileAccess.WRITE)
	if optical_file == null or diagnostic_file == null or event_file == null:
		error = "Cannot open capture files"
		return false
	event_file.store_line("x,y,t_ns,p,sequence")
	var hashes := {}
	for file in ["main.gd", "sensor_gpu.gd", "shaders/optical.glsl", "shaders/sensor.glsl", "stage/stage_controller.gd", "acquisition/run_config.gd", "acquisition/crossings.gd", "acquisition/capture_writer.gd"]:
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		context.update(FileAccess.get_file_as_string("res://" + file).replace("\r\n","\n").to_utf8_buffer())
		hashes["prototype/" + file] = context.finish().hex_encode()
	source = {"commit": config.source_revision, "source_sha256_lf": hashes, "godot": Engine.get_version_info(), "os": OS.get_name()}
	return true

func append(t_ns: int, reset: bool, parameters: PackedFloat32Array, intensity: PackedFloat32Array, diagnostics: PackedFloat32Array) -> Dictionary:
	if not error.is_empty(): return {"error": error}
	if t_ns < last_ns or t_ns > config.duration_ns or intensity.size() != config.width * config.height or (frames.is_empty() and not reset):
		return fail("Invalid optical frame time, dimensions, or initialization", t_ns)
	for value in intensity:
		if not is_finite(value) or value < 0: return fail("Invalid pre-floor optical intensity", t_ns)
		if value < config.intensity_floor: clamped += 1
	var result := Crossings.expand(diagnostics, Vector2i(config.width,config.height), t_ns if reset else last_ns, t_ns, float(parameters[4]), float(parameters[5]), config.candidate_limit_per_step)
	if result.has("error"):
		var file := FileAccess.open(directory.path_join("failed-intensity.f32"),FileAccess.WRITE)
		file.store_buffer(intensity.to_byte_array())
		file.close()
		file = FileAccess.open(directory.path_join("failed-diagnostics.f32"),FileAccess.WRITE)
		file.store_buffer(diagnostics.to_byte_array())
		file.close()
		var failure := fail(result.error, t_ns)
		file = FileAccess.open(directory.path_join("failed-sample.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify({"time_ns":t_ns,"parameters":Array(parameters),"diagnostic_error":result,"config":config},"  "))
		file.close()
		return failure
	if generated + int(result.generated) > 2000000: return fail("Run exceeds two million generated events",t_ns)
	if reset and result.generated != 0: return fail("Reset emitted events", t_ns)
	var bytes := intensity.to_byte_array()
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	var entry := {"file": "intensity.f32", "offset_bytes": optical_file.get_position(), "length_bytes": bytes.size(), "time_ns": t_ns, "sha256": context.finish().hex_encode(), "reset": reset, "parameters": Array(parameters), "diagnostic_offset_bytes": diagnostic_file.get_position()}
	entry["sensor_thresholds"] = {"on":parameters[4],"off":parameters[5]}
	if not frames.is_empty():
		var previous_parameters: Array = frames[-1].parameters
		if parameters[4] != previous_parameters[4] or parameters[5] != previous_parameters[5]:
			lifecycle.append({"time_ns":t_ns if reset else last_ns,"kind":"threshold-change","effective_frame_time_ns":t_ns,
				"previous_thresholds":{"on":previous_parameters[4],"off":previous_parameters[5]},"thresholds":entry.sensor_thresholds,
				"reference_policy":"explicit reset at current input" if reset else THRESHOLD_CHANGE_POLICY,"material_reset":false})
	optical_file.store_buffer(bytes)
	diagnostic_file.store_buffer(diagnostics.to_byte_array())
	frames.append(entry)
	if reset: lifecycle.append({"time_ns": t_ns, "kind": "new-stream" if frames.size()==1 else "sensor-reset", "material_reset": false})
	for event in result.events:
		if stored < config.capture_capacity:
			event_file.store_line("%d,%d,%d,%d,%d" % [event[0],event[1],int(config.epoch_ns)+event[2],event[3],stored])
			stored += 1
	generated += int(result.generated)
	last_ns = t_ns
	return result

func fail(message: String, t_ns: int) -> Dictionary:
	error = message
	var file := FileAccess.open(directory.path_join("failure.json"), FileAccess.WRITE)
	if file: file.store_string(JSON.stringify({"error": error,"failed_interval": [last_ns,t_ns],"complete": false}, "  "))
	return {"error": error}

func finish(adapter: String) -> Dictionary:
	if not error.is_empty(): return {"error": error}
	if last_ns != config.duration_ns: return fail("Capture ended before scheduled duration", last_ns)
	optical_file.close()
	diagnostic_file.close()
	event_file.close()
	var meta := {"schema":"event-lab-capture-v1","stage":"pixel-emitted","file":"events.csv","width":config.width,"height":config.height,"epoch_ns":config.epoch_ns,"duration_ns":config.duration_ns,"stream_id":config.stream_id,"input_count":generated,"stored_count":stored,"capacity":config.capture_capacity,"overflow_count":generated-stored,"complete_relative_to_stage_input":generated==stored,"overflow_policy":"drop-newest; sensor generation continues","timestamp":"integer epoch plus integer interval origin plus rounded local offset","quantization":"nearest ties-to-even local interval offset","ordering":"interval then unquantized (fraction,y,x,p); stable sequence","polarity":{"on":1,"off":-1},"sha256":FileAccess.get_sha256(directory.path_join("events.csv"))}
	var manifest := {"schema":"event-lab-pipeline-v1","effective_config":config,"source":source,"hardware":{"adapter":adapter},"captures":{"events":meta},
		"optical_input":{"shape":[config.height,config.width],"units":"nonnegative relative scene-linear detector intensity before numerical floor","archive_dtype":"little-endian float32","archive_role":"actual numerical input to GPU and recorded-input CPU adapter","trajectory":"log-linear after floor","intensity_floor":config.intensity_floor,"clamped_sample_values":clamped,"frames":frames,"sample_count":frames.size(),"skipped_scheduled_samples":0,"unobserved_between_sample_changes":"not bounded by endpoint samples"},
		"diagnostics":{"file":"diagnostics.f32","layout":"per pixel 8 FP32 [reference_offset,previous_log_minus_anchor,current_log_minus_anchor,signed_count,prior_on_count,prior_off_count,on_threshold,off_threshold]","sha256":FileAccess.get_sha256(directory.path_join("diagnostics.f32"))},
		"lifecycle":{"records":lifecycle,"reset_policy":"finish interval before same-time reset; preserve optical state and cumulative counters","pause_policy":"freeze acquisition clock; apply queued controls on resume","threshold_change_policy":THRESHOLD_CHANGE_POLICY,"overload_policy":"one scheduled sample at a time; slow simulation without skipping"},
		"stages":{"sensor_candidates":generated,"pixel_emitted":generated,"refractory_suppressed":0,"readout":"not modeled","capture_stored":stored,"capture_overflow":generated-stored,"diagnostic_failed_intervals":0,"complete_relative_to_pixel_emissions":generated==stored},
		"cost":{"synchronous_readback_usec":readback_usec},"limits":["bounded synchronous diagnostic capture, no real-time claim","ideal sensor with numerical floor, no calibrated dark response","analytic matte sphere and hard occlusion; no lens, exposure integration, or indirect transport"]}
	var file := FileAccess.open(directory.path_join("manifest.json"),FileAccess.WRITE)
	if file == null: return fail("Cannot write manifest",last_ns)
	file.store_string(JSON.stringify(manifest,"  ")+"\n")
	file.close()
	return manifest
