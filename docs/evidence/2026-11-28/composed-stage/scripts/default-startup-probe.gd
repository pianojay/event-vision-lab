extends SceneTree
var report_path := ""
var declared_revision := ""
func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report="): report_path=arg.trim_prefix("--report=")
		if arg.begins_with("--source-revision="): declared_revision=arg.trim_prefix("--source-revision=")
	call_deferred("run")
func run() -> void:
	var app=load("res://main.tscn").instantiate()
	root.add_child(app)
	current_scene=app
	var began=Time.get_ticks_usec()
	while not app.ready_gpu:
		await process_frame
		if Time.get_ticks_usec()-began>30000000:
			quit(1)
			return
	await create_timer(3.0).timeout
	var state: Dictionary=app.get_validation_snapshot()
	var raw: Dictionary=app.perception.last_raw
	var central:=0.0
	var total:=0.0
	for y in 60:
		for x in 80:
			var n: float=raw.on[y*80+x]+raw.off[y*80+x]
			total+=n
			if x>=16 and x<64 and y>=12 and y<48: central+=n
	var finished: Dictionary=await app.validation_finish()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(report_path.get_base_dir().path_join("default.png"))
	var file=FileAccess.open(report_path,FileAccess.WRITE)
	file.store_string(JSON.stringify({"kind":"normal main scene with no acquisition override","declared_source_revision":declared_revision,"main_gd_sha256":FileAccess.get_sha256("res://main.gd"),"probe_sha256":FileAccess.get_sha256(get_script().resource_path),"snapshot":state,"last_raw_window_events":total,"last_raw_central_events":central,"finalized":finished.get("finalized",false)},"  "))
	quit(0)
