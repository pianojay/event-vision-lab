shader_type canvas_item;
render_mode unshaded;
uniform bool reduced_flashes=true;
void fragment() {
    vec4 value=texture(TEXTURE,UV);
    if(reduced_flashes) value.rgb=vec3(clamp(dot(value.rgb,vec3(0.2126,0.7152,0.0722)),0.0,1.0)*0.08);
    COLOR=value;
}
