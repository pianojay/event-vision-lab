import math
import unittest
from tools.materials.transport import DiffusionSlab,square_view_factor,indirect_receiver
from tools.materials.transport_reference import diffusion_fd,interpolate,square_view_factor_4d,radiosity_solve


class TransportTests(unittest.TestCase):
    def test_regime_boundaries(self):
        for action in (lambda:DiffusionSlab(mu_s_reduced_m_inv=1),
                       lambda:DiffusionSlab(thickness_m=.001),
                       lambda:DiffusionSlab(stripe_halfwidth_m=.0001),
                       lambda:square_view_factor(.2,.01),
                       lambda:indirect_receiver(1,.99,.5,.1,.1)):
            with self.assertRaises(ValueError):action()

    def test_nonlocal_transport_and_energy(self):
        slab=DiffusionSlab()
        self.assertGreater(slab.radiance(.03),0)
        self.assertGreater(slab.radiance(0),slab.radiance(.03))
        self.assertEqual(slab.radiance(.03,0),0)
        self.assertAlmostEqual(slab.radiance(-.03),slab.radiance(.03))
        h=.0001
        total=2*sum(slab.exit_flux(-.2+(j+.5)*h)*h for j in range(4000))
        self.assertAlmostEqual(total,slab.total_escape_fraction,places=7)
        self.assertLess(total,1)

    def test_diffusion_independent_grid_convergence(self):
        slab=DiffusionSlab()
        errors=[]
        for cells in (401,801,1601,3201):
            xs,values=diffusion_fd(1,500,.04,.008,cells=cells)
            errors.append(max(abs(v-slab.exit_flux(x)) for x,v in zip(xs,values)))
        self.assertTrue(all(b<a for a,b in zip(errors,errors[1:])),errors)
        self.assertLess(errors[-1],.003)

    def test_diffusion_limits(self):
        self.assertGreater(DiffusionSlab(mu_a_m_inv=.1).total_escape_fraction,
                           DiffusionSlab(mu_a_m_inv=10).total_escape_fraction)
        self.assertGreater(DiffusionSlab(thickness_m=.02).total_escape_fraction,
                           DiffusionSlab(thickness_m=.08).total_escape_fraction)
        for thickness in (.02,.04,.08):
            slab=DiffusionSlab(thickness_m=thickness)
            xs,values=diffusion_fd(1,500,thickness,.008,cells=6401)
            self.assertAlmostEqual(interpolate(xs,values,.03),slab.exit_flux(.03),delta=.0002)

    def test_geometric_view_factor_independent_quadrature(self):
        for gap in (.1,.3,.6):
            approximate=square_view_factor(.2,gap,64)
            independent=square_view_factor_4d(.2,gap,32)
            self.assertAlmostEqual(approximate,independent,delta=.0004)
            self.assertTrue(0<approximate<1)
        self.assertGreater(square_view_factor(.2,.2),square_view_factor(.2,.4))

    def test_bounce_convergence_and_controls(self):
        f=square_view_factor(.2,.3)
        reference=radiosity_solve(3,.7,.6,f,f)[1]/math.pi
        errors=[]
        for bounces in (0,1,3,5,9):
            value=indirect_receiver(3,.7,.6,f,f,bounces)
            errors.append(abs(value-reference))
        self.assertTrue(all(b<a for a,b in zip(errors,errors[1:])),errors)
        self.assertLess(errors[-1],1e-10)
        self.assertEqual(indirect_receiver(3,0,.6,f,f),0)
        self.assertEqual(indirect_receiver(3,.7,.6,f,f,0),0)
        self.assertEqual(indirect_receiver(3,.7,.6,0,0),0)
        self.assertEqual(indirect_receiver(0,.7,.6,f,f),0)

    def test_reciprocal_unequal_patch_flux(self):
        # A1=.5, A2=1, F12=.4, F21=.2 obeys reciprocity.
        value=indirect_receiver(2,.7,.6,.4,.2,32)
        b1,b2=radiosity_solve(2,.7,.6,.4,.2)
        self.assertAlmostEqual(value,b2/math.pi)
        # Escaped + absorbed power equals externally deposited power rho1*E*A1.
        escaped=b1*(1-.4)*.5+b2*(1-.2)*1
        absorbed=(1-.7)*.4*b2*.5+(1-.6)*.2*b1*1
        self.assertAlmostEqual(escaped+absorbed,.7*2*.5)


if __name__=='__main__':unittest.main()
