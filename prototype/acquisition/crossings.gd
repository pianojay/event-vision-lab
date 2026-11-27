extends RefCounted

# Rows are [x, y, relative_ns, polarity]. Fractions are sorted before rounding.
static func expand(values: PackedFloat32Array, size: Vector2i, start_ns: int, end_ns: int, on: float, off: float, limit: int = 1000000) -> Dictionary:
	var stride := 8 if values.size() == size.x * size.y * 8 else 4
	if size.x < 1 or size.y < 1 or values.size() != size.x * size.y * stride or start_ns < 0 or end_ns < start_ns or not is_finite(on) or not is_finite(off) or on <= 0 or off <= 0:
		return {"error": "Invalid diagnostic interval"}
	var crossings: Array = []
	var count := 0
	for i in range(0, values.size(), stride):
		for j in stride:
			if not is_finite(values[i + j]):
				return {"error": "Nonfinite diagnostic value"}
		var signed_count := int(values[i + 3])
		if values[i + 3] != signed_count:
			return {"error": "Noninteger crossing count"}
		count += absi(signed_count)
		if count > limit:
			return {"error": "Diagnostic interval exceeds event resource limit"}
		var polarity := 1 if signed_count >= 0 else -1
		var threshold := on if polarity == 1 else off
		var delta := float(values[i + 2]) - float(values[i + 1])
		for level in range(1, absi(signed_count) + 1):
			var level_delta := PackedFloat32Array([polarity * level * threshold])[0]
			var crossing := PackedFloat32Array([float(values[i]) + level_delta])[0]
			if stride == 8:
				var on_level := PackedFloat32Array([(values[i+4]+(level if polarity>0 else 0))*values[i+6]])[0]
				var off_level := PackedFloat32Array([(values[i+5]+(level if polarity<0 else 0))*values[i+7]])[0]
				crossing = PackedFloat32Array([on_level-off_level])[0]
			var fraction := (crossing - float(values[i + 1])) / delta if absf(delta) > 1e-10 else 1.0
			if fraction < 0.0 or fraction > 1.0:
				return {"error": "Crossing outside declared interval", "detail": {"pixel_index": i/stride, "reference":values[i], "previous":values[i+1], "current":values[i+2], "signed_count":signed_count, "threshold":threshold, "level":level, "fraction":fraction}}
			crossings.append([clampf(fraction, 0.0, 1.0), (i / stride) % size.x, (i / stride) / size.x, polarity])
	crossings.sort_custom(func(a, b):
		if a[0] != b[0]: return a[0] < b[0]
		if a[2] != b[2]: return a[2] < b[2]
		if a[1] != b[1]: return a[1] < b[1]
		return a[3] < b[3])
	var events: Array = []
	for crossing in crossings:
		var offset := round_even(crossing[0] * (end_ns - start_ns))
		events.append([int(crossing[1]), int(crossing[2]), start_ns + offset, crossing[3]])
	return {"events": events, "generated": count}

static func round_even(value: float) -> int:
	var lower := floori(value)
	var fraction := value - lower
	return lower + int(fraction > 0.5 or (fraction == 0.5 and lower % 2 != 0))
