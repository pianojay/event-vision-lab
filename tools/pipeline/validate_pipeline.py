"""Write reproducible end-to-end runs and same-input comparisons to a new directory."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

from pipeline import Config, compare, read_capture, run, source_identity
from test_pipeline import edge


def validate(output):
    if output.exists():
        raise FileExistsError("validation output must be a new directory")
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern="test_*.py")
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("pipeline behavioral tests failed")
    configs={
        "edge-exact":edge(trajectory="exact"),
        "edge-log-coarse":edge(),
        "edge-log-midpoint-time":edge(sample_period_ns=5_000_000),
        "edge-held-coarse":edge(trajectory="held"),
        "edge-held-fine":edge(trajectory="held",sample_period_ns=100_000),
        "edge-spatial-one-sample":edge(spatial="midpoint",samples_per_axis=1,sample_period_ns=100_000),
        "pulse-uniform":edge(scene="pulse",sensor_parameters={"on_threshold":.2,"off_threshold":.2}),
        "pulse-known-boundaries":edge(scene="pulse",sampling="known-boundaries",sensor_parameters={"on_threshold":.2,"off_threshold":.2}),
        "pulse-exact":edge(scene="pulse",trajectory="exact",sensor_parameters={"on_threshold":.2,"off_threshold":.2}),
        "nonideal-coarse":edge(sensor="generic-nonideal",trajectory="held",sample_period_ns=1_000_000),
        "nonideal-fine":edge(sensor="generic-nonideal",trajectory="held",sample_period_ns=100_000),
        "nonideal-reference":edge(sensor="generic-nonideal",trajectory="held",sample_period_ns=10_000),
        "nonideal-reset-capacity":edge(sensor="generic-nonideal",trajectory="held",sample_period_ns=100_000,
                                      epoch_ns=10**18,reset_times_ns=(5_000_000,),capture_capacity=1,
                                      sensor_parameters={"on_threshold":.1,"off_threshold":.1,"refractory_s":.002}),
        "viewer-demo":Config(),
        "viewer-nonideal":Config(sensor="generic-nonideal",trajectory="held",sample_period_ns=1_000_000),
    }
    results={}
    for name,config in configs.items():
        config=replace(config,profile_name=name+"-v1",stream_id=name)
        manifest=run(config,output/name)
        results[name]={"manifest":name+"/manifest.json","stages":manifest["stages"],
                       "comparison":manifest["comparison"]["stored_vs_ideal_truth"],
                       "event_times_ns":[round(e.t*1e9) for e in read_capture(output/name/"events.csv",manifest["captures"]["events"])]}
    def events(name):
        manifest=json.loads((output/name/"manifest.json").read_text())
        return read_capture(output/name/"events.csv",manifest["captures"]["events"])
    convergence={name:compare(events("nonideal-reference"),events(name),.002)
                 for name in ("nonideal-coarse","nonideal-fine")}
    summary={"schema":"event-lab-pipeline-validation-v1","source":source_identity(),
             "behavior_tests":{"run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors)},
             "runs":results,"nonideal_same_model_sampling_comparison":convergence,
             "scope":"CPU functional comparisons. No camera calibration, upstream parity or performance benchmark."}
    (output/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Wrote {len(results)} end-to-end runs to {output}")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        validate(args.output)
    except (OSError,ValueError,TypeError,OverflowError,RuntimeError) as error:
        parser.exit(1,f"Validation failed: {error}\n")
