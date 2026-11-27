"""Bounded deterministic optical models. Geometry in metres; no sensor/display state."""
from dataclasses import dataclass
import math

Vec3 = tuple[float, float, float]


def bounded(name, value, low, high):
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")
    return value


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def add(a, b):
    return tuple(x+y for x, y in zip(a, b))


def mul(a, k):
    return tuple(x*k for x in a)


def sub(a, b):
    return add(a, mul(b, -1))


def unit(v):
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError("direction must be a finite xyz vector")
    length = math.sqrt(dot(v, v))
    if length <= 0:
        raise ValueError("direction must be nonzero")
    return mul(v, 1/length)


@dataclass(frozen=True)
class Surface:
    rho_d: float = 0.5
    rho_s: float = 0.0
    roughness: float = 0.3

    def __post_init__(self):
        bounded("rho_d", self.rho_d, 0, 1)
        bounded("rho_s", self.rho_s, 0, 1-self.rho_d)
        bounded("roughness", self.roughness, 0.1, 1)


@dataclass(frozen=True)
class Medium:
    mu_a_m_inv: float = 1.0
    eta: float = 1.5
    eta_outside: float = 1.0

    def __post_init__(self):
        bounded("mu_a_m_inv", self.mu_a_m_inv, 0, 10000)
        bounded("eta", self.eta, 0.8, 2.5)
        bounded("eta_outside", self.eta_outside, 0.8, 2.5)


@dataclass(frozen=True)
class ThinPane:
    reflection: float = 0.1
    transmission: float = 0.7

    def __post_init__(self):
        bounded("reflection", self.reflection, 0, 1)
        bounded("transmission", self.transmission, 0, 1-self.reflection)

    @property
    def absorption(self):
        return 1-self.reflection-self.transmission

    def radiance(self, background, reflected_environment):
        bounded("background", background, 0, 1e20)
        bounded("reflected_environment", reflected_environment, 0, 1e20)
        return self.transmission*background + self.reflection*reflected_environment


@dataclass(frozen=True)
class RayPath:
    exit_point: Vec3
    exit_direction: Vec3
    path_m: float
    transmission: float
    reflection: float
    absorption: float
    internal_reflection: float
    tir: bool = False


def beer(mu_a_m_inv, path_m):
    bounded("mu_a_m_inv", mu_a_m_inv, 0, 10000)
    bounded("path_m", path_m, 0, 10000)
    return math.exp(-mu_a_m_inv*path_m)


def diffuse(rho_d, irradiance):
    bounded("rho_d", rho_d, 0, 1)
    bounded("irradiance", irradiance, 0, 1e20)
    return rho_d*irradiance/math.pi


def point_irradiance(normal, light_delta, power_per_sr, visible=True):
    bounded("power_per_sr", power_per_sr, 0, 1e20)
    distance2 = dot(light_delta, light_delta)
    if distance2 <= 0:
        raise ValueError("point source cannot coincide with receiver")
    return power_per_sr*max(0, dot(unit(normal), unit(light_delta)))/distance2 if visible else 0.0


def glossy(rho_s, roughness, normal, to_light, to_view):
    """Reciprocal cosine-power BRDF, conservatively energy bounded, not GGX.

    Exponent s=2/r^2-2. Integral f*cos(theta_o) <= rho_s because cos<=1
    and the full reflected-direction hemisphere integral is 2*pi/(s+1).
    Constant rho_s replaces spectral Fresnel. Exact mirror delta is unsupported.
    """
    bounded("rho_s", rho_s, 0, 1)
    bounded("roughness", roughness, 0.1, 1)
    n, l, v = unit(normal), unit(to_light), unit(to_view)
    if dot(n,l) <= 0 or dot(n,v) <= 0:
        return 0.0
    exponent = 2/roughness**2-2
    reflected = sub(mul(n, 2*dot(n,l)), l)
    cosine = max(0.0, dot(reflected,v))
    return rho_s*(exponent+1)/(2*math.pi)*cosine**exponent


