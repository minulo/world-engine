"""How much water the air can take up from a wet surface: the Priestley-Taylor rule.

Model: the form in which the SPLASH model states it [DOCUMENTED: Davis et al. 2017, Geoscientific
Model Development 10, 689, equations 10 to 13, 19, 20, 22, B1, B2 and B8]:

    demand = (1 + w) * s / (s + g) * Rn / Lv          kg of water per m² and second

    Rn   energy the surface gains from radiation: sunlight absorbed less the heat it radiates away
    s    how fast the pressure of water vapour in saturated air rises with temperature (Pa/K)
    g    the psychrometric constant (Pa/K): the same for dry air, set by the air pressure
    Lv   the heat needed to turn a kilogram of water into vapour
    w    0.26, which the paper calls the entrainment factor [INFERRED gloss: what the mixing of
         the air above adds to the evaporation that the energy alone would give]

The fraction s / (s + g) is the share of the available energy that goes into evaporating water
and not into warming the air; it grows with temperature, from 0.40 at freezing to 0.78 at
30 C at sea level [MEASURED: these formulas with these constants]. Every number of these
formulas is handed in from models.yaml.

The two parts of Rn follow the same paper. Of the sunlight at the top of the air, the share
(c + d * sunshine) * (1 + 2.67e-5 * height) reaches the ground, and the ground reflects 0.17
of it. The heat the surface radiates away, less what the air radiates back, is
(b + (1 - b) * sunshine) * (A - T), T in degrees C. "sunshine" is the share of the possible
hours of sunshine: the paper takes it from measurements of cloud.

Outside the ground the formulas were fitted to, each is held at a limit [INFERRED: the limits
are mine; the paper does not treat these cases]. Ground below sea level gets the sunlight of
sea level: the gain with height is not carried below zero. The air lets through no more
sunlight than arrives. A surface hotter than A loses nothing. The air pressure is held at a
set share of its base from the height at which the formula ends, about 44 km up; below sea
level it is carried on, since more air lies above such ground.

Ignores: wind and the dryness of the air, which the rule folds into the one number w. A
kilogram of water on a square metre is taken as one millimetre: the paper divides by the
density of water at the cell's temperature (its equation 19), which makes the demand larger
by about 0.4 % at 30 C [UNVERIFIED: from the density of water as I recall it, 995.7 kg/m3
at 30 C].
Wrong where: in dry air, where more water is taken than the rule gives [UNVERIFIED: recalled].
"""
import numpy as np

from .units import ZERO_CELSIUS_IN_K


def saturation_slope(t_c: np.ndarray, c: dict) -> np.ndarray:
    """Rise of the saturation vapour pressure with temperature, Pa/K (Davis et al. 2017, eq. B1)."""
    shifted = t_c + c["offset_c"]
    return c["factor_pa_c"] * np.exp(c["exponent"] * t_c / shifted) / (shifted * shifted)


def latent_heat(t_c: np.ndarray, c: dict) -> np.ndarray:
    """Heat of vaporisation of water, J/kg (Davis et al. 2017, eq. B2, after Henderson-Sellers 1984): the factor
    times the square of T / (T - offset), T in kelvin."""
    t_k = t_c + ZERO_CELSIUS_IN_K
    ratio = t_k / (t_k - c["offset_k"])
    return c["factor_j_kg"] * ratio * ratio


def air_pressure(height_m: np.ndarray, gravity: float, c: dict) -> np.ndarray:
    """Air pressure at a height above sea level, Pa: the barometric formula for air that cools steadily with height
    (Davis et al. 2017, eq. 20)."""
    base = np.maximum(1.0 - c["lapse_k_per_m"] * height_m / c["sea_level_temperature_k"], c["lowest_share"])
    return c["sea_level_pressure_pa"] * base ** (gravity * c["molar_mass_air_kg"] / (c["gas_constant_j_mol_k"] * c["lapse_k_per_m"]))


def psychrometric(pressure_pa: np.ndarray, heat_j_kg: np.ndarray, c: dict) -> np.ndarray:
    """The psychrometric constant, Pa/K (Davis et al. 2017, eq. B8)."""
    return c["specific_heat_air_j_kg_k"] * c["molar_mass_air_kg"] * pressure_pa / (c["molar_mass_water_kg"] * heat_j_kg)


def net_longwave(t_c: np.ndarray, sunshine: float, c: dict) -> np.ndarray:
    """Heat the surface loses as radiation, less what the air sends back, W/m² (Davis et al. 2017, eq. 13)."""
    return (c["b"] + (1.0 - c["b"]) * sunshine) * np.maximum(c["a_c"] - t_c, 0.0)


def absorbed_sunlight(top_of_air_w_m2: np.ndarray, height_m: np.ndarray, sunshine: float, reflects: float, c: dict) -> np.ndarray:
    """Sunlight a surface absorbs, W/m²: what the air lets through, more of it at height, less the share the
    surface reflects (Davis et al. 2017, eqs. 10 to 12)."""
    through = (c["through_overcast"] + c["through_gain_with_sunshine"] * sunshine) * (1.0 + c["through_gain_per_m"] * np.maximum(height_m, 0.0))
    return (1.0 - reflects) * np.minimum(through, 1.0) * top_of_air_w_m2


def priestley_taylor(net_radiation_w_m2: np.ndarray, t_c: np.ndarray, pressure_pa: np.ndarray, extra: float,
                     vapour: dict, heat: dict, air: dict) -> np.ndarray:
    """The demand of the air for water, in kg of water per m² and second, which is mm of water a second.
    Nothing where the surface loses more energy than it gains."""
    s = saturation_slope(t_c, vapour)
    lv = latent_heat(t_c, heat)
    g = psychrometric(pressure_pa, lv, air)
    return (1.0 + extra) * s / (s + g) * np.maximum(net_radiation_w_m2, 0.0) / lv
