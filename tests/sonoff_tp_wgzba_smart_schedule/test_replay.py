"""Replays real mornings through the blueprint's own learning step.

data/mornings.csv holds the two thermostats' climate entity between 05:30 and
08:00: the time (UTC), the room, its reported temperature, its HVAC action
and its target. Each morning is fed, event by event, through the Learn the
warm-up time template, starting from the learned values the blueprint held
that morning (on the current measuring rules), and the result is checked.
"""
import csv
import datetime as dt
from pathlib import Path

from sim import World, TZ

DATA = Path(__file__).resolve().parent / 'data' / 'mornings.csv'

# (date, room): (learned before, learned after), on the current rules.
EXPECTED = {
    ('2026-11-07', 'upstairs'): ([3.36, 8.0, 20.4], [3.69, 7.9, 22.7]),
    ('2026-11-07', 'downstairs'): ([3.36, 5.0, 14.9], [3.69, 5.3, 15.2]),
    ('2026-11-08', 'upstairs'): ([3.69, 7.9, 22.7], [3.95, 7.0, 23.2]),
    ('2026-11-08', 'downstairs'): ([3.69, 5.3, 15.2], [3.95, 5.8, 14.0]),
    # Peaked at 20.8, fell to 20.6 before the Timer ended: measured to the peak.
    ('2026-11-09', 'upstairs'): ([3.95, 7.0, 23.2], [4.16, 6.5, 25.2]),
    ('2026-11-09', 'downstairs'): ([3.95, 5.8, 14.0], [4.16, 6.0, 13.8]),
}


def load():
    out = {}
    for r in csv.DictReader(DATA.open()):
        t = dt.datetime.fromisoformat(r['time_utc'].replace('Z', '+00:00')).astimezone(TZ)
        out.setdefault((t.strftime('%Y-%m-%d'), r['room']), []).append(
            (t, float(r['current_temperature']), r['hvac_action'], float(r['target'])))
    return out


def replay(rows, learned):
    """Feed one morning through the learning template; return the learned values."""
    w = World(start=rows[0][0])
    step = next(a for a in w.bp['actions'] if a.get('alias') == 'Learn the warm-up time')
    template = step['then'][0]['variables']['state']
    learning = w.bp['variables']['learning']
    # The morning's start: our Timer raising the target, with the heating on.
    i = next(k for k, r in enumerate(rows) if r[2] == 'heating' and rows[k - 1][2] != 'heating')
    t0, room0, _, _ = rows[i]
    j = next(k for k in range(i, len(rows)) if rows[k][3] > rows[i - 1][3])
    target = rows[j][3]
    drop = next((r[0] for r in rows[j:] if r[3] < target), None)
    state = {'learn': {'v': learned, 'm': [int(t0.timestamp()), room0, target]}}
    w.set('select.t_schedule_group', 'Schedule 1', when=t0 - dt.timedelta(hours=1))
    w.set('sensor.t_hvac_action', 'heating', when=t0)
    for t, cur, hvac, tgt in rows[i + 1:]:
        w.now = t
        w.set('sensor.t_hvac_action', hvac)
        w.set('climate.t', 'heat', {'current_temperature': cur, 'temperature': tgt, 'hvac_action': hvac}, force_update=True)
        timer_on = drop is None or t < drop
        ctx = dict(state=state, learning=learning, heat_within=w.bp['trigger_variables']['heat_within'],
                   hvac_action_sensor='sensor.t_hvac_action', climate_entity='climate.t', room_temp=cur,
                   schedule_group='select.t_schedule_group', period_entities=[],
                   plan={'until': int(drop.timestamp()) if drop else 0, 'cancelled': False, 'temp': target,
                         'applied': int(t0.timestamp())},
                   plan_today=True, exit_pressed_at=0, override_running=timer_on, on_schedule=True,
                   routine_timer_running=timer_on, high_threshold=0.2)
        state = w.render(template, ctx)
        if 'm' not in state['learn']:
            break
    return state['learn'].get('v')


def test_real_mornings_learn_what_the_rules_say():
    data = load()
    for key, (before, after) in EXPECTED.items():
        got = replay(data[key], before)
        assert got == after, (key, got, after)
