extends SceneTree

const Processor = preload("res://processing/event_processor.gd")

func _initialize() -> void:
	var input_path := ""
	var output_path := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--input="):
			input_path = arg.trim_prefix("--input=")
		if arg.begins_with("--output="):
			output_path = arg.trim_prefix("--output=")
	var fixtures: Array = JSON.parse_string(FileAccess.get_file_as_string(input_path))
	var results: Array = []
	for fixture in fixtures:
		var processor = Processor.new()
		var size := Vector2i(fixture.size[0], fixture.size[1])
		processor.configure(fixture.config, size)
		var rows: Array = []
		for row in fixture.events:
			rows.append([int(row[0]), int(row[1]), int(row[2]), int(row[3])])
		processor.consume(rows)
		var snapshots: Array = []
		for cursor in fixture.cursors:
			snapshots.append(processor.snapshot(int(cursor)))
		processor.configure(fixture.get("reconfigure", fixture.config), size)
		snapshots.append(processor.snapshot(int(fixture.cursors[-1])))
		processor.reset()
		snapshots.append(processor.snapshot(int(fixture.cursors[-1])))
		results.append(snapshots)
	var output := FileAccess.open(output_path, FileAccess.WRITE)
	output.store_string(JSON.stringify(results))
	quit()
