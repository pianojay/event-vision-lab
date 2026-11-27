extends RefCounted

const Processor = preload("res://processing/event_processor.gd")

var history = Processor.new()
var config: Dictionary
var reset_ns := -1

func configure(settings: Dictionary, size: Vector2i) -> void:
	var next := {"initial_log_intensity": 0.0, "on_threshold": 0.2, "off_threshold": 0.2}
	for key in settings:
		assert(next.has(key), "Unknown reconstruction setting")
		next[key] = settings[key]
	for key in next:
		assert(typeof(next[key]) in [TYPE_INT, TYPE_FLOAT] and is_finite(next[key]))
		assert(key == "initial_log_intensity" or next[key] > 0)
	history.configure({}, size)
	config = next.duplicate(true)

func consume(events: Array) -> void:
	history.consume(events)

func reset(timestamp_ns: int = -1) -> void:
	assert(timestamp_ns >= -1)
	reset_ns = timestamp_ns
	history.reset()

func snapshot(cursor_ns: int) -> Dictionary:
	assert(cursor_ns >= 0)
	var size: Vector2i = history.sensor_size
	var log_intensity: Array = []
	var support: Array = []
	log_intensity.resize(size.x * size.y)
	support.resize(size.x * size.y)
	log_intensity.fill(float(config.initial_log_intensity))
	support.fill(0)
	var integrated := 0
	var latest := -1
	for event in history.events:
		if event[2] > cursor_ns:
			break
		if event[2] <= reset_ns:
			continue
		var index: int = event[1] * size.x + event[0]
		log_intensity[index] += config.on_threshold if event[3] == 1 else -config.off_threshold
		support[index] += 1
		integrated += 1
		latest = event[2]
	var intensity: Array = []
	var clipped := 0
	var observed := 0
	for index in log_intensity.size():
		var value: float = log_intensity[index]
		if value < -80 or value > 80:
			clipped += 1
		intensity.append(exp(clampf(value, -80, 80)))
		if support[index] > 0:
			observed += 1
	return {"dimensions": [size.x, size.y], "cursor_ns": cursor_ns, "reset_ns": reset_ns,
		"log_intensity": log_intensity, "relative_intensity": intensity, "support": support,
		"integrated_count": integrated, "observed_pixels": observed,
		"latest_event_age_ns": null if latest < 0 else cursor_ns - latest,
		"elapsed_since_reset_ns": maxi(0, cursor_ns - maxi(0, reset_ns)),
		"clipped_intensity_pixels": clipped, "reads_ground_truth": false}
