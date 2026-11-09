## Weather causes: why the weather of a day is as it is (build step 8, departure 3)

Section 18.4 listed as departure 3: "Weather keeps no cause records. The design says 'weather causes when a day is
recomputed on request'; that is not built, and the viewer says so for a day's field." It is built now. The numbers
below were measured on the default world (preview mesh, seed 20261004, world fingerprint 2c1ec14dd7744f7d), unless a
line says otherwise. The world is the same as before: built with this change and with the unfinished commit it
finishes, it has the same fingerprint [MEASURED], and no code of the climate was changed.

### What was built

- **The records.** When a day is worked out for a "why" answer (`Engine.day_view(store, day)`), the weather stage runs
  with `ctx.recording` on, as the climate's cause pass does, and its two processes record their drivers:
  - `storm_influence` (SynopticStorms): the part that mid-latitude storms give, the part that tropical cyclones give
    and what the cap on overlapping storms takes, which add up to the influence; the cell where each kind's strongest
    storm there was born; the row of the table of storms of the strongest storm; and whether any storm reaches the
    cell. A storm is said to reach a cell within twice its radius, where its influence has fallen to e^-4, about 2 %, of
    its strength [a wording of the answers, not a part of the model]; a cyclone that has lost all its strength reaches
    none.
  - `weather_temperature`, `weather_pressure`, `weather_wind` (DailyWeather), each a sum: the monthly means around the
    date, and the day's own part (for the temperature its departure, with the remembered noise of the date and the
    spread it is scaled by; for the pressure the day's own warmth and the storms passing today; for the wind the day's
    gust, taken along the day's wind).
  - `weather_precipitation`: whether the day is wet, dry or in a month without rain; the chance of rain, its two
    sources (the month's share of wet days and the chance that the storms passing today bring rain) and which of them
    is the larger; the draw of the date, the mean rain of a day around the date and the amount drawn.

  The records change nothing a day holds, and `Engine.day_weather` keeps none: the record of one day never stands
  beside another.
- **The answers.** `store.DayView` holds the day beside the stored world: the day's fields, its table of storms, its
  drivers and its lineage; everything else is read from the world, which is not changed. `explain()` reads it as it
  reads a stored world, gives the sentences the slot `{day}`, and the heading names the day. The five fields have
  sentence patterns in `data/explanations.yaml`. A new key of a sum's driver, `follow_first`, names the day's own part
  and follows it first, however small it is beside the month's mean: a departure of 0.5 K is 0.18 % of 285 K, and a
  sum leaves unsaid any part below 0.2 % of its largest (`causes.WORTH_SAYING`). The month's part is always named. The walk goes from the
  day's own part to the seed, where the remembered noise of the date ends, and on into the climate the day read: the
  spread of WeatherStatistics and the month's temperature, the storm map at the cell where the strongest storm was
  born, the share of wet days and the month's rain. A day's rain goes first to the larger of the two sources of its
  chance.
- **A world stored before.** Every world built before this change stored no weather patterns. Such a world is answered
  with the patterns of this copy of the engine, each only where every driver it names is one its process records, and
  the answer says so in a notice.
- **Where to ask.** `python -m worldengine explain STORE --lat --lon --field <weather field> --day N` (with
  `--json` too); the server's `/api/explain?cell=&field=&day=`; and the viewer's why panel for a day's field, which
  asks for the day shown and drops an answer that comes back after a later one was asked for. The server works a day
  out once, with its causes, for its values (`/api/weather`) and its answers alike, and keeps the last two days. A
  field of a day asked without a day, a field that is not of a day asked with one, and a day before day 0 are refused
  by all three, in words that say what to ask instead.
- **The scan.** `python tools/why_scan.py STORE --day N` reads the answers of that day too. Its rules for the weather:
  every entry about a field of the day names that day; a day with rain is called wet and one without dry, or in a month
  without rain, as its record says; the amount, temperature, pressure and wind given are the day's; the parts of a sum
  add up to the value given, and the day's own part is named wherever it is not nothing; the chance of rain is the one
  its two sources make, and the draw lies below it on a wet day and not on a dry one; a cell no storm reaches is said
  to be reached by none, and the strongest storm named is the one of the row given, with its kind, birth day and
  strength.
- **The tests' world.** `tests/test_days.py` runs the real SynopticStorms and DailyWeather around a climate planted by
  hand (`toy_processes.PlantedClimate`) on mesh level 4, so that a world builds in under a second and a day takes about
  0.2 s [MEASURED]: wet days, dry days and a desert where no rain falls in any month, a storm track and a cradle of
  tropical cyclones.
- **Two small faults fixed on the way.** The answer for `wet_day_fraction` printed "0.47 0 to 1 of the days are wet"; it
  prints a share ("47 % of the days"). The server cut the closing quote off a refusal whose words end in one ("got
  'soon"); it now strips quotes only from the text of a missing key, which Python quotes.

### Conditions

| Condition | Result |
|---|---|
| A day's answer is the same however the day was reached | Bit for bit, the answers of 27 cells for the five fields (`tests/test_days.py`): asked alone of a fresh engine; of an engine made from the data instead of the store; and after days 199 (with causes), 201 (without) and 40 had been worked out. In the server, the same bytes after days 199, 41 and 7 had been asked for, and in a second server (`tests/test_store_server.py`). Another day gives other answers |
| A day worked out with its causes holds what it holds without them | Bit for bit, every field and every column of the table of storms, on days 40, 200 and 275 |
| Drivers add up to the value where a field is additive | `storm_influence`, `weather_temperature`, `weather_pressure` and `weather_wind`, within 2e-5 of the field's largest value: on three days of the tests' world, and on day 200 of the default world (`tests/test_world.py`, the test of every additive field, which now counts three asides: the two numbers of a day's temperature beside runoff's) |
| The rain's record holds its rule | Wet exactly where rain falls; the draw at most the chance on a wet day and at least it on a dry one (in 32 bits); the chance 1 − (1 − share)(1 − storms' chance) within 1e-6; a wet day's rain the day's mean over the chance times the amount drawn, within 1e-5 |
| The walk reaches the climate fields the day read | The temperature reaches the seed of the remembered noise, the spread and the month's temperature; a wet day the storms made likely goes on to the storm; the storm goes back to the storm map at the cell its strongest one was born in, for a mid-latitude storm and for a tropical cyclone |
| No answer of a day says what its numbers contradict | Default world, `tools/why_scan.py --every 7 --day 200`: 39,528 answers read (32,208 of the climate, 7,320 of the day), none contradicted [MEASURED]. Every cell of the five fields of the day on days 200 and 20: 51,210 answers each, none contradicted, in about 104 s a day [MEASURED]. In `tests/test_world.py`, every ninth cell on days 20 and 200 |
| The scan finds what it is built to find | 8 faults planted in true answers of a day (`tests/test_days.py`), one for each of eight of its rules: each reported, and nothing else |

A test that broke would show: each of these mutations, made one at a time, failed at least one of the new tests
[MEASURED]: the walk no longer naming a small day's own part; `day_view` working the day out without records;
`day_weather` keeping the record of an earlier day; the pattern of the storms losing the cell of the birth; the
departure recorded without its noise; the slot `{day}` left out; the server answering a day's field from the stored
world.

### Departures and limits

1. The climate's answers are those of the year. The walk goes from "the monthly means around this date give 7.5 °C" on
   to the stored field's own answer, which averages the months ("The temperature here averages 6.1 °C over the year",
   at 50° N, 9° E on day 180) [MEASURED]. A walk that stayed in the month of the day would need the climate's
   patterns to speak of a month.
