#[compute]
#version 450
// Each dispatch renders new linear radiance and updates an ideal event sensor.
// Scene generation is deliberately analytic: no TAA, exposure, or render noise.
layout(local_size_x=8, local_size_y=8, local_size_z=1) in;
layout(set=0, binding=0, std430) buffer SensorState { vec4 pixels[]; } state;
layout(rgba32f, set=0, binding=1) uniform writeonly image2D radiance_out;
layout(rgba32f, set=0, binding=2) uniform writeonly image2D events_out;
layout(rgba32f, set=0, binding=3) uniform image2D activity_out;
layout(push_constant, std430) uniform Parameters {
    vec4 clock;      // sample time, elapsed sample time, reset, constant-input test
    vec4 sensor;     // ON threshold, OFF threshold, activity decay seconds, test intensity
    vec4 camera;     // camera xyz, yaw
    vec4 optics;     // pitch, width, height, tan(half vertical FOV)
    vec4 world;      // moving object phase, lamp on, strobe enabled, light strength
    vec4 stimulus;   // strobe Hz, panel phase, matte sphere control, control albedo
    vec4 light;      // point source xyz, unused; independent from camera
} p;

vec3 moving_center() {
    return vec3(sin(p.world.x * 0.9) * 1.8, 0.5, -2.5);
}

void sphere_hit(vec3 ro, vec3 rd, vec3 center, float radius, float id,
                inout float nearest, inout vec3 normal, inout float material) {
    vec3 oc = ro - center;
    float b = dot(oc, rd), c = dot(oc, oc) - radius * radius;
    float discriminant = b*b-c;
    if (discriminant < 0.0) return;
    float t = -b-sqrt(discriminant);
    if (t > 0.001 && t < nearest) {
        nearest=t; normal=normalize(ro+rd*t-center); material=id;
    }
}

void box_hit(vec3 ro, vec3 rd, vec3 center, vec3 extent,
             inout float nearest, inout vec3 normal, inout float material) {
    vec3 safe_rd = mix(vec3(1e-7), rd, greaterThan(abs(rd), vec3(1e-7)));
    vec3 a=(center-extent-ro)/safe_rd, b=(center+extent-ro)/safe_rd;
    vec3 lo=min(a,b), hi=max(a,b);
    float t=max(max(lo.x,lo.y),lo.z), far_t=min(min(hi.x,hi.y),hi.z);
    if (t > 0.001 && t < far_t && t < nearest) {
        nearest=t;
        vec3 h=(ro+rd*t-center)/extent;
        vec3 ah=abs(h);
        normal=ah.x>ah.y && ah.x>ah.z ? vec3(sign(h.x),0,0) :
               ah.y>ah.z ? vec3(0,sign(h.y),0) : vec3(0,0,sign(h.z));
        material=4.0;
    }
}

float intersect_world(vec3 ro, vec3 rd, out vec3 normal, out float material) {
    float nearest=1000.0;
    normal=vec3(0,1,0); material=0.0;
    if (p.stimulus.z>0.5) {
        sphere_hit(ro,rd,vec3(0,1,-1),1.0,7.0,nearest,normal,material);
        return nearest;
    }
    if (abs(rd.y)>1e-6) {
        float t=-ro.y/rd.y;
        vec3 hit=ro+rd*t;
        if (t>0.001 && t<nearest && abs(hit.x)<5.0 && hit.z>-5.0 && hit.z<6.0) {
            nearest=t; normal=vec3(0,1,0); material=1.0;
        }
    }
    if (abs(rd.z)>1e-6) {
        float t=(-5.0-ro.z)/rd.z;
        vec3 hit=ro+rd*t;
        if (t>0.001 && t<nearest && abs(hit.x)<5.0 && hit.y>0.0 && hit.y<4.0) {
            nearest=t; normal=vec3(0,0,1); material=2.0;
            if (abs(hit.x)<1.15 && abs(hit.y-2.25)<0.5) material=6.0;
        }
    }
    if (abs(rd.x)>1e-6) {
        for(int side=-1; side<=1; side+=2) {
            float t=(float(side)*5.0-ro.x)/rd.x;
            vec3 hit=ro+rd*t;
            if(t>0.001 && t<nearest && hit.z>-5.0 && hit.z<6.0 && hit.y>0.0 && hit.y<4.0) {
                nearest=t; normal=vec3(-float(side),0,0); material=2.0;
            }
        }
    }
    sphere_hit(ro,rd,vec3(-1.4,0.9,-0.7),0.9,3.0,nearest,normal,material);
    sphere_hit(ro,rd,moving_center(),0.42,5.0,nearest,normal,material);
    box_hit(ro,rd,vec3(1.25,0.65,-1.5),vec3(0.65),nearest,normal,material);
    return nearest;
}

