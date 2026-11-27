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
		push_error("Material GPU checks require a genuine graphics context.")
		quit(1)
		return
	var source := RDShaderSource.new()
	source.source_compute = "#version 450\n" + FileAccess.get_file_as_string("res://shaders/material_models.glsl") + """
layout(local_size_x=1,local_size_y=1,local_size_z=1) in;
layout(set=0,binding=0,std430) buffer Output { float value[]; } result;
void main() {
    result.value[0]=mat_beer(1.7,0.4);
    result.value[1]=mat_beer(0.0,2.0);
    result.value[2]=mat_diffuse(0.55,0.5);
    result.value[3]=mat_glossy(0.5,0.2,vec3(0,0,1),vec3(0,0,1),vec3(0,0,1));
    result.value[4]=mat_fresnel(1.0,1.0,1.5);
    result.value[5]=mat_fresnel(0.5,1.5,1.0);
    result.value[6]=mat_fresnel(0.0,1.0,1.0);
    vec3 ep,ed; vec4 energy;
    bool transmitted=mat_slab(vec3(0),vec3(0.5,0,-sqrt(0.75)),vec3(0,0,1),
        0.2,1.0,1.5,0.7,ep,ed,energy);
    result.value[7]=ep.x;
    result.value[8]=ep.z;
    result.value[9]=ed.x;
    result.value[10]=dot(energy,vec4(1));
    result.value[11]=energy.y;
    result.value[12]=float(transmitted);
    transmitted=mat_sphere(vec3(0.3,0,3),vec3(0,0,-1),vec3(0),1.0,1.0,1.5,0.5,ep,ed,energy);
    result.value[13]=ed.x;
    result.value[14]=ed.z;
    result.value[15]=dot(energy,vec4(1));
    result.value[16]=energy.y;
    result.value[17]=float(transmitted);
    result.value[18]=mat_thin_weights(0.1,0.6).z;
    vec3 ray;
    result.value[19]=float(mat_refract(vec3(sqrt(0.75),0,-0.5),vec3(0,0,1),1.5,1.0,ray));
    vec3 fluorescence=mat_fluorescence(3.0,0.4,0.8,0.7,405.0,550.0,0.1,0.9);
    result.value[20]=fluorescence.x;
    result.value[21]=fluorescence.y;
    result.value[22]=fluorescence.z;
    result.value[23]=mat_fluorescence(0.0,3.0,0.8,0.7,405.0,550.0,0.1,0.9).y;
    float stored=mat_population_step(0.0,2.0,0.2,0.4,0.6);
    result.value[24]=stored;
    result.value[25]=mat_afterglow_power(mat_population_step(stored,0.0,0.3,0.4,0.6),0.4,0.8);
    result.value[26]=mat_population_step(stored,100.0,0.0,0.4,0.6);
    result.value[27]=mat_population_step(0.0,2.0,0.000001,0.4,0.6);
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
	var initial := PackedByteArray()
	initial.resize(256*4)
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
	_check("Beer numerical attenuation",values[0],pow((1.0-0.68/2048)/(1.0+0.68/2048),1024))
	_check("Zero absorption",values[1],1.0)
	_check("Lambert radiance",values[2],0.275/PI)
	_check("Conservative glossy peak",values[3],0.5*49.0/(2.0*PI))
	_check("Normal dielectric Fresnel",values[4],0.04)
	_check("Total internal reflection",values[5],1.0)
	_check("Equal index Fresnel",values[6],0.0)
	var theta_t := asin(0.5/1.5)
	_check("Slab lateral displacement",values[7],0.2*tan(theta_t))
	_check("Slab rear plane",values[8],-0.2)
	_check("Parallel exit direction",values[9],0.5)
	_check("Slab energy accounting",values[10],1.0)
	var theta_i := PI/6.0
	var reflected := 0.5*(pow(sin(theta_i-theta_t)/sin(theta_i+theta_t),2)+pow(tan(theta_i-theta_t)/tan(theta_i+theta_t),2))
	_check("Slab primary transmitted energy",values[11],pow(1-reflected,2)*exp(-0.7*0.2/cos(theta_t)))
	_check("Slab path exists",values[12],1.0)
	var sphere_i := asin(0.3)
	var sphere_t := asin(0.2)
	var deviation := 2*(sphere_i-sphere_t)
	_check("Curved refraction x direction",values[13],-sin(deviation))
	_check("Curved refraction z direction",values[14],-cos(deviation))
	_check("Sphere energy accounting",values[15],1.0)
	var sphere_r := 0.5*(pow(sin(sphere_i-sphere_t)/sin(sphere_i+sphere_t),2)+pow(tan(sphere_i-sphere_t)/tan(sphere_i+sphere_t),2))
	_check("Sphere primary transmitted energy",values[16],pow(1-sphere_r,2)*exp(-cos(sphere_t)))
	_check("Sphere path exists",values[17],1.0)
	_check("Nonbending pane absorption",values[18],0.3)
	_check("TIR ray rejected",values[19],0.0)
	_check("Fluorescence direct bands",values[20],(0.1*0.6+0.9*0.4)/PI)
	_check("Fluorescence photon energy conversion",values[21],0.9*(3.0*0.8/(6.62607015e-34*299792458.0/(405e-9)))*0.7*(6.62607015e-34*299792458.0/(550e-9))/PI)
	_check("Fluorescence excitation absorption",values[22],2.4)
	_check("Nonexciting band control",values[23],0.0)
	var stored_expected := 0.6*2.0*0.4*(1.0-exp(-0.2/0.4))
	_check("Causal reservoir charge",values[24],stored_expected)
	_check("Afterglow persists after source off",values[25],0.8*stored_expected*exp(-0.3/0.4)/0.4)
	_check("Paused material state",values[26],stored_expected)
	_check("Small timestep reservoir",values[27],0.6*2.0*0.4*(1.0-exp(-0.000001/0.4)),0.0000000001)
	for resource in [uniforms,pipeline,shader,buffer]:
		rd.free_rid(resource)
	rd.free()
	var report := {"passed": not failed,"scope":"standalone material GLSL numerical probes; not integrated stage validation","checks":checks}
	var arguments := OS.get_cmdline_user_args()
	var output_path := ""
	for index in range(arguments.size()):
		var argument := arguments[index]
		if argument.begins_with("--output=") or argument.begins_with("--report="):
			output_path=argument.substr(argument.find("=")+1)
		elif argument in ["--output","--report"] and index+1 < arguments.size():
			output_path=arguments[index+1]
	if not output_path.is_empty():
		var file := FileAccess.open(output_path,FileAccess.WRITE)
		if file == null:
			push_error("Cannot write material GPU evidence.")
			failed=true
		else:
			file.store_string(JSON.stringify(report,"  ")+"\n")
	print("MATERIAL_GPU_RESULT ",JSON.stringify(report))
	quit(1 if failed else 0)