2. Nothing of a day is stored. Each answer works the day out again: 0.09 to 0.11 s a day on the preview mesh, with
   records or without (the difference lies within what one run differs from the next), 1.8 ms an answer, and 0.7 s to
   make the engine from the store plus 0.6 s for its first day [MEASURED, the default world, alone on the machine but
   for one scan].
3. An answer holds at most 16 entries, as every answer does. A wet day the storms made likely spends most of them on
   the storm and the place it was born, and the share of wet days and the month's rain then need a question of their
   own.
4. Which source of the chance of rain is the larger, and where a storm "reaches", are words for the answers; the
   model uses neither.
5. The patterns a world stored before this change borrows are read from the engine's data folder when the answer is
   asked; a world built now keeps its own.
6. The viewer's panel was not run in a browser: the build machine has no Playwright. Its code was run under Node with
   stand-ins for the page and the server: it asks `/api/explain?cell=3&field=weather_precipitation&day=200`, writes
   "Why is weather precipitation like this here on day 201?" for the later day, drops the earlier answer that came
   back last, and asks a stored field without a day [MEASURED].
7. The days of a run that steps through dates (`Engine.run_dated`) still run without records: nothing asks why there.

What remains of departure 3: nothing of what the design names. The walk into the month of the day (item 1) and a
browser check of the panel (item 6) are not done.
