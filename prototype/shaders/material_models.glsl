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
    float lobe = exponent == 0.0 ? 1.0
        : pow(max(0.0, dot(reflect(-l,n),v)), exponent);
    return rho_s * (exponent + 1.0) / (2.0 * MAT_PI) * lobe;
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
// Return (direct detector radiance, converted detector radiance, absorbed power).
vec3 mat_fluorescence(float excitation_irradiance, float emission_band_irradiance,
        float absorption_fraction, float quantum_yield, float excitation_nm, float emission_nm,
        float detector_excitation, float detector_emission) {
    float absorbed=absorption_fraction*excitation_irradiance;
    float converted=absorbed*quantum_yield*excitation_nm/emission_nm;
    return vec3((detector_excitation*(excitation_irradiance-absorbed)
        +detector_emission*emission_band_irradiance)/MAT_PI,
        detector_emission*converted/MAT_PI,absorbed);
}
float mat_population_step(float stored_energy, float absorbed_power, float dt_s,
        float lifetime_s, float storage_yield) {
    float x=dt_s/lifetime_s;
    float uptake=x<0.001 ? x*(1.0-x*0.5+x*x/6.0) : 1.0-exp(-x);
    return stored_energy*exp(-x)+storage_yield*absorbed_power*lifetime_s*uptake;
}
float mat_afterglow_power(float stored_energy, float lifetime_s, float radiative_yield) {
    return radiative_yield*stored_energy/lifetime_s;
}
float mat_subsurface_stripe(float x_m, float stripe_halfwidth_m,
        float deposited_power_per_length, float mu_a_m_inv, float mu_s_reduced_m_inv,
        float thickness_m) {
    float D=1.0/(3.0*(mu_a_m_inv+mu_s_reduced_m_inv));
    float k=MAT_PI/thickness_m;
    float kappa=sqrt(mu_a_m_inv/D+k*k);
    float a=stripe_halfwidth_m;
    float x=abs(x_m);
    float integral;
    if (x>=a) integral=exp(-kappa*(x-a))*(1.0-exp(-2.0*kappa*a))/kappa;
    else integral=(2.0-exp(-kappa*(a+x))-exp(-kappa*(a-x)))/kappa;
    return deposited_power_per_length*k*k/(4.0*kappa)*integral/(2.0*a)/MAT_PI;
}
// Equal aligned facing squares only; compute once per geometry change on host.
float mat_square_view_factor(float side_m, float gap_m, int samples) {
    float h=side_m/float(samples);
    float total=0.0;
    for (int i=0;i<samples;i++) {
        float x=(float(i)+0.5)*h;
        for (int j=0;j<samples;j++) {
            float y=(float(j)+0.5)*h;
            float r2=gap_m*gap_m+x*x+y*y;
            total+=(side_m-x)*(side_m-y)*gap_m*gap_m/(MAT_PI*r2*r2);
        }
    }
    return 4.0*total*h*h/(side_m*side_m);
}
float mat_indirect_receiver(float direct_irradiance_reflector, float rho_reflector,
        float rho_receiver, float f_reflector_to_receiver, float f_receiver_to_reflector,
        int bounces) {
    float first=rho_reflector*direct_irradiance_reflector;
    float second=0.0;
    float result=0.0;
    for (int bounce=0;bounce<bounces;bounce++) {
        float next_first=rho_reflector*f_reflector_to_receiver*second;
        second=rho_receiver*f_receiver_to_reflector*first;
        first=next_first;
        result+=second;
    }
    return result/MAT_PI;
}
#endif
