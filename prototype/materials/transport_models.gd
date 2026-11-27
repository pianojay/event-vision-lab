extends RefCounted

# Callers validate the material registry before these pure numerical helpers.
# Parameter bounds and restricted geometry are in docs/research/materials/README.md.
static func subsurface_stripe(x_m: float, stripe_halfwidth_m: float,
		deposited_power_per_length: float, mu_a_m_inv: float, mu_s_reduced_m_inv: float,
		thickness_m: float) -> float:
	var diffusion := 1.0/(3.0*(mu_a_m_inv+mu_s_reduced_m_inv))
	var k := PI/thickness_m
	var kappa := sqrt(mu_a_m_inv/diffusion+k*k)
	var a := stripe_halfwidth_m
	var x := absf(x_m)
	var integral: float
	if x>=a:
		integral=exp(-kappa*(x-a))*(1.0-exp(-2.0*kappa*a))/kappa
	else:
		integral=(2.0-exp(-kappa*(a+x))-exp(-kappa*(a-x)))/kappa
	return deposited_power_per_length*k*k/(4.0*kappa)*integral/(2.0*a)/PI

static func square_view_factor(side_m: float, gap_m: float, samples: int = 32) -> float:
	var h := side_m/samples
	var total := 0.0
	for i in range(samples):
		var x := (i+0.5)*h
		for j in range(samples):
			var y := (j+0.5)*h
			var r2 := gap_m*gap_m+x*x+y*y
			total+=(side_m-x)*(side_m-y)*gap_m*gap_m/(PI*r2*r2)
	return 4.0*total*h*h/(side_m*side_m)

static func indirect_receiver(direct_irradiance_reflector: float, rho_reflector: float,
		rho_receiver: float, f_reflector_to_receiver: float, f_receiver_to_reflector: float,
		bounces: int = 16) -> float:
	var first := rho_reflector*direct_irradiance_reflector
	var second := 0.0
	var result := 0.0
	for bounce in range(bounces):
		var next_first := rho_reflector*f_reflector_to_receiver*second
		second=rho_receiver*f_receiver_to_reflector*first
		first=next_first
		result+=second
	return result/PI
