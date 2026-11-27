extends SceneTree
const Kernel = preload("res://sensor_gpu.gd")
const Expand = preload("res://acquisition/crossings.gd")
var device: RenderingDevice
var kernel: RefCounted
var checks: Array = []
var report := ""
func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report="): report=arg.trim_prefix("--report=")
	call_deferred("run")
func check(label: String, passed: bool, detail: Variant=null) -> void:
	checks.append({"name":label,"passed":passed,"detail":detail})
	print("PASS " if passed else "FAIL ",label," ",detail)
func params(intensity: float, reset: bool=false) -> PackedFloat32Array:
	return PackedFloat32Array([0.001,0.001,float(reset),1,0.25,0.5,0.2,intensity,0,1.55,5.1,0,-0.1,1,1,0.55,0,1,0,5,2,0,1,0.55,0,2,2,0])
func step(values: PackedFloat32Array) -> PackedFloat32Array:
	kernel.dispatch([values])
	device.submit()
	device.sync()
	return kernel.read_diagnostics()
func run() -> void:
	device=RenderingServer.create_local_rendering_device()
	if device==null:
		push_error("Real RenderingDevice required")
		quit(1)
		return
	kernel=Kernel.new()
	if not kernel.initialize(device,Vector2i(1,1)):
		push_error(kernel.error)
		quit(1)
		return
	var values:=step(params(0,true))
	check("optical archive preserves pre-floor zero",kernel.read_intensity()[0]==0)
	check("sensor floor keeps zero finite",is_finite(kernel.read_state()[3]) and absf(kernel.read_state()[3]-log(1e-6))<1e-5)
	check("reset emits no crossings",values[3]==0)
	step(params(1,true))
	values=step(params(exp(1.1)))
	var expanded:=Expand.expand(values,Vector2i(1,1),9000000000000000,9000000000001000,0.25,0.5)
	check("complete ON crossings exported",not expanded.has("error") and expanded.events.size()==4,expanded)
	check("GPU counts equal expanded events",kernel.read_events()[0]==expanded.events.size())
	values=step(params(1))
	expanded=Expand.expand(values,Vector2i(1,1),1000,2000,0.25,0.5)
	check("asymmetric OFF threshold",not expanded.has("error") and expanded.events.size()==2 and expanded.events[0][3]==-1,expanded)
	step(params(1,true))
	var old_ref:=PackedFloat32Array([0.638227581977844,-1000,-1000,0.443717420101166]).to_byte_array()
	device.buffer_update(kernel.buffer,0,old_ref.size(),old_ref)
	var anchor_data:=PackedFloat32Array([0.638227581977844,0,0,0,0.2,0.2,0,0]).to_byte_array()
	device.buffer_update(kernel.anchors,0,anchor_data.size(),anchor_data)
	var input:=params(exp(0.438228875398636))
	input[4]=0.2
	input[5]=0.2
	values=step(input)
	check("camera counterexample waits for actual threshold",values[3]==0,Array(values))
	step(params(1,true))
	values=step(params(exp(0.5)))
	expanded=Expand.expand(values,Vector2i(1,1),0,1000,0.25,0.5)
	check("rounded optical input below threshold emits one event",not expanded.has("error") and expanded.events.size()==1,expanded)
	var endpoint_threshold: float=values[2]/2.0
	step(params(1,true))
	var endpoint_input:=params(exp(0.5))
	endpoint_input[4]=endpoint_threshold
	values=step(endpoint_input)
	expanded=Expand.expand(values,Vector2i(1,1),0,1000,endpoint_threshold,0.5)
	check("representable measured endpoint retained",not expanded.has("error") and expanded.events.size()==2 and expanded.events[-1][2]==1000,expanded)
	values=step(endpoint_input)
	check("endpoint event not repeated",values[3]==0)
	step(params(exp(-3.95),true))
	var rise:=params(exp(-2.10))
	rise[4]=0.2
	rise[5]=0.2
	step(rise)
	var fall:=params(exp(-3.95))
	fall[4]=0.2
	fall[5]=0.2
	values=step(fall)
	check("anchored counts retain exact return after nine levels",values[3]==-9,Array(values))
	var failed:=false
	for item in checks:
		if not item.passed: failed=true
	if not report.is_empty():
		var file:=FileAccess.open(report,FileAccess.WRITE)
		file.store_string(JSON.stringify({"checks":checks,"failed":failed,"adapter":RenderingServer.get_video_adapter_name()},"  "))
	kernel.cleanup()
	device.free()
	quit(1 if failed else 0)
