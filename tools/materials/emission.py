"""Two-band prompt conversion and causal metastable energy, before sensing."""
from dataclasses import dataclass
import math
from tools.materials.surface import bounded


@dataclass(frozen=True)
class Fluorophore:
    excitation_nm: float = 405.0
    emission_nm: float = 550.0
    absorption_fraction: float = .8
    quantum_yield: float = .7
    detector_excitation: float = .1
    detector_emission: float = .9

    def __post_init__(self):
        bounded("excitation_nm",self.excitation_nm,300,700)
        bounded("emission_nm",self.emission_nm,max(400,self.excitation_nm),900)
        for name in ('absorption_fraction','quantum_yield','detector_excitation','detector_emission'):
            bounded(name,getattr(self,name),0,1)

    def evaluate(self, excitation_irradiance, emission_band_irradiance=0.0):
        """One-sided diffuse sheet; two narrow bands, unresolved prompt lifetime.

        Nonabsorbed illumination is reflected diffusely. Absorbed excitation
        converts photons with quantum yield; the wavelength ratio converts
        photon yield to energy yield. Emission-band illumination does not excite.
        Detector values are declared dimensionless linear band sensitivities.
        """
        bounded("excitation_irradiance",excitation_irradiance,0,1e20)
        bounded("emission_band_irradiance",emission_band_irradiance,0,1e20)
        absorbed=self.absorption_fraction*excitation_irradiance
        emitted=absorbed*self.quantum_yield*self.excitation_nm/self.emission_nm
        direct_excitation=excitation_irradiance-absorbed
        direct=(self.detector_excitation*direct_excitation+self.detector_emission*emission_band_irradiance)/math.pi
        converted=self.detector_emission*emitted/math.pi
        return {'absorbed_power':absorbed,'converted_emission_power':emitted,
                'direct_excitation_power':direct_excitation,'direct_emission_band_power':emission_band_irradiance,
                'heat_power':absorbed-emitted,'direct_detector_radiance':direct,
                'converted_detector_radiance':converted,'detector_radiance':direct+converted}


@dataclass(frozen=True)
class Phosphor:
    lifetime_s: float = .4
    storage_yield: float = .6
    radiative_yield: float = .8

    def __post_init__(self):
        bounded('lifetime_s',self.lifetime_s,1e-4,1000)
        bounded('storage_yield',self.storage_yield,0,1)
        bounded('radiative_yield',self.radiative_yield,0,1)


class Population:
    """Optical state owner, independent of sensor and display lifecycles.

    U is stored excitation energy per area. dU/dt=storage_yield*Pabs-U/tau.
    The state models a metastable reservoir. Classification is an assumption
    about the reservoir, not a lifetime threshold separating two effects.
    """
    def __init__(self, parameters=Phosphor()):
        self.parameters=parameters
        self.reset_material()

    def reset_material(self, stored_energy=0.0):
        bounded('stored_energy',stored_energy,0,1e20)
        self.stored_energy=stored_energy

    @property
    def emitted_power(self):
        return self.parameters.radiative_yield*self.stored_energy/self.parameters.lifetime_s

    def advance(self, dt_s, absorbed_power):
        bounded('dt_s',dt_s,0,10000)
        bounded('absorbed_power',absorbed_power,0,1e20)
        p=self.parameters
        decay=math.exp(-dt_s/p.lifetime_s)
        uptake=-math.expm1(-dt_s/p.lifetime_s)
        previous=self.stored_energy
        self.stored_energy=previous*decay+p.storage_yield*absorbed_power*p.lifetime_s*uptake
        released=max(0.0,previous+p.storage_yield*absorbed_power*dt_s-self.stored_energy)
        return {'stored_energy':self.stored_energy,'emitted_power':self.emitted_power,
                'emitted_energy':p.radiative_yield*released,
                'heat_energy':(1-p.storage_yield)*absorbed_power*dt_s+(1-p.radiative_yield)*released}
