## Stages that step by a month or a year (the dated clock, after section 18.4)

Section 18.4, departure 4, said: "A stage that steps by a month or a year is ordered and checked, but running one is
refused: only a daily step is built." This work builds the two longer steps. `Engine.run_dated` now steps stages of a
day, a month and a year side by side, the run store records the step each stage reached, and a run continued from a
run store equals one long run, bit for bit. The default data list no stage on the dated clock, so no world changes;
everything below was tried on toy stages (`tests/test_days.py`) and timed with a probe stage on the preview world.

### What was built

- **The calendar** (`library/days.py`: `step_of`, `first_day_of_step`, `days_in_step`). A day d lies in year
  floor(d / D), where D is the planet's year in days (`year_length_s` over 86,400 s), and in month
  floor((d mod D) / (D / months)) of that year. That is the same expression by which `month_weights` mixes two
  months for the weather of a day, so a day belongs to the month the weather of that day takes more of, and the two
  agree about the month a day lies in [MEASURED on days 0 to 1095, `tests/test_days.py`]. A month is numbered over the years from 0, the first month of year 0
  (month 12 is the first month of year 1); its month of the year is the number modulo the months of the year. On the
  default planet (D = 365.256 days) a month holds 30 or 31 whole days and a year 365 or 366: years 0 to 4 begin on
  days 0, 366, 731, 1096 and 1462, the months of year 0 hold 31, 30, 31, 30, 31, 30, 31, 30, 30, 31, 30, 31 days and
  those of year 1 30, 31, 30, 31, 30, 30, 31, 30, 31, 30, 31, 30 [MEASURED]. Over the first million days the month
  number never fell and never skipped a month, the guard that keeps a day's month below the last never acted, and the
  month always equalled floor(d / (D / months)); of the 32,853 whole months 14,391 held 31 days and 18,462 held 30, of
  the 2,737 whole years 702 held 366 days and 2,035 held 365 [MEASURED].
- **How the steps interleave** (`Engine.run_dated`, whose description states the rule). On each day of a run the
  weather of the day is worked out first, and then every stage on the dated clock whose step begins on that day makes
  its step, in the order of `stages.yaml`. A daily stage steps every day, a monthly stage on the first day of each
  month, a yearly stage on the first day of each year. On a day on which two stages step, the one listed first steps
  first. So a monthly stage listed before a daily one makes its step on the first day of a month before the daily step
  of that day: it reads the daily stage as it stood at the end of the month before (a read from the previous step;
  the scheduler already refuses a plain read of a later stage), and the daily stage reads the month's new value on
  every day of the month. Listed after it, the monthly stage reads the daily stage as it stands at the end of the
  month's first day. A run that stops inside a month has made that month's step; its continuation makes the next on
  the first day of the next month.
- **What a step is handed.** `ctx.round` is the number of the step: the day, the month counted over the years, or the
  year. The draws of a step are keyed by that number, as a geological round's are by its round. `ctx.step_length` is
  the number of whole days the step holds (1 for a daily stage; it was nothing on the dated clock before). The test
  harness (`worldengine.testing.Harness`) hands a process of a dated stage the same length for the step it is told to
  run.
- **The run store** (`store.save_run`, `read_run`) now records the calendar (the year in days and the months of a year)
  and, for each stage, its step and the number of the step it reached. A continuation steps each stage from the step
  after the one recorded. Beside the fields and the copies read from the previous step it now keeps the stages' tables
  and the copies of them read from the previous step, their members of groups as they stand and as read from the
  previous step, and the causes of each stage's last step. Before, only fields, copies and causes were kept, and the
  causes only of the run's last day. A stage that makes no step in a continued run keeps the causes it had. They
  are needed because a monthly stage's output stands for a whole month: with the members of groups left out of the
  store, a daily stage that reads a monthly stage's member got nothing from it after a continuation until the next
  month began, and the continued run differed from the long one [MEASURED: the test, with the members left out].
- **The weather is worked out only where a stage steps by a day**: the scheduler refuses a monthly or yearly stage
  that reads the weather, so without a daily stage no day's weather is used (the probe under "Measured").
