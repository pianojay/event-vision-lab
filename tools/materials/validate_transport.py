"""Spatial diffusion, independent quadrature and bounce-convergence evidence."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
from tools.materials.transport import DiffusionSlab,square_view_factor,indirect_receiver
from tools.materials.transport_reference import diffusion_fd,interpolate,square_view_factor_4d,radiosity_solve
from tools.materials.validate_surface import evidence,evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    slab=DiffusionSlab()
    xs,flux=diffusion_fd(1,500,.04,.008,cells=12801)
    coordinate=lambda t:.02-.02*math.sin(math.tau*t)
    subsurface=evaluate('subsurface',lambda t:slab.radiance(coordinate(t),.03),
        lambda t:interpolate(xs,flux,coordinate(t))*.03/math.pi,
        lambda t:.03/(2*.008*math.pi) if abs(coordinate(t))<.008 else 0.0,
        {**asdict(slab),'deposited_power_per_length':.03,'observer_x_m':.02,'source_center_m':'.02*sin(2*pi*t)','receiver':'opposite slab face','temporal_transport':'instantaneous steady state'},
        tolerances=(1e-5,5e-5,1e-5))
    subsurface['spatial_profile']=[{'x_m':x,'exit_radiance':slab.radiance(x,.03),'fd_radiance':interpolate(xs,flux,x)*.03/math.pi,
                                  'entrance_deposition_per_area':.03/.016 if abs(x)<.008 else 0.0} for x in [j*.001 for j in range(-80,81)]]
    grid_sweep=[]
    for cells in (401,801,1601,3201,6401,12801):
        grid_x,grid_flux=diffusion_fd(1,500,.04,.008,cells=cells)
        grid_sweep.append({'cells':cells,'dx_m':.6/cells,'max_flux_error':max(abs(y-slab.exit_flux(x)) for x,y in zip(grid_x,grid_flux))})
    subsurface['independent_grid_convergence']=grid_sweep
    subsurface['thickness_absorption_scattering_sweep']=[]
    for thickness in (.02,.04,.08):
        for absorption in (.1,1,10):
            for scattering in (500,1000):
                model=DiffusionSlab(absorption,scattering,thickness,.008)
                grid_x,grid_flux=diffusion_fd(absorption,scattering,thickness,.008,cells=6401)
                subsurface['thickness_absorption_scattering_sweep'].append({**asdict(model),'escape_fraction_both_faces':model.total_escape_fraction,
                    'max_flux_error':max(abs(y-model.exit_flux(x)) for x,y in zip(grid_x,grid_flux))})
    subsurface['lateral_boundary_extent_sweep']=[{'extent_m':extent,'x_003_flux':interpolate(*diffusion_fd(1,500,.04,.008,extent=extent,cells=round(2*extent/.00005)),.03)} for extent in (.15,.3,.6)]
    f=square_view_factor(.2,.3,64)
    f_independent=square_view_factor_4d(.2,.3,48)
    source=lambda t:math.exp(.7*math.sin(math.tau*t))
    indirect=evaluate('interreflection',lambda t:indirect_receiver(source(t),.7,.6,f,f,16),
        lambda t:radiosity_solve(source(t),.7,.6,f_independent,f_independent)[1]/math.pi,
        lambda t:indirect_receiver(source(t),.7,.6,f,f,0),
        {'geometry':'equal aligned parallel facing square patches','side_m':.2,'gap_m':.3,'rho_reflector':.7,'rho_receiver':.6,'receiver_direct_irradiance':0,
         'direct_reflector_irradiance':'exp(.7*sin(2*pi*t))','view_factor':f,'independent_4d_view_factor':f_independent,'quadrature_axis_samples':64,'bounces':16},
        tolerances=(1e-5,2e-4,5e-5))
    indirect['geometry_convergence']=[]
    for gap in (.1,.2,.3,.6):
        independent=square_view_factor_4d(.2,gap,48)
        indirect['geometry_convergence'].append({'gap_m':gap,'reference_4d_axis_samples':48,'reference':independent,
            'samples':[{'axis_samples':n,'value':square_view_factor(.2,gap,n),'abs_error':abs(square_view_factor(.2,gap,n)-independent)} for n in (4,8,16,32,64,128)]})
    independent=radiosity_solve(1,.7,.6,f,f)[1]/math.pi
    indirect['bounce_convergence']=[{'bounces':n,'radiance':indirect_receiver(1,.7,.6,f,f,n),'error_vs_linear_solve':abs(indirect_receiver(1,.7,.6,f,f,n)-independent)} for n in (0,1,2,3,5,9,16,32)]
    indirect['reflectance_sweep']=[{'rho_reflector':rho,'receiver_radiance':indirect_receiver(1,rho,.6,f,f,32)} for rho in (0,.1,.3,.6,.9)]
    indirect['zero_reflectance_control']=indirect_receiver(1,0,.6,f,f,16)
    indirect['ambient']=0
    report=evidence([subsurface,indirect])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'models':[{k:m[k] for k in ('name','passed','linear_abs_max','log_abs_max','static_events','event_comparison')} for m in report['models']]}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
