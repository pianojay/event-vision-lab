// Bounded optical models. SI geometry, scene-linear radiance, no sensor floor.
#ifndef EVENT_LAB_MATERIAL_MODELS
#define EVENT_LAB_MATERIAL_MODELS
const float MAT_PI = 3.14159265358979323846;
float mat_beer(float mu_a_m_inv, float path_m) {
    return exp(-mu_a_m_inv * path_m);
}
float mat_diffuse(float rho_d, float irradiance) {
    return rho_d * irradiance / MAT_PI;
}
float mat_glossy(float rho_s, float roughness, vec3 n, vec3 l, vec3 v) {
    if (dot(n,l) <= 0.0 || dot(n,v) <= 0.0) return 0.0;
    float exponent = 2.0 / (roughness * roughness) - 2.0;
    return rho_s * (exponent + 1.0) / (2.0 * MAT_PI)
        * pow(max(0.0, dot(reflect(-l,n),v)), exponent);
}
vec3 mat_thin_weights(float reflection, float transmission) {
    return vec3(reflection, transmission, 1.0-reflection-transmission);
}
float mat_fresnel(float cos_i, float eta_i, float eta_t) {
    if (eta_i == eta_t) return 0.0;
    float sin_t2 = (eta_i*eta_i)/(eta_t*eta_t)*(1.0-cos_i*cos_i);
    if (sin_t2 >= 1.0) return 1.0;
    float cos_t = sqrt(1.0-sin_t2);
    float rs = (eta_i*cos_i-eta_t*cos_t)/(eta_i*cos_i+eta_t*cos_t);
    float rp = (eta_t*cos_i-eta_i*cos_t)/(eta_t*cos_i+eta_i*cos_t);
    return 0.5*(rs*rs+rp*rp);
}
bool mat_refract(vec3 i, vec3 n, float eta_i, float eta_t, out vec3 transmitted) {
    float c = clamp(-dot(i,n),0.0,1.0);
    float ratio = eta_i/eta_t;
    float k = 1.0-ratio*ratio*(1.0-c*c);
    transmitted = vec3(0.0);
    if (k <= 0.0) return false;
    transmitted = normalize(ratio*i+(ratio*c-sqrt(k))*n);
    return true;
}
// energy=(front reflected, transmitted, absorbed, untraced internal reflected).
// False means no primary transmitted path. No internal reflection is mislabelled absorption.
bool mat_slab(vec3 entry, vec3 incident, vec3 normal, float thickness_m,
        float eta_outside, float eta, float mu_a_m_inv,
        out vec3 exit_point, out vec3 exit_direction, out vec4 energy) {
    exit_point = entry;
    exit_direction = vec3(0.0);
    energy = vec4(1.0,0.0,0.0,0.0);
    vec3 inside;
    if (!mat_refract(incident,normal,eta_outside,eta,inside)) return false;
    float front_r = mat_fresnel(clamp(-dot(incident,normal),0.0,1.0),eta_outside,eta);
    float distance = thickness_m / (-dot(inside,normal));
    exit_point = entry + inside*distance;
    float attenuation = mat_beer(mu_a_m_inv,distance);
    float back_r = mat_fresnel(clamp(-dot(inside,normal),0.0,1.0),eta,eta_outside);
    energy = vec4(front_r,(1.0-front_r)*attenuation*(1.0-back_r),
        (1.0-front_r)*(1.0-attenuation),(1.0-front_r)*attenuation*back_r);
    return mat_refract(inside,normal,eta,eta_outside,exit_direction);
}
bool mat_sphere(vec3 origin, vec3 incident, vec3 center, float radius_m,
        float eta_outside, float eta, float mu_a_m_inv,
        out vec3 exit_point, out vec3 exit_direction, out vec4 energy) {
    exit_point=origin; exit_direction=vec3(0.0); energy=vec4(0.0);
    vec3 oc=origin-center;
    float b=dot(oc,incident);
    float discr=b*b-dot(oc,oc)+radius_m*radius_m;
    if (discr <= 0.0 || -b-sqrt(discr) <= 0.0) return false;
    vec3 entry=origin+incident*(-b-sqrt(discr));
    vec3 normal=normalize(entry-center);
    float front_r=mat_fresnel(clamp(-dot(incident,normal),0.0,1.0),eta_outside,eta);
    energy=vec4(1.0,0.0,0.0,0.0);
    vec3 inside;
    if (!mat_refract(incident,normal,eta_outside,eta,inside)) return false;
    float distance=-2.0*dot(entry-center,inside);
    exit_point=entry+inside*distance;
    vec3 exit_normal=-normalize(exit_point-center);
    float back_r=mat_fresnel(clamp(-dot(inside,exit_normal),0.0,1.0),eta,eta_outside);
    float attenuation=mat_beer(mu_a_m_inv,distance);
    energy=vec4(front_r,(1.0-front_r)*attenuation*(1.0-back_r),
        (1.0-front_r)*(1.0-attenuation),(1.0-front_r)*attenuation*back_r);
    return mat_refract(inside,exit_normal,eta,eta_outside,exit_direction);
}
#endif
