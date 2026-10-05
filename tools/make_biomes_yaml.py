"""Write data/biomes.yaml from the digitised Whittaker chart of the R package plotbiomes.

A development tool, run once; the result is checked in. It needs a clone of
https://github.com/valentinitnelav/plotbiomes (MIT licence, copyright 2017 Valentin Stefan) and the
Python package rdata. The chart is Figure 5.5 of Ricklefs 2008, The Economy of Nature, as that
package digitised it: the corners of each biome's outline in mean yearly temperature (degrees C)
and yearly precipitation (cm).
    python tools/make_biomes_yaml.py PATH_TO_plotbiomes
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine import console                          # noqa: E402

NAMES = {"Tundra": "tundra", "Boreal forest": "boreal_forest", "Temperate seasonal forest": "temperate_seasonal_forest",
         "Temperate rain forest": "temperate_rainforest", "Tropical rain forest": "tropical_rainforest",
         "Tropical seasonal forest/savanna": "tropical_seasonal_forest_savanna", "Subtropical desert": "subtropical_desert",
         "Temperate grassland/desert": "temperate_grassland_desert", "Woodland/shrubland": "woodland_shrubland"}
# display colours of the chart, and the share of ground shaded by plants used until the full Biomes model (build step 7)
LOOK = {"tundra": ("#C1E1DD", 0.3), "boreal_forest": ("#A5C790", 0.8), "temperate_seasonal_forest": ("#97B669", 0.85),
        "temperate_rainforest": ("#75A95E", 0.95), "tropical_rainforest": ("#317A22", 0.95),
        "tropical_seasonal_forest_savanna": ("#A09700", 0.7), "subtropical_desert": ("#DCBB50", 0.1),
        "temperate_grassland_desert": ("#FCD57A", 0.4), "woodland_shrubland": ("#D16E3F", 0.5)}
KOPPEN = [("Af", "#0000FF"), ("Am", "#0078FF"), ("Aw", "#46AAFA"), ("BWh", "#FF0000"), ("BWk", "#FF9696"), ("BSh", "#F5A500"),
          ("BSk", "#FFDC64"), ("Csa", "#FFFF00"), ("Csb", "#C8C800"), ("Csc", "#969600"), ("Cwa", "#96FF96"), ("Cwb", "#64C864"),
          ("Cwc", "#329632"), ("Cfa", "#C8FF50"), ("Cfb", "#64FF50"), ("Cfc", "#32C800"), ("Dsa", "#FF00FF"), ("Dsb", "#C800C8"),
          ("Dsc", "#963296"), ("Dsd", "#966496"), ("Dwa", "#AAAFFF"), ("Dwb", "#5A78DC"), ("Dwc", "#4B50B4"), ("Dwd", "#320087"),
          ("Dfa", "#00FFFF"), ("Dfb", "#37C8FF"), ("Dfc", "#007D7D"), ("Dfd", "#00465F"), ("ET", "#B2B2B2"), ("EF", "#666666")]


def write(repo):
    import rdata                                             # needed for this one step only: --help works without it
    warnings.simplefilter("ignore")
    df = rdata.read_rda(str(Path(repo) / "data" / "Whittaker_biomes.rda"))["Whittaker_biomes"]
    out = ["# Category lists and rule tables for Biomes (design, Layer 1 and Layer 5).",
           "#",
           "# biomes: Whittaker's chart of mean yearly temperature against yearly precipitation, as digitised from",
           "#   Figure 5.5 of Ricklefs 2008, The Economy of Nature, by the R package plotbiomes",
           "#   (https://github.com/valentinitnelav/plotbiomes, MIT licence, copyright 2017 Valentin Stefan).",
           "#   Each outline is a list of corners [degrees C, cm per year]. Written by tools/make_biomes_yaml.py.",
           "#   ocean and ice are not on the chart: the engine sets them (sea cells; warmest month below freezing).",
           "#   color is for display only. cover is the share of ground shaded by plants: a first value of my own,",
           "#   [INFERRED], used until the full Biomes model of build step 7.",
           "# climate_classes: the Köppen-Geiger classes, with the display colours of the published maps as I recall",
           "#   them [UNVERIFIED; display only]. The rules are in models.yaml under Biomes.",
           "biomes:",
           "  - {name: ocean, color: \"#1B4A8A\", cover: 0.0}",
           "  - {name: ice, color: \"#F4F7FA\", cover: 0.0}"]
    for biome_id in sorted(df["biome_id"].unique()):
        rows = df[df["biome_id"] == biome_id]
        name = NAMES[str(rows["biome"].iloc[0])]
        color, cover = LOOK[name]
        pts = ", ".join(f"[{t:.2f}, {p:.2f}]" for t, p in zip(rows["temp_c"], rows["precp_cm"]))
        out.append(f"  - name: {name}\n    color: \"{color}\"\n    cover: {cover}\n    outline: [{pts}]")
    out.append("climate_classes:")
    out.append("  - {name: ocean, color: \"#1B4A8A\"}")
    for name, color in KOPPEN:
        out.append(f"  - {{name: {name}, color: \"{color}\"}}")
    Path(__file__).resolve().parents[1].joinpath("data", "biomes.yaml").write_text("\n".join(out) + "\n", encoding="utf-8")


def parser():
    p = console.tool_parser(__doc__, "python tools/make_biomes_yaml.py")
    p.add_argument("repo", metavar="PATH_TO_plotbiomes")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not (Path(args.repo) / "data" / "Whittaker_biomes.rda").exists():
        print(f"{args.repo} holds no data/Whittaker_biomes.rda: it is not a clone of plotbiomes", file=sys.stderr)
        return 2
    write(args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
