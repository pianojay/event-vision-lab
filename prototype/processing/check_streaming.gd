extends SceneTree

const Streaming = preload("res://processing/streaming_processor.gd")

func _initialize() -> void:
	var source := ""
	var target := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--input="):
			source = arg.trim_prefix("--input=")
		if arg.begins_with("--output="):
			target = arg.trim_prefix("--output=")
	var fixtures: Array = JSON.parse_string(FileAccess.get_file_as_string(source))
	var results: Array = []
	for fixture in fixtures:
		var stream = Streaming.new()
		var size := Vector2i(fixture.size[0], fixture.size[1])
		stream.configure(fixture.config, size)
		var snapshots: Array = []
		for operation in fixture.operations:
			if operation.has("config"):
				stream.configure(operation.config, size)
			if operation.has("reset"):
				stream.reset()
			var rows: Array = []
			for event in operation.get("events", []):
				rows.append([int(event[0]), int(event[1]), int(event[2]), int(event[3])])
			stream.consume(rows)
			snapshots.append(stream.snapshot(int(operation.cursor)))
		results.append(snapshots)
	var output := FileAccess.open(target, FileAccess.WRITE)
	output.store_string(JSON.stringify(results))
	quit()
