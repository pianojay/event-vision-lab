"""Independent discretizations for the bounded transport experiments."""
import math


def diffusion_fd(mu_a,mu_s,thickness,halfwidth,power_line=1.0,extent=.3,cells=2401):
    """Cell-centred finite differences, zero at far lateral boundaries.

    Separating sin(pi*z/H) from the 2D PDE leaves a screened 1D Poisson equation.
    The finite-volume source integrates the stripe/cell overlap, so source
    energy does not change when the grid crosses the illumination boundary.
    A Thomas solve is independent of the analytic exponential convolution.
    """
    dx=2*extent/cells
    xs=[-extent+(j+.5)*dx for j in range(cells)]
    d=1/(3*(mu_a+mu_s))
    k=math.pi/thickness
    coupling=d/dx**2
    diag=2*coupling+mu_a+d*k*k
    rhs=[]
    for x in xs:
        overlap=max(0,min(x+dx/2,halfwidth)-max(x-dx/2,-halfwidth))
        rhs.append(power_line/(2*halfwidth)*(overlap/dx)*k/2)
    # Ghost cells at boundaries have zero fluence. Boundary error decays
    # exponentially and is measured through an independent extent sweep.
    upper=[-coupling/diag]
    solution=[rhs[0]/diag]
    for j in range(1,cells):
        divisor=diag+coupling*upper[-1]
        upper.append(-coupling/divisor)
        solution.append((rhs[j]+coupling*solution[-1])/divisor)
    for j in range(cells-2,-1,-1):
        solution[j]-=upper[j]*solution[j+1]
    return xs,[d*k*u for u in solution]


def interpolate(xs,values,x):
    position=(x-xs[0])/(xs[1]-xs[0])
    i=max(0,min(len(xs)-2,int(math.floor(position))))
    fraction=max(0,min(1,position-i))
    return values[i]*(1-fraction)+values[i+1]*fraction


def square_view_factor_4d(side,gap,samples=16):
    """Direct midpoint integral over both physical patch areas, no convolution."""
    h=side/samples
    points=[((i+.5)*h,(j+.5)*h) for i in range(samples) for j in range(samples)]
    total=0.0
    for ax,ay in points:
        for bx,by in points:
            r2=gap*gap+(bx-ax)**2+(by-ay)**2
            # cos(theta_a)*cos(theta_b)/pi/r^2.
            total+=gap*gap/(math.pi*r2*r2)
    return total*h**4/side**2


def radiosity_solve(irradiance,rho_1,rho_2,f12,f21):
    """Gaussian elimination of B1-rho1*F12*B2=rho1*E, B2-rho2*F21*B1=0."""
    matrix=[[1.,-rho_1*f12,rho_1*irradiance],[-rho_2*f21,1.,0.]]
    factor=matrix[1][0]/matrix[0][0]
    for j in range(3): matrix[1][j]-=factor*matrix[0][j]
    b2=matrix[1][2]/matrix[1][1]
    b1=(matrix[0][2]-matrix[0][1]*b2)/matrix[0][0]
    return b1,b2
