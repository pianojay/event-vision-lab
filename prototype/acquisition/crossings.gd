extends RefCounted

# Rows are [x, y, relative_ns, polarity]. Fractions are sorted before rounding.
static func expand(values: PackedFloat32Array, size: Vector2i, start_ns: int, end_ns: int, on: float, off: float, limit: int = 1000000) -> Dictionary:
	if values.size() != size.x * size.y * 4 or start_ns < 0 or end_ns < start_ns or on <= 0 or off <= 0:
		return {"error": "Invalid diagnostic interval"}
	var crossings: Array = []
	var count := 0
	for i in range(0, values.size(), 4):
		for j in 4:
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
			var fraction := (float(values[i]) + polarity * level * threshold - float(values[i + 1])) / delta if absf(delta) > 1e-10 else 1.0
			if fraction < -0.0001 or fraction > 1.0001:
				return {"error": "Crossing outside declared interval"}
			crossings.append([clampf(fraction, 0.0, 1.0), (i / 4) % size.x, (i / 4) / size.x, polarity])
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
