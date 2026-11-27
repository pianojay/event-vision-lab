import math
import unittest
from tools.materials.surface import (Surface, Medium, ThinPane, beer, diffuse, glossy,
    point_irradiance, fresnel, refract, slab, sphere, dot)
from tools.timing.timing_reference import SampledPixel


class SurfaceTests(unittest.TestCase):
    def test_invalid_boundaries(self):
        for action in [lambda: Surface(.8,.3), lambda: Surface(roughness=0),
                       lambda: ThinPane(.5,.6),lambda: Medium(-1),
                       lambda: beer(1,-1),lambda: diffuse(float('nan'),1)]:
            with self.assertRaises(ValueError): action()

    def test_beer_controls_and_composition(self):
        self.assertEqual(beer(0,10),1)
        self.assertEqual(beer(100,0),1)
        self.assertAlmostEqual(beer(2,.3)*beer(2,.2),beer(2,.5))
        # Independent implicit-midpoint integration of dI/dx=-mu*I.
        errors=[]
        for n in (10,20,40,80):
            q=2*.7/(2*n)
            reference=((1-q)/(1+q))**n
            errors.append(abs(reference-beer(2,.7)))
        self.assertTrue(all(b<a/3 for a,b in zip(errors,errors[1:])))
        self.assertLess(errors[-1],1e-5)

    def test_diffuse_cosine_distance_shadow(self):
        for angle in (0,.3,1.2,2.0):
            for distance in (.5,1,3):
                l=(distance*math.sin(angle),0,distance*math.cos(angle))
                got=diffuse(.4,point_irradiance((0,0,1),l,2))
                self.assertAlmostEqual(got,.4*2*max(0,math.cos(angle))/(math.pi*distance**2))
        self.assertEqual(point_irradiance((0,0,1),(0,0,1),2,False),0)
        self.assertEqual(diffuse(0,10),0)

    def test_constant_albedo_cancels_but_additive_light_does_not(self):
        def capture(rho,bg=0):
            pixel=SampledPixel()
            return [e for k in range(101) for e in pixel.feed(k/100,math.log(rho*math.exp(.8*k/100)+bg))]
        a,b=capture(.1),capture(.8)
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b): self.assertAlmostEqual(x.t,y.t)
        self.assertLess(len(capture(.1,.2)),len(capture(.8,.2)))

    def test_glossy_energy_reciprocity_and_peak_width(self):
        n=(0,0,1)
        for roughness in (.1,.3,1):
            for angle in (0,.7,1.4):
                l=(math.sin(angle),0,math.cos(angle))
                integral=0
                # Uniform solid-angle midpoint quadrature. Integral includes cos(theta_o).
                for z_index in range(100):
                    z=(z_index+.5)/100
                    for phi_index in range(200):
                        phi=math.tau*(phi_index+.5)/200
                        v=(math.sqrt(1-z*z)*math.cos(phi),math.sqrt(1-z*z)*math.sin(phi),z)
                        integral+=glossy(.7,roughness,n,l,v)*z*math.tau/(100*200)
                self.assertLessEqual(integral,.7001)
                v=(0,.6,.8)
                self.assertAlmostEqual(glossy(.7,roughness,n,l,v),glossy(.7,roughness,n,v,l))
        self.assertGreater(glossy(.7,.1,n,n,n),glossy(.7,.5,n,n,n))

    def test_pane_energy_and_limits(self):
        for pane in (ThinPane(0,1),ThinPane(0,0),ThinPane(.1,.6)):
            self.assertAlmostEqual(pane.reflection+pane.transmission+pane.absorption,1)
        self.assertEqual(ThinPane(0,1).radiance(2,4),2)
        self.assertEqual(ThinPane(0,0).radiance(2,4),0)
        self.assertAlmostEqual(ThinPane(.1,.6).radiance(2,4),1.6)

    def test_fresnel_snell_and_tir(self):
        self.assertAlmostEqual(fresnel(1,1,1.5),.04)
        self.assertEqual(fresnel(0,1,1),0)
        self.assertEqual(fresnel(math.cos(math.radians(60)),1.5,1),1)
        self.assertIsNone(refract((math.sin(math.radians(60)),0,-.5),(0,0,1),1.5,1))
        for angle in (0,.2,.7,1.3):
            ray=refract((math.sin(angle),0,-math.cos(angle)),(0,0,1),1,1.5)
            self.assertAlmostEqual(math.asin(ray[0]),math.asin(math.sin(angle)/1.5))

    def test_slab_displacement_energy(self):
        for eta in (1,1.3,1.5,2):
            for angle in (0,.3,.8):
                i=(math.sin(angle),0,-math.cos(angle))
                path=slab((0,0,0),i,(0,0,1),.2,Medium(.7,eta))
                theta_t=math.asin(math.sin(angle)/eta)
                self.assertAlmostEqual(path.exit_point[0],.2*math.tan(theta_t))
                self.assertAlmostEqual(path.path_m,.2/math.cos(theta_t))
                self.assertAlmostEqual(dot(path.exit_direction,i),1)
                self.assertAlmostEqual(path.transmission+path.reflection+path.absorption+path.internal_reflection,1)

    def test_sphere_independent_angle_geometry(self):
        for b in (-.8,-.3,0,.3,.8):
            for eta in (1,1.5,2):
                ray=sphere((b,0,3),(0,0,-1),(0,0,0),1,Medium(.5,eta))
                incident=math.asin(b)
                transmitted=math.asin(b/eta)
                deviation=2*(incident-transmitted)
                self.assertAlmostEqual(ray.exit_direction[0],-math.sin(deviation))
                self.assertAlmostEqual(ray.exit_direction[2],-math.cos(deviation))
                self.assertAlmostEqual(ray.path_m,2*math.cos(transmitted))
                self.assertAlmostEqual(ray.transmission+ray.reflection+ray.absorption+ray.internal_reflection,1)
        self.assertIsNone(sphere((2,0,3),(0,0,-1),(0,0,0),1))


if __name__=='__main__': unittest.main()
