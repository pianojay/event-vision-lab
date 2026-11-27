extends RefCounted
const Streaming = preload("res://processing/streaming_processor.gd")
var processor = Streaming.new()
var raw = Streaming.new()
var size: Vector2i
var log_estimate := PackedFloat64Array()
var prior := 0.0
var on_threshold := 0.2
var off_threshold := 0.2
var integrated_count := 0
var cursor_ns := 0
var processing_usec := 0
var max_processing_usec := 0
var inference_enabled := false
var last_raw: Dictionary = {}
var last_processed: Dictionary = {}
var reset_count := 0

func configure(sensor_size: Vector2i,settings: Dictionary = {}) -> void:
	size = sensor_size
	processor.configure(settings,size)
	raw.configure({"representation":"window","window_ns":100000000,"window_capacity":100000},size)
	log_estimate.resize(size.x*size.y)
	log_estimate.fill(prior)

func consume(events: Array,t_ns: int) -> void:
	var before := Time.get_ticks_usec()
	raw.consume(events)
	processor.consume(events)
	# Forward contrast integration uses raw events, including those excluded from processing.
	for event in events:
		var index: int = event[1]*size.x+event[0]
		log_estimate[index] += on_threshold if event[3]>0 else -off_threshold
		integrated_count += 1
	cursor_ns = t_ns
	last_raw = raw.snapshot(t_ns)
	last_processed = processor.snapshot(t_ns)
	var cost := Time.get_ticks_usec()-before
	processing_usec += cost
	max_processing_usec = maxi(max_processing_usec,cost)

func reset_sensor(t_ns: int) -> void:
	raw.reset()
	processor.reset()
	reset_prior(t_ns)
	reset_count += 1

func reset_prior(t_ns: int) -> void:
	cursor_ns = t_ns
	log_estimate.fill(prior)
	integrated_count = 0

func image(snapshot: Dictionary) -> Image:
	var dims: Array = snapshot.dimensions
	var data := PackedByteArray()
	data.resize(dims[0]*dims[1]*4)
	for i in dims[0]*dims[1]:
		var divisor: float = snapshot.bin_areas[i] if snapshot.normalization == "per-pixel" else 1.0
		var activity: float = (snapshot.on[i]+snapshot.off[i])/divisor
		var value := int(255.0*(1.0-exp(-processor.config.gain*activity)))
		data[i*4] = value
		data[i*4+1] = value
		data[i*4+2] = value
		data[i*4+3] = 255
	return Image.create_from_data(dims[0],dims[1],false,Image.FORMAT_RGBA8,data)

func reconstruction_image() -> Image:
	var data := PackedByteArray()
	data.resize(size.x*size.y*4)
	for i in log_estimate.size():
		var intensity := exp(clampf(log_estimate[i],-80,80))
		var value := int(255.0*intensity/(1.0+intensity))
		data[i*4] = value
		data[i*4+1] = value
		data[i*4+2] = value
		data[i*4+3] = 255
	return Image.create_from_data(size.x,size.y,false,Image.FORMAT_RGBA8,data)

func metadata() -> Dictionary:
	return {"processing":processor.config,"configuration_generation":processor.configuration_generation,"processing_overflow":processor.window_overflow_count,"raw_window_overflow":raw.window_overflow_count,"resident_event_count":processor.window_count+raw.window_count,"state_cells":log_estimate.size()+processor.on.size()*4+raw.on.size()*4,"processing_usec":processing_usec,"max_processing_usec":max_processing_usec,"inference":{"enabled":inference_enabled,"constant_log_prior":prior,"on_threshold":on_threshold,"off_threshold":off_threshold,"integrated_count":integrated_count,"reads_truth":false,"history":"forward-only per-pixel sum; no event archive; cannot warm from past"},"sensor_reset_count":reset_count}
