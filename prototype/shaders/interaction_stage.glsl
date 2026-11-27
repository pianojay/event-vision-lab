// Included after the legacy Parameters block and material_models.glsl.
layout(std430,set=0,binding=1) readonly buffer StageState { vec4 control; vec4 motion; vec4 transport; vec4 material[9]; } s;
vec3 stage_debug=vec3(-1.0);
vec3 stage_center(int i) { return vec3(float(i%3-1)*3.0,6.0-float(i/3)*2.5,-3.0); }
void stage_plane(vec3 ro,vec3 rd,vec3 center,vec3 normal,vec3 axis,vec2 halfsize,int id,inout float nearest,inout vec3 n,inout int station) {
    float denom=dot(rd,normal);
    if(abs(denom)<1e-6) return;
    float t=dot(center-ro,normal)/denom;
    vec3 local=ro+rd*t-center;
    if(t>0.001 && t<nearest && abs(dot(local,axis))<halfsize.x && abs(dot(local,cross(normal,axis)))<halfsize.y) {
        nearest=t; n=denom<0.0?normal:-normal; station=id;
    }
}
float stage_intersect(vec3 ro,vec3 rd,out vec3 n,out int id) {
    float nearest=1000.0; id=-1; n=vec3(0,0,1);
    for(int i=0;i<9;i++) {
        vec3 c=stage_center(i); c.x+=s.motion.x;
        if(i==1 || i==2 || i==4) {
            vec3 sphere_center=c+(i==4?vec3(-0.46,0,0):vec3(0));
            float radius=i==4?0.43:0.8;
            vec3 oc=ro-sphere_center; float b=dot(oc,rd), d=b*b-dot(oc,oc)+radius*radius;
            float t=d>0.0?-b-sqrt(d):-1.0;
            if(t>0.001 && t<nearest) {nearest=t;n=normalize(ro+rd*t-sphere_center);id=i;}
            if(i==4) stage_plane(ro,rd,c+vec3(0.47,0,0),vec3(0,0,1),vec3(1,0,0),vec2(0.4,0.8),14,nearest,n,id);
        } else if(i==8) {
            stage_plane(ro,rd,c+vec3(0,0.6,0),vec3(0,-1,0),vec3(1,0,0),vec2(0.5),8,nearest,n,id);
            stage_plane(ro,rd,c-vec3(0,0.6,0),vec3(0,1,0),vec3(1,0,0),vec2(0.5),9,nearest,n,id);
            // Baffle outside the mutual patch volume blocks source-to-receiver rays.
            stage_plane(ro,rd,c+vec3(0,0.4,1.0),vec3(0,0,1),vec3(1,0,0),vec2(0.8,0.28),10,nearest,n,id);
        } else {
            stage_plane(ro,rd,c,vec3(0,0,1),vec3(1,0,0),vec2(0.95),i,nearest,n,id);
            if(i==7) stage_plane(ro,rd,c-vec3(0,0,s.material[7].z),vec3(0,0,-1),vec3(1,0,0),vec2(0.95),17,nearest,n,id);
        }
    }
    return nearest;
}
float stage_pattern(vec3 ro,vec3 rd) {
    // Actual fixed back/front planes, sampled with the transmitted/reflected ray.
    float z=rd.z<0.0?-5.0:4.0;
    if(abs(rd.z)<1e-6) return 0.02;
    float t=(z-ro.z)/rd.z;
    if(t<0.0) return 0.02;
    vec3 q=ro+rd*t;
    float checker=mod(floor(q.x*4.0)+floor(q.y*4.0),2.0);
    return mix(0.08,0.8,checker);
}
float stage_radiance(vec3 ro,vec3 rd) {
    vec3 n; int id; float distance=stage_intersect(ro,rd,n,id);
    if(id<0) return stage_pattern(ro,rd);
    vec3 hit=ro+rd*distance;
    if(id==10) return 0.008;
    int i=min(id,8); if(id==17) i=7; if(id==14) i=4;
    vec3 c=stage_center(i)+vec3(s.motion.x,0,0);
    vec4 a=s.material[i];
    bool effect=s.control.z>0.5 || int(s.control.y)!=i;
    vec3 l=normalize(p.light.xyz-hit);
    float d2=max(dot(p.light.xyz-hit,p.light.xyz-hit),0.01);
    float strobe=p.world.z>0.5?(fract(p.clock.x*p.stimulus.x)<0.25?1.0:0.0):1.0;
    float power=p.world.y*p.world.w*strobe;
    vec3 sn; int sid; float shadow=stage_intersect(hit+n*0.002,l,sn,sid);
    float E=power*max(dot(n,l),0.0)/d2*(shadow*shadow<d2?0.0:1.0);
    float transmitted=stage_pattern(hit+rd*0.002,rd);
    float reflected=stage_pattern(hit+n*0.002,reflect(rd,n));
    if(i==0) return transmitted*mat_beer(effect?a.x:0.0,a.y/max(abs(dot(rd,n)),0.001));
    if(i==1) return mat_diffuse(effect?a.x:0.25,E);
    if(i==2) return mat_diffuse(a.x,E)+(effect?mat_glossy(a.y,a.z,n,l,-rd)*E:0.0);
    if(i==3) {vec3 weights=mat_thin_weights(a.x,effect?a.y:0.0); return weights.x*reflected+weights.y*transmitted;}
    if(i==4) {
        vec3 exit_point,exit_direction; vec4 energy;
        bool trace;
        if(id==14) trace=mat_slab(hit,rd,n,a.y,1.0,effect?a.x:1.0,a.z,exit_point,exit_direction,energy);
        else trace=mat_sphere(ro,rd,c-vec3(0.46,0,0),0.43,1.0,effect?a.x:1.0,a.z,exit_point,exit_direction,energy);
        if(int(s.control.w)==1) stage_debug=vec3(energy.z);
        if(int(s.control.w)==2) stage_debug=vec3(energy.w);
        return energy.x*reflected+(trace?energy.y*stage_pattern(exit_point+exit_direction*0.002,exit_direction):0.0);
    }
    if(i==5) {
        // Same point source, two narrow bands. Detector excitation sensitivity=.1, emission=1.
        vec3 bands=mat_fluorescence(E*s.motion.w,E*(1.0-s.motion.w),a.x,effect?a.y:0.0,a.z,a.w,0.1,1.0);
        if(int(s.control.w)==1) stage_debug=vec3(bands.x);
        if(int(s.control.w)==2) stage_debug=vec3(bands.y);
        return bands.x+bands.y;
    }
    if(i==6) return effect?s.motion.z/MAT_PI:0.0;
    if(i==7) {
        float x=hit.x-c.x-s.motion.y;
        // Rear source illuminates a finite stripe. Opposite face gets steady slab transport.
        if(id==17) return abs(x)<a.w?power:0.0;
        return effect?mat_subsurface_stripe(x,a.w,power*2.0*a.w,a.x,a.y,a.z):0.0;
    }
    // Uniform-patch radiosity with a dedicated source at (0,-.6,3) relative to the pair.
    // Baffle spans x+-0.8,y[.12,.68],z=1; reflector-to-receiver paths stay at |z|<=.5.
    vec3 source=c+vec3(0,-0.6,3.0);
    vec3 reflector=c-vec3(0,0.6,0);
    // Source raised slightly above reflector to avoid grazing incidence.
    source.y+=0.3;
    vec3 source_ray=source-reflector;
    float Ein=power*max(normalize(source_ray).y,0.0)/dot(source_ray,source_ray);
    if(id==9) return mat_diffuse(a.x,Ein);
    return mat_indirect_receiver(Ein,a.x,a.y,s.transport.x,s.transport.x,effect?int(a.w):0);
}
