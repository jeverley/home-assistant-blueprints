# Tests for the Sonoff TP-WGZBA smart schedule blueprint

These run the blueprint in a small simulator, so changes can be checked before
they reach a real thermostat. They need Python 3.11 or later with `jinja2` and
`pyyaml`, and nothing from Home Assistant itself.

```
python3 tests/sonoff_tp_wgzba_smart_schedule/run_tests.py
```

- `-k text` runs only the tests whose name contains the text.
- `-v` shows the traceback of each failure.
- `--blueprint path` runs the tests against another copy of the blueprint, for
  example an older version from git, to check that a test fails without the fix
  it covers:

  ```
  git show <commit>:blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml > /tmp/old.yaml
  python3 tests/sonoff_tp_wgzba_smart_schedule/run_tests.py --blueprint /tmp/old.yaml
  ```

A test fails on a failed assertion or on any error, so a broken blueprint or
simulator never passes silently. The runner exits with 1 if any test failed.

## What is here

- `sim.py`: the simulator. It loads the blueprint with a set of inputs and models
  just enough of Home Assistant (states, the template functions the blueprint
  uses, its triggers, conditions and actions) and of the thermostat (its stored
  schedules, the override Timer, its heating hysteresis, the room warming and
  cooling, and its temperature reports in 0.3 °C steps or every 15 minutes).
  `fresh_on_apply=False` models firmware that keeps its hysteresis when an
  override is applied. While an entity reads unavailable (as when ZHA reloads),
  the thermostat carries on with its own values without reporting them, and
  `restore()` brings the entity back with the thermostat's current value.
- `test_learning.py`: learning the warm-up time, how a measurement starts and
  ends, and what is learned.
- `test_routine.py`: alarm mornings, getting up, bedtime, a second alarm, Warm
  on time for warmer periods, and a ZHA reload.
- `test_presence.py`: occupancy, the away schedule, and geofencing pre-heating.
- `test_replay.py`: real mornings fed through the blueprint's own learning step,
  from `data/mornings.csv`, each checked against figures worked out
  independently from its reports. `test_presence.py` also replays two days of
  real trips from `data/trips.csv` and checks when pre-heating started.

## Data

`data/mornings.csv` holds the two thermostats' climate entity between 02:30
and 08:30 on real mornings (31 October to 10 November 2026): the time (UTC),
the room, its reported temperature, its HVAC action and its target.

`data/trips.csv` holds two people's Proximity readings on 31 October and
2 November 2026: the time (UTC), the person (as `person_a` or `person_b`), and
either their distance from home, rounded to 100 m, or their direction of
travel.

Nothing else from the house is kept.