- **Refusals.** The refusal of a month or a year is gone (section 18.2 counts it among the refusals of a run, as "a
  step that is not a day", and 18.4 names it as departure 4), and its test
  (`test_a_stage_that_steps_by_a_month_runs_once_a_month`) now runs one. Four are new, each held by a test of
  `tests/test_days.py`:
  1. a run that starts on a day inside a step of one of its stages ("a run starts on the first day of a step of each
     of its stages, but day 100 lies inside a month of stage flock, which began on day 92; the next begins on day
     122"): the monthly stage's value would otherwise be missing for the rest of the month;
  2. a continuation whose stages on the dated clock, or their steps, differ from the run store's: the world's
     fingerprint does not change when a stage of the dated clock changes its step, so the world check alone let it
     through;
  3. a continuation on another calendar (another year length or number of months);
  4. on loading, a stage that steps by a month or a year on a planet whose month or year is shorter than a day: some
     months would hold no day and a step would be skipped.
  The first and last day of a run are now checked as the day of `day_weather` is ("a day is a whole number from 0").
- **The command line** has no command that runs the dated clock (`weather` computes days through `day_weather`), so
  it needed no change.

### Conditions

| Condition | Result |
|---|---|
| A continued run equals one long run, bit for bit | Passes: days 0 to 800 in one run, and in four joined at day 173 (inside month 5, which began on day 153), 400 (inside month 13) and 730 (the last day of year 1), with a yearly, a monthly and a daily stage in either order; every field, copy, table column, member of a group and cause the same, and the steps reached the same (day 800, month 26, year 2) [MEASURED, `tests/test_days.py`] |
| The monthly stage steps on the first day of each month, as the weather counts months | Passes: to day 1095 it makes 36 steps of 30 or 31 days, every day of each is one whose weather takes more of that month than of any other, months 12 and 24 begin on days 366 and 731, and the yearly stage has stepped through 1,096 days, the first whole day of year 3 [MEASURED] |
| The steps interleave as stated | Passes: listed before the daily barrel, the monthly flock steps on day 153 and finds the barrel of day 152, and the barrel of day 153 loses what the flock of month 5 added to the group; listed after, it finds the barrel of day 153 |
| A run that makes no step of a stage keeps its state and its causes | Passes: days 174 to 180, inside month 5; the causes kept are those of the step of day 153 and sum to the flock |
| Every refusal held by a test (`tools/refusal_audit.py`) | Passes: 269 of 269 held, with every test file but `tests/test_world.py` [MEASURED, 2026-11-09]. The two runs before found six reached by no test, none of them new: `no run store at` in `store.py`, three refusals of a day's weather in `server.py`, and the two of `server.check`, which only the launcher's own process reached, where the audit does not look. Each now has a test (`tests/test_days.py`, `tests/test_store_server.py`) |
| The new tests fail when what they test is broken | Each of 14 changes to the code (the members of groups, the copies of tables, the copies of groups or the causes not carried; the steps reached ignored; the stages run in reverse order; the causes recorded on the run's last day only; a step one day long; months counted from the ceiling; fields read back as float32; a run allowed to start inside a step; the weather never worked out; the harness handing no length; groups saved but not read back) made at least one test of `tests/test_days.py` fail [MEASURED, each in a copy of the code] |

### Departures and limits

1. A step is made when it begins, not when it ends. A monthly stage cannot see the later days of its own month; listed
   before a daily stage it sees the month before whole, which is the closest it comes to a month's summary.
2. A run must start on the first day of a step of every stage: with a yearly stage, on the first day of a year.
3. The months are equal shares of the year in time, as the weather has them, so their whole days come in a pattern of
   30 and 31 that changes from year to year. They are not the months of any human calendar.
4. A continuation is refused for other stages, steps or calendar, but not for other constants or implementations of
   the processes of the dated clock or the weather: the run store holds no fingerprint of them, as before.
5. A start step of a process on the dated clock (`has_start`) is still not run, and a stage's `first_date` in
   `stages.yaml` is still accepted and not used; both were so before [INFERRED: read in `run_dated` and
   `_check_settings`, not tried].
6. A run reads only the fields of the stored world: a member of a group worked out in the climate stage, and a push
   with a fixed region on a group, are not handed to a stage of the dated clock or the weather that reads that group
   [INFERRED: read in `Engine._world_from`, which fills fields only; not tried, and no process of the default data
   reads a group on those clocks].
7. A run store written before this change records no steps. A continuation of one is refused with the words of the
   second new refusal ("the run store's stages step through dates as follows: none; ...") [MEASURED: a store written
   by hand in the old layout]. No command ever wrote one.

### Measured

A probe stage on the preview world (seed 20261004; the build took 111.6 s beside another job on the 4-core machine):
a monthly stage that keeps half of last month's value and adds the climate's surface temperature of its month times
the days of the month, and a daily stage that reads the weather's temperature [MEASURED, a script outside the
repository, on 2026-11-09]:

| Run | Time | Days whose weather was worked out |
|---|---|---|
| The monthly stage alone, days 0 to 365 (12 steps) | 0.39 s, the first reading of the world's fields included | 0 |
| The monthly stage alone, days 0 to 3652 (120 steps) | 0.09 s | 0 |
| The monthly and the daily stage, days 0 to 365 | 34.8 s | 366 |

With a daily stage nearly all the time is the weather, 0.095 s a day here against the 0.3 s of section 18.5; why the
two differ was not looked into. `tests/test_days.py` holds 36 tests, 17 more than before and one rewritten, and takes
about 12 s; `tests/test_store_server.py` gained one [MEASURED]. The README's count of 997 tests is 18 short.
