#[compute]
#version 450
// Ideal sensor consumes the optical FP32 detector intensity in alpha.
layout(local_size_x=8, local_size_y=8, local_size_z=1) in;
layout(set=0, binding=0, std430) buffer SensorState { vec4 pixels[]; } state;
layout(rgba32f, set=0, binding=1) uniform readonly image2D optical_input;
layout(rgba32f, set=0, binding=2) uniform writeonly image2D events_out;
layout(rgba32f, set=0, binding=3) uniform image2D activity_out;
layout(set=0, binding=4, std430) buffer Diagnostics { vec4 pixels[]; } diagnostics;
layout(push_constant, std430) uniform Parameters {
    vec4 clock;      // sample time, elapsed sample time, reset, constant-input test
    vec4 sensor;     // ON threshold, OFF threshold, activity decay seconds, test intensity
    vec4 camera;     // camera xyz, yaw
    vec4 optics;     // pitch, width, height, tan(half vertical FOV)
    vec4 world;      // moving object phase, lamp on, strobe enabled, light strength
    vec4 stimulus;   // strobe Hz, panel phase, matte sphere control, control albedo
    vec4 light;      // point source xyz, unused; independent from camera
} p;

void main() {
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy), size=ivec2(p.optics.yz);
    if (any(greaterThanEqual(pixel,size))) return;
    uint index=uint(pixel.y*size.x+pixel.x);
    float intensity=max(imageLoad(optical_input,pixel).a,1e-6);
    float current=log(intensity);
    vec4 old=state.pixels[index]; // reference, last ON, last OFF, previous log I
    vec4 diagnostic=vec4(old.x,old.w,current,0.0);
    float on=0.0, off=0.0;
    if (p.clock.z>0.5) {
        old=vec4(current,-1000.0,-1000.0,current);
        diagnostic=vec4(current,current,current,0.0);
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
            diagnostic.w=polarity*count;
            old.x=crossing;
            if (polarity>0.0) { on=count; old.y=timestamp; }
            else { off=count; old.z=timestamp; }
        }
        old.w=current;
    }
    state.pixels[index]=old;
    diagnostics.pixels[index]=diagnostic;
    imageStore(events_out,pixel,vec4(on,off,old.y,old.z));
    // Event-derived activity integrates EVERY substep, including bursts which
    // precede the final sample of a displayed frame. Not an RGB reconstruction.
    vec4 history=p.clock.z>0.5 ? vec4(0.0) : imageLoad(activity_out,pixel);
    history.rg=history.rg*exp(-p.clock.y/max(p.sensor.z,0.001))+vec2(on,off);
    history.ba+=vec2(on,off);
    imageStore(activity_out,pixel,history);
}
