"""The air's demand for water over Earth's land as the engine works it out, beside a published budget of the
land's energy and beside the form of the paper whose formulas it uses.

    python tools/earth_demand.py [--level 7] [--sea-water relief|planet]

Hydrology's demand is the Priestley-Taylor rule on the energy the ground gains from radiation. The two parts of
that energy come from the formulas of Davis et al. 2017 (the SPLASH model), which ask for a share of sunshine;
the engine has no clouds and gives every cell and month the same share (data/models.yaml, Hydrology, demand).

  1. The radiation at the ground over Earth's land, from those formulas under Earth's temperatures (CRU), beside
     the published budget of the land [DOCUMENTED: Trenberth, Fasullo and Kiehl 2009, Table 2b, the row of the land:
     a synthesis of measurements and models, not a measurement], and what the land's evaporation takes of it. The
     engine leaves the land more energy than the budget does; the lines under the table take that excess apart, and
     show what other shares of sunshine would give. The share enters both formulas, the sunlight that reaches the
     ground and the heat the ground radiates away, and no one share returns both of the budget's numbers. What the
     table cannot show is why: whether the share, the formulas' constants or the ground's reflection is at fault,
     and where on the land.
  2. The demand itself, in two forms. The engine takes the net radiation of the whole day: the day's gain less the
     night's loss. The paper takes the hours in which the ground gains energy (its equations 14, 24 and 25) and
     gives the night's loss back to the soil as condensation (its equations 16 and 18). To compare them the course
     of a day is laid under each month's mean sunlight: the sun's height through the day at mid-month for each
     latitude, scaled so that the day's mean is the engine's. The ground that lies under snow is left out of both,
     as Hydrology leaves it out.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402
from worldengine import console                          # noqa: E402
from worldengine.library import evaporation as ev        # noqa: E402
from worldengine.library import orbit                    # noqa: E402

# W/m2 over land, 2000 to 2004 [DOCUMENTED: Trenberth, Fasullo and Kiehl 2009, Table 2b, the row "This paper" under Land: net solar
# 145.1, solar reflected 39.6 (so 184.7 reach the ground), net longwave 79.6, evaporation 38.5, sensible heat 27; read out by a
# page reader on 2026-10-05]. These are a published synthesis of measurements and models, not measurements of one kind.
LAND_MEASURED = {"reaches": 184.7, "absorbed": 145.1, "lost": 79.6, "evaporation": 38.5, "sensible": 27.0}
DAY_S = 86400.0
OTHER_SHARE = 0.5           # a third share of sunshine for the table of shares, below the engine's


def measure(level=7, earth=None, sea_water=ref.SEA_WATER):
    """The numbers of the report, as a dict (see report). `earth` is an Earth built already."""
    e = earth if earth is not None else ref.Earth(level, sea_water=sea_water)
    h = e.hydrology()
    planet, c = e.h.params["planet"], e.h.params["models"]["slots"]["Hydrology"]["constants"]["demand"]
    months = e.rain.shape[0]
    area = e.area.astype(np.float64)
    celsius = e.celsius
    known = np.isfinite(celsius).all(axis=0)
    land = e.land & known
    height = np.where(e.wet, 0.0, e.mean - e.sea_level)
    top = e.h.run("Insolation", reads={"latitude": e.latitude}).fields["insolation"].astype(np.float64)
    s = c["sunshine_fraction"]
    absorbed = ev.absorbed_sunlight(top, height[None, :], s, c["sunlight"]["ground_reflects"], c["sunlight"])
    reaches = absorbed / (1.0 - c["sunlight"]["ground_reflects"])
    lost = ev.net_longwave(celsius, s, c["longwave"])
    over_land = lambda v: float((np.nanmean(v, axis=0) * area)[land].sum() / area[land].sum())
    budget = {"reaches": over_land(reaches), "absorbed": over_land(absorbed), "lost": over_land(lost)}
    # what the land's evaporation takes, as energy: every month's water times the heat that evaporating it takes
    given = h.fields["evapotranspiration"].astype(np.float64) * ev.latent_heat(celsius, c["heat"])       # J/m2 a month
    budget["evaporation"] = float((np.nansum(given, axis=0) * area)[land].sum() / area[land].sum() / planet["year_length_s"])
    # the excess of the energy left to the land, taken apart: each part is the change that setting one thing to the
    # budget's value would make, the others left at the budget's values, so that the three add up to the excess
    m = LAND_MEASURED
    reflects, measured_reflects = 1.0 - budget["absorbed"] / budget["reaches"], 1.0 - m["absorbed"] / m["reaches"]
    excess = {"sunlight": (budget["reaches"] - m["reaches"]) * (1.0 - measured_reflects),
              "reflection": budget["reaches"] * (measured_reflects - reflects), "heat_loss": m["lost"] - budget["lost"]}
    # the share of sunshine that would return each of the budget's numbers, the other things left as they are
    through = c["sunlight"]
    lift = 1.0 + through["through_gain_per_m"] * np.maximum(height, 0.0)
    wants_sun = (LAND_MEASURED["reaches"] / over_land(top * lift[None, :]) - through["through_overcast"]) / through["through_gain_with_sunshine"]
    b = c["longwave"]["b"]
    wants_heat = (LAND_MEASURED["lost"] / over_land(np.maximum(c["longwave"]["a_c"] - celsius, 0.0)) - b) / (1.0 - b)

    def with_share(share):
        """The three numbers of the budget with another share of sunshine, everywhere alike: the share enters both formulas."""
        took = ev.absorbed_sunlight(top, height[None, :], share, c["sunlight"]["ground_reflects"], c["sunlight"])
        gave = ev.net_longwave(celsius, share, c["longwave"])
        return {"reaches": over_land(took / (1.0 - c["sunlight"]["ground_reflects"])), "lost": over_land(gave), "left": over_land(took) - over_land(gave)}
    shares = {float(x): with_share(float(x)) for x in (OTHER_SHARE, s, wants_heat)}

    # the demand, the engine's form and the paper's
    pressure = ev.air_pressure(height, planet["surface_gravity_m_s2"], c["air"])
    slope = ev.saturation_slope(celsius, c["vapour"])
    heat = ev.latent_heat(celsius, c["heat"])
    per_joule = slope / (slope + ev.psychrometric(pressure[None, :], heat, c["air"])) / heat        # kg of water for each joule
    extra = c["priestley_taylor_extra"]
    o = planet["orbit"]
    middle = (np.arange(months) + 0.5) / months
    longitude, _ = orbit.solar_longitude(middle, o["eccentricity"], np.deg2rad(o["perihelion_solar_longitude_deg"]), o["northward_equinox_year_fraction"])
    declination = np.arcsin(np.sin(np.deg2rad(planet["axial_tilt_deg"])) * np.sin(longitude))[:, None]
    phi = np.deg2rad(e.mesh.lat)[None, :]
    ru, rv = np.sin(declination) * np.sin(phi), np.cos(declination) * np.cos(phi)
    sunset = np.arccos(np.clip(-ru / np.maximum(rv, orbit.GRAZING), -1.0, 1.0))                      # the hour angle of sunset
    shape = (ru * sunset + rv * np.sin(sunset)) / np.pi                                             # the day's mean of the sun's height
    rw = np.where(shape > 0.0, absorbed / np.where(shape > 0.0, shape, 1.0), 0.0)                    # so that the day's mean is the engine's
    with np.errstate(invalid="ignore", divide="ignore"):
        crossing = np.where(rw * rv > 0.0, (lost - rw * ru) / np.where(rw * rv > 0.0, rw * rv, 1.0), np.inf)
    gains_until = np.minimum(np.arccos(np.clip(crossing, -1.0, 1.0)), sunset)                       # the paper's h_n
    gain = np.maximum(DAY_S / np.pi * ((rw * ru - lost) * gains_until + rw * rv * np.sin(gains_until)), 0.0)       # J/m2 a day, the paper's H_N+
    whole = DAY_S * (absorbed - lost)
    loss = np.minimum(whole - gain, 0.0)                                                            # the rest of the day, the paper's H_N-
    days = planet["year_length_s"] / months / DAY_S
    free = np.nan_to_num(h.drivers["potential_evapotranspiration"]["snow_free"].astype(np.float64))
    engine = (1.0 + extra) * per_joule * np.maximum(whole, 0.0) * days * free                        # mm a month
    paper = (1.0 + extra) * per_joule * gain * days * free
    dew = per_joule * np.abs(loss) * days * free
    field = np.nan_to_num(h.fields["potential_evapotranspiration"].astype(np.float64))
    year = lambda v, mask: float((np.nansum(v, axis=0) * area)[mask].sum() / area[mask].sum())
    bands = {"all land": land, "60 south to 60 north": land & (np.abs(e.mesh.lat) < 60.0), "23 south to 23 north": land & (np.abs(e.mesh.lat) < 23.0),
             "30 to 60 north": land & (e.mesh.lat > 30.0) & (e.mesh.lat < 60.0), "60 to 90 north": land & (e.mesh.lat > 60.0)}
    return {"budget": budget, "excess": excess, "wants_sun": float(wants_sun), "wants_heat": float(wants_heat), "sunshine": s, "shares": shares,
            "land_with_temperature": float(area[land].sum() / area[e.land].sum()),
            "field": year(field, land), "largest_gap_to_the_field": float(np.abs(engine - field)[:, land].max()),
            "bands": {name: {"engine": year(engine, mask), "paper": year(paper, mask), "dew": year(dew, mask)} for name, mask in bands.items()},
            "none_where_the_paper_has_some": float(((engine == 0.0) & (paper > 1.0))[:, land].mean())}


def report(level=7, say=print, earth=None, sea_water=ref.SEA_WATER):
    r = measure(level, earth, sea_water)
    say(f"Earth's land on the mesh ({100 * r['land_with_temperature']:.1f} % of it has temperatures in the data), with one share of sunshine, {r['sunshine']:g}, everywhere")
    say("\n1. Radiation at the ground over land, W/m2 on the year's mean")
    b, m = r["budget"], LAND_MEASURED
    say(f"{'':34s}{'the engine':>12s}{'the budget':>12s}")
    for key, words in (("reaches", "sunlight that reaches the ground"), ("absorbed", "sunlight that the ground absorbs"), ("lost", "heat that the ground radiates away")):
        say(f"{words:34s}{b[key]:12.1f}{m[key]:12.1f}")
    say(f"{'left to warm the air and evaporate':34s}{b['absorbed'] - b['lost']:12.1f}{m['absorbed'] - m['lost']:12.1f}   the engine has "
        f"{(b['absorbed'] - b['lost']) / (m['absorbed'] - m['lost']):.2f} of the budget's")
    say(f"{'of that, evaporation takes':34s}{b['evaporation']:12.1f}{m['evaporation']:12.1f}   the engine has "
        f"{b['evaporation'] / m['evaporation']:.2f} of the budget's")
    x = r["excess"]
    say(f"the excess of {(b['absorbed'] - b['lost']) - (m['absorbed'] - m['lost']):.1f} W/m2 taken apart: {x['sunlight']:.1f} from the sunlight that reaches "
        f"the ground; {x['reflection']:.1f} from the ground reflecting {1 - b['absorbed'] / b['reaches']:.2f} of it where the budget has "
        f"{1 - m['absorbed'] / m['reaches']:.2f}; {x['heat_loss']:.1f} from the heat that the ground radiates away")
    say(f"the share of sunshine that would return the budget's sunlight at the ground: {r['wants_sun']:.2f}; the budget's loss of heat: {r['wants_heat']:.2f}")
    say("the share of sunshine enters both formulas. With another share, everywhere alike:")
    say(f"{'':6s}{'share':>7s}{'sunlight at the ground':>24s}{'heat radiated away':>20s}{'left':>8s}")
    for share, v in sorted(r["shares"].items()):
        say(f"{'':6s}{share:7.2f}{v['reaches']:24.1f}{v['lost']:20.1f}{v['left']:8.1f}" + ("   as built" if share == r["sunshine"] else ""))
    say(f"{'':6s}{'budget':>7s}{m['reaches']:24.1f}{m['lost']:20.1f}{m['absorbed'] - m['lost']:8.1f}")
    say("(the budget is a published synthesis for 2000 to 2004, not a measurement; the engine's side uses Earth's temperatures of 1961 to 1990\n"
        " from a grid of 5 degrees, and the evaporation is Hydrology's under the rain data. What the comparison cannot show: where on the land\n"
        " the energy is too much, since the budget is one number for all land; and why.)")

    say("\n2. The demand for water over land, mm a year, on the ground that is free of snow")
    say(f"the field potential_evapotranspiration: {r['field']:.0f}; worked out again here from the same numbers: within {r['largest_gap_to_the_field']:.1e} mm a month in every cell")
    say(f"{'':24s}{'the engine':>11s}{'the paper':>11s}{'the night gives back':>22s}{'the paper, net':>16s}{'net / engine':>14s}")
    for name, x in r["bands"].items():
        say(f"{name:24s}{x['engine']:11.0f}{x['paper']:11.0f}{x['dew']:22.0f}{x['paper'] - x['dew']:16.0f}{(x['paper'] - x['dew']) / x['engine']:14.2f}")
    a = r["bands"]["all land"]
    say(f"the engine: the whole day's net radiation. The paper: the hours of gain alone ({a['paper'] / a['engine']:.2f} of the engine's over all land), "
        f"with the night's loss given back to the soil as condensation")
    say(f"in {100 * r['none_where_the_paper_has_some']:.1f} % of the land's cells and months the engine's demand is nothing where the paper's form gives more than 1 mm")
    return r


def parser():
    p = console.tool_parser(__doc__, "python tools/earth_demand.py")
    p.add_argument("--level", type=console.whole_number(3, 8), default=7, metavar="LEVEL")
    p.add_argument("--sea-water", choices=("relief", "planet"), default=ref.SEA_WATER)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not ref.available():
        print("the Earth reference data is not here: run python tools/fetch_reference_data.py", file=sys.stderr)
        return 1
    report(args.level, sea_water=args.sea_water)
    return 0


if __name__ == "__main__":
    sys.exit(main())
