"""Reproduce isolated linear/log/event evidence; no GPU or calibration claims."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import time
from tools.materials.surface import beer, diffuse, glossy, ThinPane, Medium, sphere
from tools.timing.timing_reference import sampled_events, compare

ROOT=Path(__file__).resolve().parents[2]
FLOOR=1e-6
THRESHOLD=.2


def f32(v):
    return struct.unpack('<f',struct.pack('<f',v))[0]


def lamp(t):
    return math.exp(.7*math.sin(math.tau*t))


def absorption_ref(t):
    # Implicit midpoint integration of attenuation over a 0.4 m slab.
    steps=512
    h=1.7*.4/(2*steps)
    return lamp(t)*((1-h)/(1+h))**steps


def sphere_reference(t):
    # Independent 2D trigonometric construction at a unit sphere, camera x=b.
    b=.55*math.sin(math.tau*t)
    i=math.asin(b)
    r=math.asin(b/1.5)
    inside_angle=i-r
    x=b-2*math.cos(r)*math.sin(inside_angle)
    z=math.sqrt(1-b*b)-2*math.cos(r)*math.cos(inside_angle)
    direction_angle=2*inside_angle
    background_x=x-(z+3)*math.tan(direction_angle)
    # Fresnel from angle identities, not the vector implementation.
    if abs(i)<1e-10:
        reflectance=.04
    else:
        reflectance=.5*((math.sin(i-r)/math.sin(i+r))**2+
                         (math.tan(i-r)/math.tan(i+r))**2)
    transmission=(1-reflectance)**2*math.exp(-.2*2*math.cos(r))
    return transmission*(.6+.35*math.sin(4*background_x))+.02*reflectance


def sphere_sample(t):
    b=.55*math.sin(math.tau*t)
    path=sphere((b,0,3),(0,0,-1),(0,0,0),1,Medium(.2,1.5))
    u=(-3-path.exit_point[2])/path.exit_direction[2]
    bgx=path.exit_point[0]+u*path.exit_direction[0]
    return path.transmission*(.6+.35*math.sin(4*bgx))+.02*path.reflection


def scenarios():
    n=(0,0,1)
    def spec(t):
        a=.5*math.sin(math.tau*t)
        return .02+glossy(.5,.2,n,(math.sin(a),0,math.cos(a)),n)*max(0,math.cos(a))
    exponent=2/.2**2-2
    return {
        'absorption': (lambda t: lamp(t)*beer(1.7,.4),absorption_ref,
                       lambda t: lamp(t),{'mu_a_m_inv':1.7,'path_m':.4}),
        'diffuse': (lambda t: diffuse(.55,2*max(0,math.cos(.8*math.sin(math.tau*t)))/4),
                    lambda t: .55*max(0,math.cos(.8*math.sin(math.tau*t)))/(2*math.pi),
                    lambda t: diffuse(.55,.5),{'rho_d':.55,'light_distance_m':2,'power_per_sr':2,'light_angle_rad':'.8*sin(2*pi*t)','ambient':0}),
        'glossy': (spec,lambda t: .02+.5*(exponent+1)/(2*math.pi)*math.cos(.5*math.sin(math.tau*t))**(exponent+1),
                   lambda t: .02,{'rho_s':.5,'roughness':.2,'light_angle_rad':'.5*sin(2*pi*t)','view_normal':True,'declared_diffuse_radiance':.02}),
        'transmission': (lambda t: ThinPane(.1,.6).radiance(lamp(t),.2),
                        lambda t: .6*lamp(t)+.02,lambda t: lamp(t),{'R':.1,'T':.6,'A':.3,'reflected_environment':.2}),
        'refraction': (sphere_sample,sphere_reference,
                       lambda t: (.96**2)*math.exp(-.4)*(.6+.35*math.sin(4*.55*math.sin(math.tau*t)))+.0008,
                       {'sphere_center_m':[0,0,0],'radius_m':1,'camera_origin_m':['.55*sin(2*pi*t)',0,3],'ray':[0,0,-1],'background_z_m':-3,'eta':1.5,'eta_outside':1,'mu_a_m_inv':.2,'control':'unbent background ray with fixed normal-incidence energy; isolates geometric effect'})}


def trace(fn,hz=240):
    times=[k/hz for k in range(hz+1)]
    linear=[f32(fn(t)) for t in times]
    logs=[math.log(max(FLOOR,v)) for v in linear]
    events=sampled_events(lambda t: logs[round(t*hz)],times,THRESHOLD,THRESHOLD)
    return {'times_s':times,'linear_f32':linear,'log':logs,'delta_log':[0]+[b-a for a,b in zip(logs,logs[1:])],
            'events':[asdict(e) for e in events]},events


def evaluate(name,fn,reference,control,parameters):
    data,events=trace(fn)
    refdata,refevents=trace(reference)
    controls,_=trace(control)
    error=max(abs(a-b) for a,b in zip(data['linear_f32'],refdata['linear_f32']))
    log_error=max(abs(a-b) for a,b in zip(data['log'],refdata['log']))
    fine_times=[k/3840 for k in range(3841)]
    fine_events=sampled_events(lambda t: math.log(max(FLOOR,reference(t))),fine_times)
    convergence=[]
    for hz in (60,120,240,480):
        _,coarse=trace(fn,hz)
        convergence.append({'hz':hz,**compare(fine_events,coarse,1/hz)})
    static,static_events=trace(lambda t: fn(.137))
    timings=[]
    checksum=0
    for _ in range(5):
        start=time.perf_counter()
        values=[fn(k/240) for k in range(241)]
        timings.append(time.perf_counter()-start)
        checksum+=sum(values)
    comparison=compare(refevents,events,1e-6)
    passed=(error<2e-6 and log_error<2e-5 and comparison['missing']==0 and comparison['extra']==0 and not static_events)
    return {'name':name,'parameters':parameters,'reference_tolerances':{'linear_abs':2e-6,'log_abs':2e-5,'event_time_s':1e-6,'missing_extra':0},
            'passed':passed,'linear_abs_max':error,'log_abs_max':log_error,'event_comparison':comparison,
            'trace':data,'independent_reference':refdata,'isolated_control':controls,
            'sampling_convergence_against_3840_hz':convergence,'static_events':len(static_events),
            'cost':{'scope':'CPU binary64 model calls only, 241 samples; excludes rendering, reference, sensor, I/O and GPU','runs_s':timings,'median_s':statistics.median(timings),'checksum':checksum}}


def evidence(models):
    source_files=sorted(list((ROOT/'tools/materials').glob('*.py'))+list((ROOT/'prototype/materials').glob('*'))+[ROOT/'prototype/shaders/material_models.glsl'])
    return {'schema':'event-lab-material-evidence-v1','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':{str(f.relative_to(ROOT)).replace(chr(92),'/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files if f.is_file()},
            'host':{'platform':platform.platform(),'processor':platform.processor(),'python':platform.python_version()},
            'scope':'isolated deterministic CPU optical models and existing ideal SampledPixel; no integrated 3D stage or real camera validation',
            'sensor':{'profile':'existing tools/timing/timing_reference.py SampledPixel log-linear','threshold_on':THRESHOLD,'threshold_off':THRESHOLD,'floor':FLOOR,'floor_is':'explicit numerical clamp only','optical_archive_precision':'FP32 before log'},
            'models':models,'passed':all(m['passed'] for m in models)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=evidence([evaluate(name,*values) for name,values in scenarios().items()])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'models':[{k:m[k] for k in ('name','passed','linear_abs_max','log_abs_max','static_events')} for m in report['models']]}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__': main()
