"""The table of section 4.5 from six logs of tools/earth_rivers.py --valley-share X --settlements 20.
python share_table.py FOLDER  prints it; share_table(folder) returns it."""
import re
import sys
from pathlib import Path

SHARES = ["0.02", "0.05", "0.1", "0.2", "0.3", "0.5"]


def share_table(folder):
    rows = {}

    def put(name, share, value):
        rows.setdefault(name, {})[share] = value
    for x in SHARES:
        t = (Path(folder) / f"share_{x}.log").read_text()
        m = re.search(r"River mouths within 300 km, of 24: engine (\d+); mean heights (\d+); at random (\d+) to (\d+)", t)
        put("River mouths within 300 km, of 24, as the engine settles ties", x, m[1])
        put("… in 20 random settlements", x, f"{m[3]} to {m[4]}" if m[3] != m[4] else m[3])
        part = t[t.index("River mouths within 300 km, of 24"):t.index("Gauges within a factor of two, of 21")]
        m = re.search(r"in all 20: (\d+) rivers; in none: (\d+); in some: (\d+)", part)
        put("… rivers that pass in all 20, in none, in some", x, f"{m[1]}, {m[2]}, {m[3]}")
        for river in ("Nile", "Congo"):
            m = re.search(rf"^{river}\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) of 20", part, re.M)
            put(f"… the {river}'s mouth passes in, of 20", x, m[5])
        m = re.search(r"Gauges within a factor of two, of 21: engine (\d+); mean heights (\d+); at random (\d+) to (\d+)", t)
        put("Gauges within a factor of two, of 21, as the engine settles ties", x, m[1])
        put("… in 20 random settlements ", x, f"{m[3]} to {m[4]}" if m[3] != m[4] else m[3])
        part = t[t.index("Gauges within a factor of two, of 21"):t.index("Like for like, all like basins together")]
        m = re.search(r"in all 20: (\d+) rivers; in none: (\d+); in some: (\d+)", part)
        put("… rivers that pass in all 20, in none, in some ", x, f"{m[1]}, {m[2]}, {m[3]}")
        m = re.search(r"The lake at the Caspian's place: engine: (.*?); mean heights: (.*?); at random: closed in (\d+) of 20, "
                      r"(?:overflow up to ([\d.]+) km3 a year, )?([\d.]+) to ([\d.]+) million km2 at (-?\d+) to (-?\d+) m", t)
        put("The lake at the Caspian's place, as the engine settles ties", x, "closed" if m[1].startswith("closed") else "overflows")
        put("… closed in, of 20 random settlements", x, m[3])
        put("… its level", x, f"{m[7]} to {m[8]} m" if m[7] != m[8] else f"{m[7]} m")
        put("… its area, million km²", x, f"{m[5]} to {m[6]}")
        m = re.search(r"Like for like, all like basins together, the engine sheds of the measured depth: engine ([\d.]+); mean heights ([\d.]+); "
                      r"at random ([\d.]+) to ([\d.]+)", t)
        put("Like for like, engine over measured, as the engine settles ties", x, m[1])
        put("… in 20 random settlements  ", x, f"{m[3]} to {m[4]}")
        m = re.search(r"Land under lakes, %: engine ([\d.]+); mean heights ([\d.]+); at random ([\d.]+) to ([\d.]+)", t)
        put("Land under lakes, as the engine settles ties", x, f"{float(m[1]):.1f} %")
        m = re.search(r"Of the rain on land, back to the air: engine ([\d.]+)", t)
        put("Rain on land that goes back to the air", x, f"{float(m[1]):.3f}")
        m = re.search(r"Rivers reaching the sea, thousand km3 a year: engine ([\d.]+)", t)
        put("Rivers reaching the sea, thousand km³ a year", x, f"{float(m[1]):.1f}")
    out = ["| Share of a cell's land points below the height used | " + " | ".join(f"**{x}**" if x == "0.1" else x for x in SHARES) + " |",
           "|---" * (len(SHARES) + 1) + "|"]
    for name, by in rows.items():
        out.append(f"| {name.strip()} | " + " | ".join((f"**{by[x]}**" if x == "0.1" else by[x]) for x in SHARES) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    print(share_table(sys.argv[1]))
