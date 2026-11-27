extends RefCounted

var rd: RenderingDevice
var size: Vector2i
var shader := RID()
var pipeline := RID()
var buffer := RID()
var radiance := RID()
var events := RID()
var activity := RID()
var uniforms := RID()
var error := ""
var optical_shader := RID()
var optical_pipeline := RID()
var optical_uniforms := RID()
var diagnostics := RID()

func initialize(device: RenderingDevice, sensor_size: Vector2i) -> bool:
	rd = device
	size = sensor_size
	var source := RDShaderSource.new()
	source.source_compute = FileAccess.get_file_as_string("res://shaders/sensor.glsl").replace("#[compute]", "")
	var spirv := rd.shader_compile_spirv_from_source(source)
	error = spirv.get_stage_compile_error(RenderingDevice.SHADER_STAGE_COMPUTE)
	if not error.is_empty():
		return false
	shader = rd.shader_create_from_spirv(spirv)
	if not shader.is_valid():
		error = "Could not create sensor shader."
		return false
	pipeline = rd.compute_pipeline_create(shader)
	var initial := PackedByteArray()
	initial.resize(size.x * size.y * 16)
	buffer = rd.storage_buffer_create(initial.size(), initial)
	diagnostics = rd.storage_buffer_create(initial.size(), initial)
	radiance = _make_texture()
	events = _make_texture()
	activity = _make_texture()
	var state_uniform := RDUniform.new()
	state_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER
	state_uniform.binding = 0
	state_uniform.add_id(buffer)
	var radiance_uniform := RDUniform.new()
	radiance_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
	radiance_uniform.binding = 1
	radiance_uniform.add_id(radiance)
	var event_uniform := RDUniform.new()
	event_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
	event_uniform.binding = 2
	event_uniform.add_id(events)
	var activity_uniform := RDUniform.new()
	activity_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
	activity_uniform.binding = 3
	activity_uniform.add_id(activity)
	var diagnostic_uniform := RDUniform.new()
	diagnostic_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER
	diagnostic_uniform.binding = 4
	diagnostic_uniform.add_id(diagnostics)
	uniforms = rd.uniform_set_create([state_uniform, radiance_uniform, event_uniform, activity_uniform, diagnostic_uniform], shader, 0)
	source.source_compute = FileAccess.get_file_as_string("res://shaders/optical.glsl").replace("#[compute]", "")
	spirv = rd.shader_compile_spirv_from_source(source)
	error = spirv.get_stage_compile_error(RenderingDevice.SHADER_STAGE_COMPUTE)
	if not error.is_empty():
		return false
	optical_shader = rd.shader_create_from_spirv(spirv)
	optical_pipeline = rd.compute_pipeline_create(optical_shader)
	var optical_uniform := RDUniform.new()
	optical_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
	optical_uniform.binding = 0
	optical_uniform.add_id(radiance)
	optical_uniforms = rd.uniform_set_create([optical_uniform], optical_shader, 0)
	return pipeline.is_valid() and uniforms.is_valid() and optical_pipeline.is_valid() and optical_uniforms.is_valid()

func _make_texture() -> RID:
	var format := RDTextureFormat.new()
	format.width = size.x
	format.height = size.y
	format.format = RenderingDevice.DATA_FORMAT_R32G32B32A32_SFLOAT
	format.usage_bits = RenderingDevice.TEXTURE_USAGE_STORAGE_BIT | RenderingDevice.TEXTURE_USAGE_SAMPLING_BIT | RenderingDevice.TEXTURE_USAGE_CAN_COPY_FROM_BIT
	return rd.texture_create(format, RDTextureView.new())

func dispatch(parameters: Array) -> void:
	var commands := rd.compute_list_begin()
	for values: PackedFloat32Array in parameters:
		var bytes := values.to_byte_array()
		for pass_data in [[optical_pipeline, optical_uniforms], [pipeline, uniforms]]:
			rd.compute_list_bind_compute_pipeline(commands, pass_data[0])
			rd.compute_list_bind_uniform_set(commands, pass_data[1], 0)
			rd.compute_list_set_push_constant(commands, bytes, bytes.size())
			rd.compute_list_dispatch(commands, ceili(size.x / 8.0), ceili(size.y / 8.0), 1)
			rd.compute_list_add_barrier(commands)
	rd.compute_list_end()

func read_events() -> PackedFloat32Array:
	return rd.texture_get_data(events, 0).to_float32_array()

func read_state() -> PackedFloat32Array:
	return rd.buffer_get_data(buffer).to_float32_array()

func read_activity() -> PackedFloat32Array:
	return rd.texture_get_data(activity, 0).to_float32_array()

func read_radiance() -> PackedFloat32Array:
	return rd.texture_get_data(radiance, 0).to_float32_array()

func read_diagnostics() -> PackedFloat32Array:
	return rd.buffer_get_data(diagnostics).to_float32_array()

func read_intensity() -> PackedFloat32Array:
	var rgba := read_radiance()
	var values := PackedFloat32Array()
	values.resize(size.x * size.y)
	for i in values.size():
		values[i] = rgba[i * 4 + 3]
	return values

func cleanup() -> void:
	for resource in [optical_uniforms, optical_pipeline, optical_shader, uniforms, pipeline, shader, buffer, diagnostics, radiance, events, activity]:
		if resource.is_valid():
			rd.free_rid(resource)
