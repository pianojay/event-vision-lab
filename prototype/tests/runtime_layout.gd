extends RefCounted

static func instantiate_lab() -> Control:
	var scene: PackedScene = load(ProjectSettings.get_setting("application/run/main_scene"))
	return scene.instantiate()

static func snapshot(lab: Control, require_composed: bool = true) -> Dictionary:
	var viewport := lab.get_viewport_rect()
	var errors: Array = []
	var panels := {}
	var required := {"main_observation":lab.canvas, "observation_selector":lab.mode_select, "pause":lab.pause_check}
	var sidebar: Node = lab.mode_select.get_parent()
	while sidebar != null and not sidebar is ScrollContainer:
		sidebar = sidebar.get_parent()
	required["sidebar"] = sidebar
	if require_composed:
		required["raw_events"] = lab.get("raw_panel")
		required["processed_events"] = lab.get("processing_panel")
		required["inference"] = lab.get("reconstruction_panel")
	var lab_rect := lab.get_global_rect()
	if not lab_rect.position.is_equal_approx(viewport.position) or not lab_rect.size.is_equal_approx(viewport.size):
		errors.append("Main scene does not fill the viewport")
	var hero_fraction := 0.0
	for name in required:
		var control: Control = required[name]
		if control == null:
			errors.append("Missing panel: " + name)
			continue
		var rect := control.get_global_rect()
		var visible := control.is_visible_in_tree()
		panels[name] = {"rect":[rect.position.x,rect.position.y,rect.size.x,rect.size.y],"visible":visible}
		if name == "inference" and not lab.perception.inference_enabled:
			continue
		if not visible or rect.size.x <= 0 or rect.size.y <= 0:
			errors.append("Panel is hidden or has no area: " + name)
		elif not viewport.grow(1.0).encloses(rect):
			errors.append("Panel extends beyond viewport: " + name)
		if name == "main_observation":
			hero_fraction = rect.get_area() / maxf(viewport.get_area(), 1.0)
			if hero_fraction < 0.1:
				errors.append("Main observation occupies less than 10 percent of viewport")
		elif name == "sidebar" and rect.size.y < viewport.size.y * 0.4:
			errors.append("Sidebar occupies less than 40 percent of viewport height")
	return {"valid":errors.is_empty(),"errors":errors,"scene_file_path":lab.scene_file_path,
		"viewport":[viewport.position.x,viewport.position.y,viewport.size.x,viewport.size.y],
		"lab_rect":[lab_rect.position.x,lab_rect.position.y,lab_rect.size.x,lab_rect.size.y],
		"main_observation_area_fraction":hero_fraction,"panels":panels}
