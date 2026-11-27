shader_type canvas_item;
render_mode unshaded;
uniform sampler2D event_texture : filter_nearest, repeat_disable;
uniform sampler2D scene_texture : filter_nearest, repeat_disable;
uniform sampler2D activity_texture : filter_nearest, repeat_disable;
uniform bool polarity_color=false;
uniform bool reduced_flashes=true;
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
    float on=representation==2 ? (on_age<display_interval ? 1.0 : 0.0) : exp(-on_age/max(persistence,0.001));
    float off=representation==2 ? (off_age<display_interval ? 1.0 : 0.0) : exp(-off_age/max(persistence,0.001));
    if (representation==0) {
        vec2 counts=texture(activity_texture,UV).rg;
        on=1.0-exp(-0.55*counts.r);
        off=1.0-exp(-0.55*counts.g);
    }
    vec3 value=background+vec3(0.52)*(1.0-(1.0-on)*(1.0-off));
    if (polarity_color) value=background+vec3(0.12,0.42,0.46)*on+vec3(0.46,0.29,0.16)*off;
    if (representation==3) {
        vec3 linear=texture(scene_texture,UV).rgb;
        value=pow(max(linear/(linear+vec3(1.0)),vec3(0.0)),vec3(1.0/2.2));
    }
    if (reduced_flashes) value=vec3(clamp(dot(value,vec3(0.2126,0.7152,0.0722)),0.0,1.0)*0.08);
    COLOR=vec4(value,1.0);
}