vec3 scene_radiance(vec2 uv) {
    float yaw=p.camera.w, pitch=p.optics.x;
    vec3 forward=vec3(sin(yaw)*cos(pitch),sin(pitch),-cos(yaw)*cos(pitch));
    vec3 right=normalize(cross(forward,vec3(0,1,0))), up=cross(right,forward);
    vec2 screen=uv*2.0-1.0;
    screen.y=-screen.y;
    vec3 rd=normalize(forward+right*screen.x*(p.optics.y/p.optics.z)*p.optics.w+up*screen.y*p.optics.w);
    vec3 n; float mat;
    float t=intersect_world(p.camera.xyz,rd,n,mat);
    if (mat==0.0) return vec3(0.015);
    vec3 hit=p.camera.xyz+rd*t;
    vec3 albedo=vec3(0.55,0.6,0.65);
    if (mat==1.0) {
        float checker=mod(floor(hit.x*1.5)+floor(hit.z*1.5),2.0);
        albedo=mix(vec3(0.12),vec3(0.65),checker);
    } else if (mat==2.0) {
        float stripe=step(0.12,fract(hit.x*0.6+hit.z*0.6));
        albedo=mix(vec3(0.16),vec3(0.55,0.6,0.65),stripe);
    } else if (mat==3.0) {
        albedo=mix(vec3(0.06,0.22,0.28),vec3(0.3,0.75,0.8),step(0.5,fract(hit.y*4.0)));
    } else if (mat==4.0) {
        albedo=vec3(0.7,0.4,0.16);
    } else if (mat==5.0) {
        albedo=vec3(0.8,0.15,0.1);
    } else if (mat==6.0) {
        float pattern=0.1+0.9*step(0.5,fract(hit.x*3.0+p.stimulus.y*0.5));
        return vec3(pattern)*1.4;
    }
    if (mat==7.0) albedo=vec3(p.stimulus.w);
    vec3 to_light=p.light.xyz-hit;
    float distance=length(to_light);
    vec3 light_dir=to_light/distance;
    vec3 shadow_normal; float shadow_mat;
    float shadow_t=intersect_world(hit+n*0.004,light_dir,shadow_normal,shadow_mat);
    float visibility=shadow_t<distance ? 0.0 : 1.0;
    float strobe=p.world.z>0.5 ? (fract(p.clock.x*p.stimulus.x)<0.25 ? 1.0 : 0.0) : 1.0;
    float lamp=p.world.y*strobe*p.world.w;
    float direct=lamp*visibility*max(dot(n,light_dir),0.0)*6.0/(distance*distance+1.0);
    // Fixed ambient term + analytic direct illumination. No simulated GI.
    float specular=mat==7.0 ? 0.0 : pow(max(dot(reflect(-light_dir,n),-rd),0.0),32.0)*0.15;
    return albedo*(0.035+direct)+vec3(specular*lamp*visibility/(distance*distance+1.0));
}

void main() {
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy), size=ivec2(p.optics.yz);
    if (any(greaterThanEqual(pixel,size))) return;
    uint index=uint(pixel.y*size.x+pixel.x);
    vec3 radiance=p.clock.w>0.5 ? vec3(p.sensor.w) : scene_radiance((vec2(pixel)+0.5)/vec2(size));
    float intensity=max(dot(radiance,vec3(0.2126,0.7152,0.0722)),1e-6);
    float current=log(intensity);
    vec4 old=state.pixels[index]; // reference, last ON, last OFF, previous log I
    float on=0.0, off=0.0;
    if (p.clock.z>0.5) {
        old=vec4(current,-1000.0,-1000.0,current);
    } else {
        float difference=current-old.x;
        float threshold=difference>=0.0 ? p.sensor.x : p.sensor.y;
        float count=floor(abs(difference)/threshold+1e-5);
        if (count>0.0) {
            float polarity=difference>=0.0 ? 1.0 : -1.0;
            float crossing=old.x+polarity*count*threshold;
            float denominator=current-old.w;
            float fraction=abs(denominator)>1e-10 ? clamp((crossing-old.w)/denominator,0.0,1.0) : 1.0;
            float timestamp=p.clock.x-p.clock.y+fraction*p.clock.y;
            old.x=crossing;
            if (polarity>0.0) { on=count; old.y=timestamp; }
            else { off=count; old.z=timestamp; }
        }
        old.w=current;
    }
    state.pixels[index]=old;
    imageStore(radiance_out,pixel,vec4(radiance,1.0));
    imageStore(events_out,pixel,vec4(on,off,old.y,old.z));
    // Event-derived activity integrates EVERY substep, including bursts which
    // precede the final sample of a displayed frame. Not an RGB reconstruction.
    vec4 history=p.clock.z>0.5 ? vec4(0.0) : imageLoad(activity_out,pixel);
    history.rg=history.rg*exp(-p.clock.y/max(p.sensor.z,0.001))+vec2(on,off);
    history.ba+=vec2(on,off);
    imageStore(activity_out,pixel,history);
}
