extends RefCounted
const PROFILE := "gpu-ideal-log-linear-v1"
const DEFAULTS := {
	"profile_name": PROFILE, "stream_id": "live-3d", "width": 80, "height": 60,
	"duration_ns": 1000000000, "sample_period_ns": 8333333, "epoch_ns": "0",
	"scene": "sphere-light", "on_threshold": 0.2, "off_threshold": 0.2,
	"capture_capacity": 500000, "candidate_limit_per_step": 1000000,
	"reset_times_ns": [], "sensor": "ideal", "trajectory": "log-linear",
	"intensity_floor": 0.000001, "source_revision": "unrecorded"
}
static func parse(overrides: Dictionary) -> Dictionary:
	var config := DEFAULTS.duplicate(true)
	for key in overrides:
		if not config.has(key): return {"error": "Unknown live config field: " + str(key)}
		config[key] = overrides[key]
	if config.profile_name != PROFILE or config.sensor != "ideal" or config.trajectory != "log-linear" or config.intensity_floor != 0.000001:
		return {"error": "Unsupported live sensor, trajectory, or numerical floor"}
	if config.scene not in ["sphere-light", "camera-occlusion", "static", "interactive"]:
		return {"error": "Unsupported stage scenario"}
	for key in ["width", "height", "duration_ns", "sample_period_ns", "capture_capacity", "candidate_limit_per_step"]:
		if typeof(config[key]) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(config[key]) or config[key] != int(config[key]):
			return {"error": "Expected integer: " + key}
		config[key] = int(config[key])
	if config.width < 1 or config.width > 256 or config.height < 1 or config.height > 256 or config.duration_ns < 1 or config.duration_ns > 3600000000000 or config.sample_period_ns < 1 or config.sample_period_ns > config.duration_ns:
		return {"error": "Invalid dimensions or bounded schedule"}
	if config.capture_capacity < 0 or config.capture_capacity > 2000000 or config.candidate_limit_per_step < 1 or config.candidate_limit_per_step > 1000000:
		return {"error": "Invalid capture capacity or interval resource bound"}
	if not config.epoch_ns is String or config.epoch_ns.is_empty() or config.epoch_ns.length() > 19:
		return {"error": "Epoch must be a decimal string"}
	for character in config.epoch_ns:
		if character not in "0123456789": return {"error": "Invalid epoch"}
	var epoch := int(config.epoch_ns)
	if epoch < 0 or epoch > 9223372036854775807 - config.duration_ns or str(epoch) != config.epoch_ns:
		return {"error": "Epoch and duration exceed int64 or epoch is not canonical"}
	if not config.stream_id is String or config.stream_id.strip_edges().is_empty():
		return {"error": "Stream identity required"}
	for key in ["on_threshold", "off_threshold"]:
		if typeof(config[key]) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(config[key]) or config[key] < 0.001 or config[key] > 10:
			return {"error": "Threshold must be finite within [0.001,10]"}
		# Match the exact parameter passed to the GPU, including asymmetric thresholds.
		config[key] = PackedFloat32Array([config[key]])[0]
	if not config.reset_times_ns is Array: return {"error": "Reset schedule must be an array"}
	var previous := 0
	for value in config.reset_times_ns:
		if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or value != int(value) or value <= previous or value >= config.duration_ns:
			return {"error": "Reset times must be increasing interior integers"}
		previous = int(value)
	var frames: int = ceili(float(config.duration_ns) / config.sample_period_ns) + 1 + config.reset_times_ns.size() * 2
	if frames > 10000 or frames * config.width * config.height > 10000000:
		return {"error": "Optical archive exceeds ten million sample values or ten thousand frames"}
	return {"config": config}

static func schedule(config: Dictionary) -> Array:
	var times: Array = [0]
	var time := int(config.sample_period_ns)
	while time < config.duration_ns:
		times.append(time)
		time += int(config.sample_period_ns)
	times.append(int(config.duration_ns))
	for reset_time in config.reset_times_ns:
		if not times.has(int(reset_time)): times.append(int(reset_time))
	times.sort()
	return times

