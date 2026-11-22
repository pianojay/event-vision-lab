shader_type canvas_item;
render_mode unshaded;
uniform sampler2D event_texture : filter_nearest, repeat_disable;
uniform sampler2D scene_texture : filter_nearest, repeat_disable;
uniform float sample_time=0.0;
uniform float persistence=0.15;
uniform int representation=0;
// One display frame can span several sensor samples. Retain every sample's
// contribution using crossing timestamps rather than only the final sample.
uniform float display_interval=0.0167;
void fragment() {
    vec4 events=texture(event_texture,UV);
    vec3 background=vec3(0.008,0.014,0.025);
    float on_age=max(sample_time-events.b,0.0);
    float off_age=max(sample_time-events.a,0.0);
    float on=representation==1 ? (on_age<display_interval ? 1.0 : 0.0) : exp(-on_age/max(persistence,0.001));
    float off=representation==1 ? (off_age<display_interval ? 1.0 : 0.0) : exp(-off_age/max(persistence,0.001));
    vec3 value=background+vec3(0.18,0.9,1.0)*on+vec3(1.0,0.28,0.15)*off;
    if (representation==2) {
        vec3 linear=texture(scene_texture,UV).rgb;
        value=pow(max(linear/(linear+vec3(1.0)),vec3(0.0)),vec3(1.0/2.2));
    }
    COLOR=vec4(value,1.0);
}
