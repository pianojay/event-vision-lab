#[compute]
#version 450
// Ideal sensor consumes the optical FP32 detector intensity in alpha.
layout(local_size_x=8, local_size_y=8, local_size_z=1) in;
layout(set=0, binding=0, std430) buffer SensorState { vec4 pixels[]; } state;
layout(rgba32f, set=0, binding=1) uniform readonly image2D optical_input;
layout(rgba32f, set=0, binding=2) uniform writeonly image2D events_out;
layout(rgba32f, set=0, binding=3) uniform image2D activity_out;
layout(set=0, binding=4, std430) buffer Diagnostics { vec4 pixels[]; } diagnostics;
layout(set=0, binding=5, std430) buffer ReferenceAnchors { vec4 pixels[]; } anchors;
layout(push_constant, std430) uniform Parameters {
    vec4 clock;      // sample time, elapsed sample time, reset, constant-input test
    vec4 sensor;     // ON threshold, OFF threshold, activity decay seconds, test intensity
    vec4 camera;     // camera xyz, yaw
    vec4 optics;     // pitch, width, height, tan(half vertical FOV)
    vec4 world;      // moving object phase, lamp on, strobe enabled, light strength
    vec4 stimulus;   // strobe Hz, panel phase, matte sphere control, control albedo
    vec4 light;      // point source xyz, occluder enabled
} p;

// Preserve small contrast around the anchor instead of subtracting rounded logs.
float relative_log(float intensity, float anchor_intensity, float anchor_log) {
    float delta=intensity-anchor_intensity;
    if (abs(delta)<=0.01*anchor_intensity) {
        precise float z=delta/(intensity+anchor_intensity);
        precise float z2=z*z;
        precise float result=2.0*z*(1.0+z2*(1.0/3.0+z2/5.0));
        return result;
    }
    return log(intensity)-anchor_log;
}

void main() {
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy), size=ivec2(p.optics.yz);
    if (any(greaterThanEqual(pixel,size))) return;
    uint index=uint(pixel.y*size.x+pixel.x);
    float intensity=max(imageLoad(optical_input,pixel).a,1e-6);
    float current=log(intensity);
    vec4 old=state.pixels[index]; // reference, last ON, last OFF, previous log I
    vec4 counts=anchors.pixels[2*index]; // anchor log, ON count, OFF count, anchor intensity
    vec4 thresholds=anchors.pixels[2*index+1]; // ON, OFF, previous intensity, unused
    float on=0.0, off=0.0;
    if (p.clock.z>0.5) {
        old=vec4(current,-1000.0,-1000.0,current);
        counts=vec4(current,0,0,intensity);
        thresholds.z=intensity;
    } else if (thresholds.x!=p.sensor.x || thresholds.y!=p.sensor.y) {
        old.x=old.w;
        counts=vec4(old.w,0,0,thresholds.z);
    }
    precise float old_on=counts.y*p.sensor.x;
    precise float old_off=counts.z*p.sensor.y;
    precise float offset=old_on-old_off;
    float previous_relative=relative_log(thresholds.z,counts.w,counts.x);
    float current_relative=relative_log(intensity,counts.w,counts.x);
    vec4 diagnostic=vec4(offset,previous_relative,current_relative,0.0);
    vec4 levels=vec4(counts.yz,p.sensor.xy);
    if (p.clock.z<0.5) {
        float difference=current_relative-offset;
        float polarity=difference>=0.0 ? 1.0 : -1.0;
        float threshold=polarity>0.0 ? p.sensor.x : p.sensor.y;
        float count=floor(abs(difference)/threshold);
        precise float new_on=(counts.y+(polarity>0.0 ? count : 0.0))*p.sensor.x;
        precise float new_off=(counts.z+(polarity<0.0 ? count : 0.0))*p.sensor.y;
        precise float crossing=new_on-new_off;
        if (polarity*(crossing-current_relative)>0.0) {
            count=max(0.0,count-1.0);
        } else {
            precise float next_on=(counts.y+(polarity>0.0 ? count+1.0 : 0.0))*p.sensor.x;
            precise float next_off=(counts.z+(polarity<0.0 ? count+1.0 : 0.0))*p.sensor.y;
            precise float next_crossing=next_on-next_off;
            if (polarity*(next_crossing-current_relative)<=0.0) count+=1.0;
        }
        if (count>0.0) {
            counts.y+=polarity>0.0 ? count : 0.0;
            counts.z+=polarity<0.0 ? count : 0.0;
            new_on=counts.y*p.sensor.x;
            new_off=counts.z*p.sensor.y;
            crossing=new_on-new_off;
            float denominator=current_relative-previous_relative;
            float fraction=abs(denominator)>1e-10 ? clamp((crossing-previous_relative)/denominator,0.0,1.0) : 1.0;
            float timestamp=p.clock.x-p.clock.y+fraction*p.clock.y;
            diagnostic.w=polarity*count;
            old.x=counts.x+crossing;
            if (polarity>0.0) { on=count; old.y=timestamp; }
            else { off=count; old.z=timestamp; }
        }
        old.w=current;
    }
    anchors.pixels[2*index]=counts;
    anchors.pixels[2*index+1]=vec4(p.sensor.xy,intensity,0);
    diagnostics.pixels[2*index]=diagnostic;
    diagnostics.pixels[2*index+1]=levels;
    state.pixels[index]=old;
    imageStore(events_out,pixel,vec4(on,off,old.y,old.z));
    vec4 history=p.clock.z>0.5 ? vec4(0.0) : imageLoad(activity_out,pixel);
    history.rg=history.rg*exp(-p.clock.y/max(p.sensor.z,0.001))+vec2(on,off);
    history.ba+=vec2(on,off);
    imageStore(activity_out,pixel,history);
}
