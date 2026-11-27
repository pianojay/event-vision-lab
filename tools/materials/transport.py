"""Restricted steady spatial diffusion and diffuse patch transport."""
from dataclasses import dataclass
import math
from tools.materials.surface import bounded


@dataclass(frozen=True)
class DiffusionSlab:
    mu_a_m_inv: float = 1.0
    mu_s_reduced_m_inv: float = 500.0
    thickness_m: float = .04
    stripe_halfwidth_m: float = .008

    def __post_init__(self):
        bounded('mu_a_m_inv',self.mu_a_m_inv,.01,1000)
        bounded('mu_s_reduced_m_inv',self.mu_s_reduced_m_inv,1,10000)
        bounded('thickness_m',self.thickness_m,.001,10)
        bounded('stripe_halfwidth_m',self.stripe_halfwidth_m,1e-6,10)
        if self.mu_s_reduced_m_inv<10*self.mu_a_m_inv:
            raise ValueError('diffusion requires reduced scattering >=10*absorption')
        if self.thickness_m*(self.mu_a_m_inv+self.mu_s_reduced_m_inv)<10:
            raise ValueError('diffusion requires slab >=10 transport mean free paths')
        if self.stripe_halfwidth_m*(self.mu_a_m_inv+self.mu_s_reduced_m_inv)<3:
            raise ValueError('stripe halfwidth requires >=3 transport mean free paths')

    @property
    def diffusion_m(self):
        return 1/(3*(self.mu_a_m_inv+self.mu_s_reduced_m_inv))

    @property
    def k_m_inv(self):
        return math.pi/self.thickness_m

    @property
    def kappa_m_inv(self):
        return math.sqrt(self.mu_a_m_inv/self.diffusion_m+self.k_m_inv**2)

    def exit_flux(self,x_m,deposited_power_per_length=1.0):
        """One face's exit W/m^2 per arbitrary common radiometric scale.

        Entrance deposited power is a uniform stripe of integral P_line W/m.
        Interior source q=P_dep(x)*(pi/2H)*sin(pi*z/H) integrates to P_dep(x).
        This explicit depth-injection proxy is not ballistic surface lighting.
        Zero-fluence faces and infinite lateral extent define the PDE boundary.
        """
        bounded('x_m',x_m,-1e4,1e4)
        bounded('deposited_power_per_length',deposited_power_per_length,0,1e20)
        a,kappa=self.stripe_halfwidth_m,self.kappa_m_inv
        x=abs(x_m)
        if x>=a:
            integral=math.exp(-kappa*(x-a))*(-math.expm1(-2*kappa*a))/kappa
        else:
            integral=(2-math.exp(-kappa*(a+x))-math.exp(-kappa*(a-x)))/kappa
        return deposited_power_per_length*self.k_m_inv**2/(4*kappa)*integral/(2*a)

    def radiance(self,x_m,deposited_power_per_length=1.0):
        return self.exit_flux(x_m,deposited_power_per_length)/math.pi

    @property
    def total_escape_fraction(self):
        # Integral over both faces divided by total deposited power.
        return self.k_m_inv**2/self.kappa_m_inv**2


def square_view_factor(side_m,gap_m,samples=32):
    """Equal, aligned, parallel, unobstructed squares, facing each other.

    Area-pair integral reduced to separations using the overlap of two squares.
    Midpoint quadrature is deterministic. Compute once per geometry change.
    """
    bounded('side_m',side_m,1e-4,100)
    bounded('gap_m',gap_m,side_m*.5,side_m*100)
    if type(samples) is not int or not 2<=samples<=128:
        raise ValueError('samples must be integer in [2,128]')
    total=0.0
    h=side_m/samples
    for i in range(samples):
        x=(i+.5)*h
        for j in range(samples):
            y=(j+.5)*h
            total+=(side_m-x)*(side_m-y)*gap_m**2/(math.pi*(gap_m**2+x*x+y*y)**2)
    return 4*total*h*h/side_m**2


def indirect_receiver(direct_irradiance_reflector,rho_reflector,rho_receiver,
                      f_reflector_to_receiver,f_receiver_to_reflector,bounces=16):
    """Two uniform diffuse patch radiosities; receiver has NO direct source.

    F_ij means fraction leaving i that reaches j. Irradiance at i receives
    F_ij*B_j by reciprocity, so receiver uses its own outgoing F_21.
    bounces=0 disables indirect. bounces=1 permits reflector->receiver once.
    Each iteration transfers the preceding bounce. Exit radiance is B2/pi.
    """
    bounded('direct_irradiance_reflector',direct_irradiance_reflector,0,1e20)
    bounded('rho_reflector',rho_reflector,0,.95)
    bounded('rho_receiver',rho_receiver,0,.95)
    bounded('f_reflector_to_receiver',f_reflector_to_receiver,0,1)
    bounded('f_receiver_to_reflector',f_receiver_to_reflector,0,1)
    if type(bounces) is not int or not 0<=bounces<=64:
        raise ValueError('bounces must be integer in [0,64]')
    first=rho_reflector*direct_irradiance_reflector
    second=0.0
    result=0.0
    for _ in range(bounces):
        first,second=rho_reflector*f_reflector_to_receiver*second,rho_receiver*f_receiver_to_reflector*first
        result+=second
    return result/math.pi
