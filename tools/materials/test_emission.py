import math
import unittest
from tools.materials.emission import Fluorophore, Phosphor, Population
from tools.timing.timing_reference import SampledPixel


class EmissionTests(unittest.TestCase):
    def test_fluorescence_photon_budget(self):
        p=Fluorophore()
        result=p.evaluate(3,.4)
        # Independent photon count through Planck's relation E=h*c/lambda.
        h,c=6.62607015e-34,299792458
        excitation_photons=3*.8/(h*c/(405e-9))
        emitted=excitation_photons*.7*(h*c/(550e-9))
        self.assertAlmostEqual(result['converted_emission_power'],emitted)
        self.assertAlmostEqual(result['direct_excitation_power']+result['direct_emission_band_power']+
                               result['converted_emission_power']+result['heat_power'],3.4)

    def test_band_control_and_prompt(self):
        p=Fluorophore(detector_excitation=.5,detector_emission=.5)
        self.assertGreater(p.evaluate(1,0)['converted_detector_radiance'],0)
        self.assertEqual(p.evaluate(0,1)['converted_detector_radiance'],0)
        self.assertEqual(p.evaluate(0,0)['detector_radiance'],0)
        self.assertEqual(Fluorophore(quantum_yield=0).evaluate(1)['converted_emission_power'],0)

    def test_invalid_material_parameters(self):
        for action in (lambda: Fluorophore(excitation_nm=650,emission_nm=500),
                       lambda: Fluorophore(quantum_yield=2),lambda: Phosphor(lifetime_s=0),
                       lambda: Population().advance(-1,1)):
            with self.assertRaises(ValueError): action()

    def test_causal_energy_and_reset(self):
        population=Population()
        p=population.parameters
        step=population.advance(.2,2)
        self.assertAlmostEqual(step['stored_energy']+step['emitted_energy']+step['heat_energy'],.4)
        before=population.emitted_power
        step=population.advance(.3,0)
        self.assertAlmostEqual(population.emitted_power,before*math.exp(-.3/p.lifetime_s))
        self.assertGreater(population.emitted_power,0)
        saved=population.stored_energy
        sensor=SampledPixel()
        sensor.feed(0,math.log(population.emitted_power))
        sensor.feed(.1,math.log(population.emitted_power),reset=True)
        self.assertEqual(population.stored_energy,saved)
        population.advance(0,100)
        self.assertEqual(population.stored_energy,saved)
        population.reset_material()
        self.assertEqual(population.emitted_power,0)

    def test_partition_invariance_and_repeated_excitation(self):
        coarse=Population()
        fine=Population()
        for power in (1,0,2,0,1):
            coarse.advance(.2,power)
            for _ in range(200): fine.advance(.001,power)
        self.assertAlmostEqual(coarse.stored_energy,fine.stored_energy,places=12)

    def test_independent_rk4_population(self):
        population=Population(Phosphor(.17,.6,.8))
        reference=0.0
        for power in (2,0,1,0):
            population.advance(.1,power)
            h=.1/100
            def derivative(u): return .6*power-u/.17
            for _ in range(100):
                a=derivative(reference); b=derivative(reference+h*a/2)
                c=derivative(reference+h*b/2); d=derivative(reference+h*c)
                reference+=h*(a+2*b+2*c+d)/6
            self.assertAlmostEqual(population.stored_energy,reference,places=10)


if __name__=='__main__': unittest.main()
