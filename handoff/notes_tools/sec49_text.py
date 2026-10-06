"""Section 4.9 of docs/BUILD_NOTES.md: the diagnosis of the weak seasons, typed by hand from the logs of
handoff/pass3/ (seasons_apart.log, eb_alone.log, eb_varying.log, seasons_sea.log, sea_capacity.log)."""

SEC49 = """### 4.9 Why the summers of northern land are cold: a diagnosis

You left the four questions of section 11 to me on 2026-10-06. I took the first as the next piece of work
and began by telling the candidate causes apart, before changing anything. Nothing in the engine was
changed: every row below is the preview Earth twin, or EnergyBalance by itself, built again with one or two
constants altered for the measurement. [MEASURED: the scripts and logs of `handoff/pass3/`; no test holds
these numbers]

**The whole engine on Earth's relief** (preview mesh), land between 40° and 60° north:

| | Coldest month | Warmest month | July less January | Open sea nearby, July less January | Land there white all year | Cold climates with warm summers (group D), share of all land | Rain |
|---|---|---|---|---|---|---|---|
| Earth | −12.7 °C | 18.4 °C | 31.1 K | 10.2 K | | 24.6 % | 654 mm |
| As built | −12.6 °C | 1.4 °C | 13.4 K | 2.7 K | 52 % | 2.1 % | 440 mm |
| No snow counted on the ground | −7.3 °C | 9.1 °C | 16.5 K | | 0 % | 8.6 % | |
| Land warms 4 times faster | −12.8 °C | 2.2 °C | 15.0 K | | 44 % | 3.3 % | |
| Spreading constant 0.35 for 0.649 | −24.1 °C | −8.1 °C | 16.0 K | | 94 % | 2.2 % | |
| Sea warms 2 times faster | −14.6 °C | 4.5 °C | 17.2 K | 5.8 K | 31 % | 6.3 % | 475 mm |
| Sea warms 3 times faster | −16.3 °C | 7.1 °C | 20.5 K | 9.2 K | 14 % | 11.1 % | 507 mm |
| Sea 3 times faster, and no snow counted | −11.5 °C | 13.2 °C | 23.7 K | 10.5 K | 0 % | 19.9 % | 779 mm |

("Sea nearby" is every sea cell of the band, coasts included. "No snow counted" sets the store at which
ground counts as covered so high that Albedo sees no snow on land; sea ice stays.)

**EnergyBalance by itself**, on Earth's land and sea, flat ground, one albedo everywhere, July less January
between 40° and 60° north:

| | Land | Sea |
|---|---|---|
| Earth (with its heights and its snow) | 31.3 K | 10.7 K |
| The engine's constants | 18.4 K | 3.8 K |
| Spreading that varies with latitude and surface, as published | 21.1 K | 3.8 K |
| The engine's spreading, a sea that warms 3 times faster | 27.8 K | 12.6 K |
| Both | 34.5 K | 13.9 K |

The spreading of the second row is that of Ziegler and Rehfeld 2021, equation 2 and Table 1. [DOCUMENTED:
read out by a page reader on 2026-10-06; solved outside the engine by `handoff/pass3/eb_varying.py`]

What this shows.

1. **Two causes are told apart, and both act.** Snow that never melts takes 7.7 K off the warmest month
   (1.4 °C with it, 9.1 °C without) and also 5.3 K off the coldest. Without the snow the winter would be 5 K
   too warm: the two errors cancel in winter and add in summer. That is why the twin's winter looked right,
   and why the fifth check's argument against "land tied to the sea" did not hold either.
2. **The larger cause is the sea.** The engine's sea hardly has seasons: 2.7 K between July and January
   where the data have 10.2 K, and the land is tied to it by the spreading. With a sea that warms three
   times faster the land's swing goes from 13.4 to 20.5 K and a quarter of the land that was white all year
   thaws.
3. **The land's own heat capacity and the published varying spreading do little:** 1.6 K and 2.7 K.
4. **No single constant mends it.** Over open sea, more than 600 km from land, the published capacity gives
   less than half of the measured swing in the north and the right swing in the far south:

| Swing of open sea, warmest month less coldest | 20° to 40° N | 40° to 60° N | 20° to 40° S | 40° to 60° S |
|---|---|---|---|---|
| Earth | 7.0 K | 9.6 K | 5.4 K | 4.3 K |
| As built (a mixed layer of 75 m) | 3.0 K | 4.4 K | 3.6 K | 4.5 K |
| Sea 2 times faster | 6.2 K | 9.3 K | 7.2 K | 9.4 K |
| Sea 3 times faster | 9.2 K | 14.0 K | 10.6 K | 14.1 K |

   Halving the capacity returns the northern seas and doubles the swing of the southern ones. Earth's
   northern seas swing about twice as far as its southern seas at the same latitude, and one depth of
   mixed layer cannot give both. [MEASURED for the table. INFERRED: that the difference is a matter of the
   depth to which the sea is stirred; nothing here measures that depth]
5. **Even with a faster sea and no snow the land reaches 23.7 K of Earth's 31.1 K**, and it is then too wet
   (779 mm for 654). What the rest is made of was not measured.

**What I decided, and why.** I changed no constant. Setting the sea's capacity to half would be a fit to the
northern seas that makes the southern seas wrong by as much, and setting it by hemisphere would place an
outcome, which the brief forbids. The cause that would give the difference, how deep wind and cooling stir
the sea, belongs to the ocean of a later build step, and
that is where the mend should be made and then judged by the four expected failures of the twin. Until
then the cold summers stay the largest known error, now with their causes measured. The limits of the
diagnosis: one relief (Earth's), the preview mesh, one constant changed at a time or two, a measure of the
sea taken from temperature data on a grid of 5° that blend land and sea near coasts, and no independent
check of these runs.
"""
