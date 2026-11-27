"""Run serialized real-context Godot replay checks; acquire the shared GPU slot first."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

from pipeline import Config, ROOT, run


def validate(output):
    if output.exists():
        raise FileExistsError("replay validation output must be new")
    cases={"ideal":Config(), "nonideal":Config(sensor="generic-nonideal",trajectory="held",sample_period_ns=1_000_000),
           "large-epoch":Config(epoch_ns=10**18), "empty-capacity":Config(capture_capacity=0)}
    checks=[]
    for name,config in cases.items():
        folder=output/name
        manifest=run(replace(config,stream_id=name,profile_name=name+"-replay-v1"),folder)
        command=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"run-pipeline.ps1"),
                 "-ExistingRun",str(folder.resolve()),"-VerifyReplay"]
        proc=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (folder/"launcher.log").write_text(proc.stdout+proc.stderr,encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"replay failed for {name}: {proc.stdout} {proc.stderr}")
        report=json.loads((folder/"replay-check.json").read_text())
        if len(report.get("control_checks",[]))!=4 or not all(check["passed"] for check in report["control_checks"]):
            raise RuntimeError(f"routed keyboard control checks failed for {name}")
        # Independent integer-ns window count, compared with the actual viewer report.
        import csv
        with (folder/"events.csv").open(newline="") as f:
            rows=list(csv.DictReader(f))
        midpoint=config.duration_ns//2
        window=min(40_000_000,config.duration_ns//5)
        visible=[r for r in rows if midpoint-window < int(r["t_ns"])-config.epoch_ns <= midpoint]
        pixels={(int(r["x"]),int(r["y"])) for r in visible}
        if report["visible_events"]!=len(visible) or report["lit_pixels"]!=len(pixels) or report["loaded_events"]!=len(rows):
            raise RuntimeError(f"replay count mismatch for {name}")
        checks.append({"case":name,"exit_code":proc.returncode,"expected_visible_events":len(visible),
                       "expected_active_pixels":len(pixels),"routed_keyboard_checks":4,"report":name+"/replay-check.json"})
    base=json.loads((output/"ideal/manifest.json").read_text())
    for name in ("bad-stage","bad-completeness","bad-epoch","bad-count","bad-epoch-type",
                 "bad-completeness-type","bad-stream","bad-polarity"):
        folder=output/name
        folder.mkdir()
        shutil.copyfile(output/"ideal/events.csv",folder/"events.csv")
        manifest=json.loads(json.dumps(base))
        meta=manifest["captures"]["events"]
        if name=="bad-stage": meta["stage"]="ideal-optical-truth"
        if name=="bad-completeness": meta["complete_relative_to_stage_input"]=False
        if name=="bad-epoch": meta["epoch_ns"]="-1"
        if name=="bad-count": meta["stored_count"]+=1
        if name=="bad-epoch-type": meta["epoch_ns"]=0.9
        if name=="bad-completeness-type": meta["complete_relative_to_stage_input"]=1
        if name=="bad-stream": meta["stream_id"]=""
        if name=="bad-polarity": meta["polarity"]={"on":-1,"off":1}
        (folder/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        command=["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"run-pipeline.ps1"),
                 "-ExistingRun",str(folder.resolve()),"-VerifyReplay"]
        proc=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (folder/"launcher.log").write_text(proc.stdout+proc.stderr,encoding="utf-8")
        if proc.returncode==0:
            raise RuntimeError(f"invalid replay accepted: {name}")
        checks.append({"case":name,"exit_code":proc.returncode,"expected":"rejected","log":name+"/launcher.log"})
    (output/"summary.json").write_text(json.dumps({"checks":checks,"scope":"Real Vulkan context; event-window counts and metadata rejection; interactive controls checked separately"},indent=2)+"\n",encoding="utf-8")
    print(f"Passed {len(checks)} replay checks")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        validate(args.output)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        parser.exit(1,f"Replay validation failed: {error}\n")
