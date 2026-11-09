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
  override is applied.
- `test_learning.py`: learning the warm-up time, how a measurement starts and
  ends, and what is learned.
- `test_routine.py`: alarm mornings, getting up, bedtime, a second alarm, and
  Warm on time for warmer periods.
- `test_presence.py`: occupancy, the away schedule, and geofencing pre-heating.
- `test_replay.py`: real mornings fed through the blueprint's own learning step,
  from `data/mornings.csv`.

## Data

`data/mornings.csv` holds the two thermostats' climate entity between 05:30
and 08:00 on real mornings: the time (UTC), the room, its reported temperature,
its HVAC action and its target. Nothing else from the house is kept.
