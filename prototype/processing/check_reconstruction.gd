extends SceneTree

const Reconstructor = preload("res://processing/contrast_integrator.gd")

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
		var model = Reconstructor.new()
		model.configure(fixture.config, Vector2i(fixture.size[0], fixture.size[1]))
		var rows: Array = []
		for row in fixture.events:
			rows.append([int(row[0]), int(row[1]), int(row[2]), int(row[3])])
		model.consume(rows)
		var snapshots: Array = []
		for cursor in fixture.cursors:
			snapshots.append(model.snapshot(int(cursor)))
		model.reset(int(fixture.reset_ns))
		model.consume(rows)
		snapshots.append(model.snapshot(int(fixture.cursors[-1])))
		results.append(snapshots)
	var output := FileAccess.open(output_path, FileAccess.WRITE)
	output.store_string(JSON.stringify(results))
	quit()