def fresnel(cos_i, eta_i, eta_t):
    """Unpolarized power reflectance at a smooth dielectric interface."""
    bounded("cos_i", cos_i, 0, 1)
    bounded("eta_i", eta_i, 0.8, 2.5)
    bounded("eta_t", eta_t, 0.8, 2.5)
    if eta_i == eta_t:
        return 0.0
    sin_t2 = (eta_i/eta_t)**2*(1-cos_i*cos_i)
    if sin_t2 >= 1:
        return 1.0
    cos_t = math.sqrt(1-sin_t2)
    rs = (eta_i*cos_i-eta_t*cos_t)/(eta_i*cos_i+eta_t*cos_t)
    rp = (eta_t*cos_i-eta_i*cos_t)/(eta_t*cos_i+eta_i*cos_t)
    return (rs*rs+rp*rp)/2


def refract(incident, normal_against_ray, eta_i, eta_t):
    i, n = unit(incident), unit(normal_against_ray)
    cosine = -dot(i,n)
    bounded("cosine against normal", cosine, -1e-12, 1+1e-12)
    cosine = min(1, max(0, cosine))
    ratio = eta_i/eta_t
    sin_t2 = ratio*ratio*(1-cosine*cosine)
    if sin_t2 >= 1:
        return None
    return unit(add(mul(i, ratio), mul(n, ratio*cosine-math.sqrt(1-sin_t2))))


def _path(entry, inside, exit_point, outward, medium, front_r):
    path = math.sqrt(dot(sub(exit_point,entry),sub(exit_point,entry)))
    attenuation = beer(medium.mu_a_m_inv,path)
    cos_exit = min(1,max(0,dot(inside,outward)))
    back_r = fresnel(cos_exit,medium.eta,medium.eta_outside)
    out = refract(inside,mul(outward,-1),medium.eta,medium.eta_outside)
    return RayPath(exit_point, out or (0.0,0.0,0.0),path,
                   (1-front_r)*attenuation*(1-back_r),front_r,
                   (1-front_r)*(1-attenuation),(1-front_r)*attenuation*back_r,
                   out is None)


def slab(entry, incident, normal, thickness_m, medium=Medium()):
    """Entry point lies on front plane; parallel rear plane is -normal*thickness.

    Primary transmitted path only. Internal-reflected energy is reported, never
    relabelled absorption. Incident and emerging rays share the outside medium.
    """
    bounded("thickness_m", thickness_m, 1e-6, 100)
    n, i = unit(normal), unit(incident)
    front_r = fresnel(min(1,max(0,-dot(i,n))),medium.eta_outside,medium.eta)
    inside = refract(i,n,medium.eta_outside,medium.eta)
    if inside is None:
        return RayPath(entry,(0,0,0),0,0,1,0,0,True)
    distance = thickness_m/(-dot(inside,n))
    return _path(entry,inside,add(entry,mul(inside,distance)),mul(n,-1),medium,front_r)


def sphere(origin, incident, center, radius_m, medium=Medium()):
    """Smooth homogeneous sphere; external camera; first transmitted chord."""
    bounded("radius_m", radius_m, 1e-6, 100)
    i, oc = unit(incident), sub(origin,center)
    if dot(oc,oc) <= radius_m*radius_m:
        raise ValueError("sphere origin must be outside")
    b = dot(oc,i)
    discr = b*b-dot(oc,oc)+radius_m*radius_m
    if discr <= 0 or -b-math.sqrt(discr) <= 0:
        return None
    entry = add(origin,mul(i,-b-math.sqrt(discr)))
    n = unit(sub(entry,center))
    front_r = fresnel(min(1,max(0,-dot(i,n))),medium.eta_outside,medium.eta)
    inside = refract(i,n,medium.eta_outside,medium.eta)
    if inside is None:
        return RayPath(entry,(0,0,0),0,0,1,0,0,True)
    chord = -2*dot(sub(entry,center),inside)
    end = add(entry,mul(inside,chord))
    return _path(entry,inside,end,unit(sub(end,center)),medium,front_r)
