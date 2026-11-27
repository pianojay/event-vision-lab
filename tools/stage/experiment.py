"""Generate predeclared integrated experiments; analyze real GPU archives without images as input to tasks."""
from __future__ import annotations
import argparse, array, csv, hashlib, json, math, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
IDS = ["absorption", "diffuse", "glossy", "transmission", "refraction", "fluorescence", "phosphorescence", "subsurface", "interreflection"]
ACTIONS = ["object", "light", "light", "stripe", "stripe", "pulse", "pulse", "stripe", "pulse"]
# These tolerances are written to protocol.json before captures exist.
GATES = {"static_event_count": 0, "optical_difference_min": 1e-5,
         "event_task_min_events": 1, "central_event_fraction_min": 0.35,
         "temporal_count_relative_tolerance": 0.35, "spatial_count_density_relative_tolerance": 0.5,
         "sensor_count_error": 0, "sensor_polarity_error": 0, "sensor_timestamp_max_ns": 100000,
         "intensity_negative_count": 0, "intensity_nonfinite_count": 0}

def prepare(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    configs = output / "configs"
    configs.mkdir()
    runs = []
    for station, name in enumerate(IDS):
        for variant, width, height, period, treatment, action in [
            ("treatment",80,60,16666667,True,ACTIONS[station]),
            ("control",80,60,16666667,False,ACTIONS[station]),
            ("static",80,60,16666667,True,"static"),
            ("temporal",80,60,8333333,True,ACTIONS[station]),
            ("spatial",160,120,16666667,True,ACTIONS[station])]:
            identity = f"{station}-{name}-{variant}"
            config = dict(scene="interaction-stage",station=station,stage_action=action,treatment=treatment,
                width=width,height=height,sample_period_ns=period,duration_ns=1000000000,
                capture_capacity=2000000,archive_mode="diagnostic",wall_paced=False,
                reconstruction_enabled=True)
            path = configs / f"{identity}.json"
            path.write_text(json.dumps(config,indent=2)+"\n")
            runs.append(dict(id=identity,station=station,variant=variant,config=str(path.resolve()),
                output=str((output/identity).resolve())))
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        ROOT/"prototype/shaders/interaction_stage.glsl",ROOT/"prototype/shaders/material_models.glsl",
        ROOT/"prototype/stage/interaction_stage.gd",ROOT/"prototype/stage/stage_controller.gd",
        ROOT/"prototype/materials/registry.json",Path(__file__)]}
    protocol = dict(schema="event-lab-stage-experiment-v2",gates=GATES,runs=runs,source_sha256=hashes,
        revision_reason="v1 transmission/object and refraction/camera trials produced peripheral activity; v2 uses finite rear emitter stripe motion at fixed camera/object/light; gates and ROI unchanged",
        optical_stimulus="At z=-5 m, two 1.8 m square emitters centred behind stations 3 and 4; radiance 0.44+0.36*sin(2*pi*(local_x-offset)/0.5 m), offset=0.2*sin(3*t) m for stripe action; front plane and other background stay fixed",
        scope="Actual combined nine-station shader, focused camera; ideal sensor; restricted analytic models",
        event_task="Locate changed region from emitted events alone; compare count/polarity/spatial histogram with paired control",
        central_region="middle 60% of pixel width and height; predeclared from focused station layout",
        comparisons="static silence; treatment/control optical difference; temporal and spatial normalized event counts",
        independent_sensor_reference="tools/acquisition/recorded_input.py reads only archived FP32 intensity; strict count/polarity,100us timestamps",
        caveat="Spatial/temporal event-count convergence does not prove every optical approximation. Failures are retained.")
    (output/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    return protocol

def read_run(path: Path):
    manifest = json.loads((path/"manifest.json").read_text())
    values = array.array("f")
    with (path/"intensity.f32").open("rb") as f: values.frombytes(f.read())
    if sys.byteorder != "little": values.byteswap()
    with (path/"events.csv").open(newline="") as f:
        events = [tuple(int(row[key]) for key in ("x","y","t_ns","p")) for row in csv.DictReader(f)]
    return manifest,values,events

def event_task(events,width,height):
    # This function has no optical input. The ROI is fixed by the protocol, not fitted to truth.
    counts=[0]*16
    central=0
    for x,y,t,p in events:
        counts[min(3,y*4//height)*4+min(3,x*4//width)]+=1
        central += int(.2*width<=x<.8*width and .2*height<=y<.8*height)
    return dict(events=len(events),on=sum(e[3]>0 for e in events),off=sum(e[3]<0 for e in events),
        central_fraction=central/max(1,len(events)),grid_4x4=counts,
        peak_cell=counts.index(max(counts)) if events else None,
        centroid=[sum(e[0] for e in events)/len(events),sum(e[1] for e in events)/len(events)] if events else None)

def analyze(output: Path):
    protocol=json.loads((output/"protocol.json").read_text())
    gates=protocol["gates"]
    results={}
    checks=[]
    missing=[]
    def check(name,passed,observed,tolerance):
        checks.append(dict(name=name,passed=bool(passed),observed=observed,tolerance=tolerance))
    for run in protocol["runs"]:
        path=Path(run["output"])
        if not (path/"manifest.json").exists(): missing.append(run["id"]); continue
        manifest,values,events=read_run(path)
        config=manifest["effective_config"]
        task=event_task(events,config["width"],config["height"])
        finite=all(math.isfinite(v) and v>=0 for v in values)
        check(run["id"]+" finite nonnegative optical",finite,finite,True)
        results[run["id"]]=dict(task=task,cost=manifest.get("runtime",manifest.get("cost",{})),
            samples=manifest["optical_input"]["sample_count"],event_sha256=manifest["captures"]["events"]["sha256"],
            min_intensity=min(values),max_intensity=max(values),mean_log_intensity=sum(math.log(max(v,1e-6)) for v in values)/len(values),
            source=manifest["source"],complete=manifest["captures"]["events"]["complete_relative_to_stage_input"])
        check(run["id"]+" complete capture",results[run["id"]]["complete"],results[run["id"]]["complete"],True)
        if run["variant"]=="static": check(run["id"]+" silence",len(events)==gates["static_event_count"],len(events),gates["static_event_count"])
        if run["variant"]=="treatment":
            check(run["id"]+" observable events",len(events)>=gates["event_task_min_events"],len(events),gates["event_task_min_events"])
            check(run["id"]+" locate station",task["central_fraction"]>=gates["central_event_fraction_min"],task["central_fraction"],gates["central_event_fraction_min"])
        # Independent reference runs separately and writes its own failures verbatim.
        reference=path/"independent-sensor.json"
        command=[sys.executable,str(ROOT/"tools/acquisition/recorded_input.py"),str(path/"manifest.json"),"--report",str(reference)]
        completed=subprocess.run(command,capture_output=True,text=True)
        results[run["id"]]["independent_reference_exit"]=completed.returncode
        results[run["id"]]["independent_reference_report"]=str(reference)
        check(run["id"]+" independent sensor",completed.returncode==0,completed.returncode,0)
        if completed.returncode: results[run["id"]]["reference_error"]=completed.stdout+completed.stderr
    for i,name in enumerate(IDS):
        keys={v:f"{i}-{name}-{v}" for v in ("treatment","control","temporal","spatial")}
        if keys["treatment"] not in results: continue
        base=results[keys["treatment"]]["task"]["events"]
        for v,scale,tol in [("temporal",1,gates["temporal_count_relative_tolerance"]),("spatial",4,gates["spatial_count_density_relative_tolerance"])]:
            if keys[v] in results:
                value=abs(results[keys[v]]["task"]["events"]/scale-base)/max(base,1)
                check(name+" "+v+" count convergence",value<=tol,value,tol)
        if keys["control"] in results:
            _,a,_=read_run(output/keys["treatment"])
            _,b,_=read_run(output/keys["control"])
            difference=max(abs(x-y) for x,y in zip(a,b))
            check(name+" treatment changes optics",difference>=gates["optical_difference_min"],difference,gates["optical_difference_min"])
    report=dict(schema="event-lab-stage-results-v1",protocol_schema=protocol["schema"],gates=gates,missing=missing,checks=checks,results=results,
        passed=not missing and all(c["passed"] for c in checks))
    (output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(passed=report["passed"],checks=len(checks),failed=sum(not c["passed"] for c in checks),missing=len(missing))))
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["prepare","analyze"])
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    if args.command=="prepare": prepare(args.output)
    else: return 0 if analyze(args.output)["passed"] else 1
    return 0
if __name__=="__main__": raise SystemExit(main())
