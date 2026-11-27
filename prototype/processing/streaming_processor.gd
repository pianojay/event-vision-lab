extends RefCounted

const Processor = preload("res://processing/event_processor.gd")

var config: Dictionary = {}
var sensor_size: Vector2i
var dimensions: Vector2i
var configuration_generation := 0
var clock_ns := -1
var on: Array = []
var off: Array = []
var last_on: PackedInt64Array
var last_off: PackedInt64Array
var window_times: PackedInt64Array
var window_indices: PackedInt32Array
var window_polarities: PackedByteArray
var window_head := 0
var window_count := 0
var incoming_count := 0
var roi_count := 0
var selected_count := 0
var window_overflow_count := 0

func configure(settings: Dictionary, size: Vector2i) -> void:
	var next: Dictionary = settings.duplicate(true)
	var capacity_value = next.get("window_capacity", 100000)
	assert(typeof(capacity_value) in [TYPE_INT, TYPE_FLOAT] and is_finite(capacity_value) and floor(capacity_value) == capacity_value)
	assert(capacity_value >= 1 and capacity_value <= 1000000)
	var capacity: int = int(capacity_value)
	next.erase("window_capacity")
	var validator = Processor.new()
	validator.configure(next, size)
	next = validator.config
	next.window_capacity = capacity
	var clear := config.is_empty() or size != sensor_size
	for key in next:
		if key not in ["gain", "normalization"] and config.get(key) != next[key]:
			clear = true
	config = next
	sensor_size = size
	var roi: Array = config.roi
	dimensions = Vector2i(ceili(float(roi[2] - roi[0]) / config.bin_size), ceili(float(roi[3] - roi[1]) / config.bin_size))
	if clear:
		var previous_clock := clock_ns
		reset()
		clock_ns = previous_clock
		configuration_generation += 1

func reset() -> void:
	var cells := dimensions.x * dimensions.y
	on.resize(cells)
	off.resize(cells)
	on.fill(0)
	off.fill(0)
	last_on.resize(cells)
	last_off.resize(cells)
	last_on.fill(-1)
	last_off.fill(-1)
	var capacity: int = config.window_capacity if config.representation == "window" else 0
	window_times.resize(capacity)
	window_indices.resize(capacity)
	window_polarities.resize(capacity)
	window_head = 0
	window_count = 0
	clock_ns = -1
	incoming_count = 0
	roi_count = 0
	selected_count = 0
	window_overflow_count = 0

func advance(cursor_ns: int) -> void:
	assert(cursor_ns >= maxi(0, clock_ns), "Streaming clock cannot move backward")
	if config.representation == "window":
		var boundary: int = cursor_ns - config.window_ns
		while window_count > 0 and window_times[window_head] <= boundary:
			var output: Array = on if window_polarities[window_head] == 1 else off
			output[window_indices[window_head]] -= 1
			window_head = (window_head + 1) % config.window_capacity
			window_count -= 1
	clock_ns = cursor_ns

func consume(events: Array) -> void:
	var previous := maxi(0, clock_ns)
	for event in events:
		assert(event.size() == 4)
		for value in event:
			assert(typeof(value) == TYPE_INT)
		assert(event[0] >= 0 and event[0] < sensor_size.x and event[1] >= 0 and event[1] < sensor_size.y)
		assert(event[2] >= previous and event[3] in [-1, 1], "Invalid, late, or unsorted event")
		previous = event[2]
	var roi: Array = config.roi
	var b: int = config.bin_size
	for event in events:
		var timestamp: int = event[2]
		advance(timestamp)
		incoming_count += 1
		if event[0] < roi[0] or event[0] >= roi[2] or event[1] < roi[1] or event[1] >= roi[3]:
			continue
		roi_count += 1
		if (config.polarity == "on" and event[3] < 0) or (config.polarity == "off" and event[3] > 0):
			continue
		selected_count += 1
		var index: int = floori(float(event[1] - roi[1]) / b) * dimensions.x + floori(float(event[0] - roi[0]) / b)
		var output: Array = on if event[3] == 1 else off
		var latest_time: int = last_on[index] if event[3] == 1 else last_off[index]
		if config.representation == "window":
			if window_count == config.window_capacity:
				window_overflow_count += 1
				continue
			var tail: int = (window_head + window_count) % config.window_capacity
			window_times[tail] = timestamp
			window_indices[tail] = index
			window_polarities[tail] = 1 if event[3] == 1 else 0
			window_count += 1
			output[index] += 1
		elif config.representation == "decay":
			output[index] = (output[index] * exp(-float(timestamp - latest_time) / config.tau_ns) if latest_time >= 0 else 0.0) + 1.0
		if event[3] == 1:
			last_on[index] = timestamp
		else:
			last_off[index] = timestamp

func snapshot(cursor_ns: int) -> Dictionary:
	advance(cursor_ns)
	var result_on: Array = on.duplicate()
	var result_off: Array = off.duplicate()
	if config.representation != "window":
		for index in on.size():
			result_on[index] = (on[index] if config.representation == "decay" else 1.0) * exp(-float(cursor_ns - last_on[index]) / config.tau_ns) if last_on[index] >= 0 else 0.0
			result_off[index] = (off[index] if config.representation == "decay" else 1.0) * exp(-float(cursor_ns - last_off[index]) / config.tau_ns) if last_off[index] >= 0 else 0.0
	var areas: Array = []
	var roi: Array = config.roi
	var b: int = config.bin_size
	for y in dimensions.y:
		for x in dimensions.x:
			areas.append(mini(b, roi[2] - roi[0] - x*b) * mini(b, roi[3] - roi[1] - y*b))
	return {"dimensions": [dimensions.x, dimensions.y], "origin": [roi[0], roi[1]], "bin_size": b,
		"on": result_on, "off": result_off, "bin_areas": areas, "cursor_ns": cursor_ns,
		"representation": config.representation, "normalization": config.normalization,
		"received_count": incoming_count, "incoming_count": incoming_count, "roi_count": roi_count,
		"polarity_count": selected_count, "selected_count": selected_count,
		"visible_count": window_count if config.representation == "window" else selected_count,
		"resident_event_count": window_count, "window_capacity": config.window_capacity,
		"window_overflow_count": window_overflow_count, "complete_since_reset": window_overflow_count == 0,
		"configuration_generation": configuration_generation, "state_cells": on.size() * 4}
