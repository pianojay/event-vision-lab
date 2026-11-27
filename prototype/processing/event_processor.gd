extends RefCounted

var config: Dictionary
var sensor_size: Vector2i
var events: Array = []

func configure(settings: Dictionary, size: Vector2i) -> void:
	assert(size.x > 0 and size.y > 0)
	assert(events.is_empty() or size == sensor_size, "Reset before changing dimensions")
	var next := {"roi": [0, 0, size.x, size.y], "bin_size": 1, "polarity": "both",
		"representation": "window", "window_ns": 40000000, "tau_ns": 40000000,
		"normalization": "count", "gain": 0.5}
	for key in settings:
		assert(next.has(key), "Unknown processing setting")
		next[key] = settings[key]
	next = next.duplicate(true)
	for key in ["bin_size", "window_ns", "tau_ns"]:
		assert(typeof(next[key]) in [TYPE_INT, TYPE_FLOAT] and floor(next[key]) == next[key])
		next[key] = int(next[key])
	var roi: Array = next.roi
	assert(roi.size() == 4)
	for index in 4:
		assert(typeof(roi[index]) in [TYPE_INT, TYPE_FLOAT] and floor(roi[index]) == roi[index])
		roi[index] = int(roi[index])
	assert(roi[0] >= 0 and roi[1] >= 0 and roi[0] <= roi[2] and roi[1] <= roi[3] and roi[2] <= size.x and roi[3] <= size.y)
	assert(next.bin_size in [1, 2, 4])
	assert(next.polarity in ["both", "on", "off"])
	assert(next.representation in ["window", "decay", "time-surface"])
	assert(next.normalization in ["count", "per-pixel"])
	assert(next.window_ns > 0 and next.tau_ns > 0 and is_finite(next.gain) and next.gain > 0)
	config = next.duplicate(true)
	sensor_size = size

func consume(rows: Array) -> void:
	var previous: int = events[-1][2] if not events.is_empty() else 0
	for row in rows:
		assert(row.size() == 4)
		assert(row[0] >= 0 and row[0] < sensor_size.x and row[1] >= 0 and row[1] < sensor_size.y)
		assert(row[2] >= previous and row[3] in [-1, 1])
		previous = row[2]
	events.append_array(rows.duplicate(true))

func reset() -> void:
	events.clear()

func snapshot(cursor_ns: int) -> Dictionary:
	assert(cursor_ns >= 0)
	var roi: Array = config.roi
	var b: int = config.bin_size
	var width := ceili(float(roi[2] - roi[0]) / b)
	var height := ceili(float(roi[3] - roi[1]) / b)
	var on: Array = []
	var off: Array = []
	on.resize(width * height)
	off.resize(width * height)
	on.fill(0)
	off.fill(0)
	var incoming := 0
	var retained := 0
	var selected := 0
	var visible := 0
	for row in events:
		if row[2] > cursor_ns:
			break
		incoming += 1
		if row[0] < roi[0] or row[0] >= roi[2] or row[1] < roi[1] or row[1] >= roi[3]:
			continue
		retained += 1
		if (config.polarity == "on" and row[3] < 0) or (config.polarity == "off" and row[3] > 0):
			continue
		selected += 1
		var age: int = cursor_ns - row[2]
		if config.representation == "window" and age >= config.window_ns:
			continue
		visible += 1
		var index: int = floori(float(row[1] - roi[1]) / b) * width + floori(float(row[0] - roi[0]) / b)
		var output: Array = on if row[3] > 0 else off
		if config.representation == "window":
			output[index] += 1
		else:
			var value := exp(-float(age) / config.tau_ns)
			output[index] = maxf(output[index], value) if config.representation == "time-surface" else output[index] + value
	var areas: Array = []
	for y in height:
		for x in width:
			areas.append(mini(b, roi[2] - roi[0] - x*b) * mini(b, roi[3] - roi[1] - y*b))
	return {"dimensions": [width, height], "origin": [roi[0], roi[1]], "bin_size": b,
		"on": on, "off": off, "bin_areas": areas, "received_count": events.size(),
		"incoming_count": incoming, "roi_count": retained, "polarity_count": selected,
		"selected_count": selected, "visible_count": visible, "cursor_ns": cursor_ns,
		"representation": config.representation, "normalization": config.normalization}
