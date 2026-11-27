"""Prompt band conversion and causal pulse evidence using the existing ideal sensor."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
from tools.materials.emission import Fluorophore,Phosphor,Population
from tools.materials.validate_surface import evidence,evaluate,trace

PULSES=((0,.2,2),(.35,.6,1),(.7,.8,3))


def population_at(t,tau=.4):
    population=Population(Phosphor(tau,.6,.8))
    cursor=0.0
    for start,end,power in PULSES:
        if t<=cursor: break
        population.advance(max(0,min(t,start)-cursor),0)
        cursor=min(t,start)
        if t<=start: break
        population.advance(min(t,end)-start,power)
        cursor=min(t,end)
    if t>cursor: population.advance(t-cursor,0)
    return population.emitted_power/math.pi+.005


def independent_convolution(t,tau=.4):
    # Simpson integration of the causal Green function over each source pulse.
    stored=0.0
    n=64
    for start,end,power in PULSES:
        b=min(t,end)
        if b<=start: continue
        h=(b-start)/n
        total=0.0
        for k in range(n+1):
            s=start+k*h
            weight=1 if k in (0,n) else (4 if k%2 else 2)
            total+=weight*.6*power*math.exp(-(t-s)/tau)
        stored+=total*h/3
    return .8*stored/tau/math.pi+.005


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    fluor=Fluorophore()
    excitation=lambda t: math.exp(.7*math.sin(math.tau*t))
    h,c=6.62607015e-34,299792458
    def independent_fluor(t):
        photons=.8*excitation(t)/(h*c/(405e-9))
        return (.1*.2*excitation(t)+.9*photons*.7*h*c/(550e-9))/math.pi
    fluorescence=evaluate('fluorescence',lambda t: fluor.evaluate(excitation(t))['detector_radiance'],independent_fluor,
        lambda t: Fluorophore(quantum_yield=0).evaluate(excitation(t))['detector_radiance'],asdict(fluor))
    fluorescence['component_trace']=[{'time_s':k/240,**fluor.evaluate(excitation(k/240))} for k in range(241)]
    fluorescence['equal_detector_weighted_incident_band_controls']={
        'excitation_band':Fluorophore(detector_excitation=.5,detector_emission=.5).evaluate(1,0),
        'emission_band':Fluorophore(detector_excitation=.5,detector_emission=.5).evaluate(0,1)}
    afterglow=evaluate('phosphorescence',population_at,independent_convolution,lambda t:.005,
        {'lifetime_s':.4,'storage_yield':.6,'radiative_yield':.8,'pulses_start_end_power':PULSES,'background_radiance':.005,'initial_energy':0})
    equilibrium=Population()
    equilibrium.reset_material(.6*2*.4)
    equilibrium_trace=[]
    for _ in range(241):
        equilibrium_trace.append(equilibrium.emitted_power)
        equilibrium.advance(1/240,2)
    afterglow['static_protocol']='constant excitation at exact reservoir equilibrium; no held transient treated as static'
    afterglow['equilibrium_max_drift']=max(equilibrium_trace)-min(equilibrium_trace)
    afterglow['lifetime_and_sampling_sweeps']=[evaluate('tau_'+str(tau),lambda t,tau=tau:population_at(t,tau),
        lambda t,tau=tau:independent_convolution(t,tau),lambda t:.005,{'lifetime_s':tau})
        for tau in (.05,.2,1.0)]
    report=evidence([fluorescence,afterglow])
    report['passed']=report['passed'] and afterglow['equilibrium_max_drift']<1e-12 and all(s['passed'] for s in afterglow['lifetime_and_sampling_sweeps'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'models':[{k:m[k] for k in ('name','passed','linear_abs_max','log_abs_max','static_events')} for m in report['models']]}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__': main()
