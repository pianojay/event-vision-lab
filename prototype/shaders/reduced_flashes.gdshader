shader_type canvas_item;
render_mode unshaded;
uniform bool reduced_flashes=true;
float limited_gray(vec3 value) {
    float linear_luminance=clamp(dot(value,vec3(0.2126,0.7152,0.0722)),0.0,1.0)*0.08;
    return linear_luminance<=0.0031308?12.92*linear_luminance:1.055*pow(linear_luminance,1.0/2.4)-0.055;
}
void fragment() {
    vec4 value=texture(TEXTURE,UV);
    if(reduced_flashes) value.rgb=vec3(limited_gray(value.rgb));
    COLOR=value;
}
