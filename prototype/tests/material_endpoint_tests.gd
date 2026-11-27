extends SceneTree

var checks: Array = []
var failed := false

func _initialize() -> void:
	call_deferred("_run")

func _check(name: String, actual: float, expected: float, tolerance: float = 0.00002) -> void:
	var passed := is_finite(actual) and absf(actual-expected) <= tolerance
	checks.append({"name": name, "passed": passed, "actual": actual, "expected": expected, "absolute_tolerance": tolerance})
	failed = failed or not passed
	print("PASS " if passed else "FAIL ", name, " actual=", actual, " expected=", expected)

func _run() -> void:
	var rd := RenderingServer.create_local_rendering_device()
	if rd == null:
		push_error("Material endpoint checks require a genuine graphics context.")
		quit(1)
		return
	var source := RDShaderSource.new()
	source.source_compute = "#version 450\n" + FileAccess.get_file_as_string("res://shaders/material_models.glsl") + """
layout(local_size_x=1,local_size_y=1,local_size_z=1) in;
layout(set=0,binding=0,std430) buffer Output { float value[]; } result;
void main() {
    float roughness=result.value[0];
    float rho_s=result.value[1];
    float below_endpoint=result.value[2];
    vec3 n=vec3(0,0,1);
    vec3 off_lobe=vec3(sqrt(0.75),0,0.5);
    vec3 zero_cosine=vec3(sqrt(0.5),0,sqrt(0.5));
    result.value[0]=mat_glossy(rho_s,roughness,n,off_lobe,off_lobe);
    result.value[1]=mat_glossy(rho_s,roughness,n,zero_cosine,zero_cosine);
    result.value[2]=mat_glossy(rho_s,roughness,n,n,off_lobe);
    result.value[3]=mat_glossy(rho_s,roughness,n,n,n);
    result.value[4]=mat_glossy(rho_s,below_endpoint,n,off_lobe,off_lobe);
    result.value[5]=mat_glossy(rho_s,0.5,n,zero_cosine,zero_cosine);
    result.value[6]=mat_glossy(rho_s,roughness,n,-n,n);
    result.value[7]=mat_glossy(rho_s,roughness,n,n,-n);
    result.value[8]=mat_glossy(rho_s,roughness,n,vec3(1,0,0),n);
}
"""
	var spirv := rd.shader_compile_spirv_from_source(source)
	var compile_error := spirv.get_stage_compile_error(RenderingDevice.SHADER_STAGE_COMPUTE)
	if not compile_error.is_empty():
		push_error(compile_error)
		rd.free()
		quit(1)
		return
	var shader := rd.shader_create_from_spirv(spirv)
	var pipeline := rd.compute_pipeline_create(shader)
	var initial := PackedFloat32Array([1.0, 0.7, 0.999, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]).to_byte_array()
	var buffer := rd.storage_buffer_create(initial.size(),initial)
	var uniform := RDUniform.new()
	uniform.uniform_type=RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER
	uniform.binding=0
	uniform.add_id(buffer)
	var uniforms := rd.uniform_set_create([uniform],shader,0)
	var commands := rd.compute_list_begin()
	rd.compute_list_bind_compute_pipeline(commands,pipeline)
	rd.compute_list_bind_uniform_set(commands,uniforms,0)
	rd.compute_list_dispatch(commands,1,1,1)
	rd.compute_list_end()
	rd.submit()
	rd.sync()
	var values := rd.buffer_get_data(buffer).to_float32_array()
	var endpoint := 0.7/(2.0*PI)
	_check("Roughness endpoint off lobe",values[0],endpoint)
	_check("Roughness endpoint zero cosine",values[1],endpoint)
	_check("Roughness endpoint positive cosine",values[2],endpoint)
	_check("Roughness endpoint peak",values[3],endpoint)
	_check("Below endpoint off lobe",values[4],0.0)
	_check("Finite-exponent zero cosine",values[5],0.0)
	_check("Endpoint light below hemisphere",values[6],0.0)
	_check("Endpoint view below hemisphere",values[7],0.0)
	_check("Endpoint light on horizon",values[8],0.0)
	for resource in [uniforms,pipeline,shader,buffer]:
		rd.free_rid(resource)
	rd.free()
	var report := {"passed": not failed,"scope":"standalone glossy roughness endpoint probes; not integrated stage validation","checks":checks}
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			var file := FileAccess.open(argument.trim_prefix("--report="),FileAccess.WRITE)
			if file == null:
				push_error("Cannot write material endpoint evidence.")
				failed=true
			else:
				file.store_string(JSON.stringify(report,"  ")+"\n")
	print("MATERIAL_ENDPOINT_RESULT ",JSON.stringify(report))
	quit(1 if failed else 0)
