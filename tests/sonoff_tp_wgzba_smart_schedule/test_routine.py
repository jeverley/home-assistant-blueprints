"""The routine: alarm mornings, getting up, bedtime, a second alarm, Warm on
time for warmer periods, and a ZHA reload."""
from sim import World, T

UP = {'Schedule 1': [('00:00', 16), ('07:00', 21), ('07:30', 20), ('22:30', 16)],
      'Schedule 2': [('00:00', 16), ('07:00', 19), ('07:30', 18), ('22:30', 16)],
      'Schedule 3': [('00:00', 12)]}
DOWN = {'Schedule 1': [('00:00', 15), ('07:00', 20), ('08:00', 19), ('17:00', 20), ('22:30', 15)],
        'Schedule 2': [('00:00', 15), ('07:00', 19), ('08:00', 18), ('17:00', 19), ('22:30', 15)],
        'Schedule 3': [('00:00', 12)]}
LEARNED = '{"f":0,"a":0,"r":{},"l":{"v":[2.0,8.0,15.0]}}'


def world(schedules=UP, room=19.0, alarm=None, start=T(4, 0), learned=True, **inputs):
    inputs.setdefault('getting_up_enabled', False)
    inputs.setdefault('bedtime_enabled', False)
    w = World(schedules=schedules, room=room, start=start, inputs=inputs)
    w.room['loss'] = 0.0
    if learned:
        w.set('input_text.state', LEARNED)
    w.set_alarm(alarm)
    w.prime()
    w.run('catch-up')
    return w


def timers(w):
    """[(time, temperature, period)] for each Timer the routine applied."""
    out = []
    for r in w.runs:
        temp = period = None
        for c in r['calls']:
            if 'override_target_temperature' in c:
                temp = float(c.split('"value": ')[1].rstrip('}'))
            if 'override_period' in c:
                period = int(c.split('"value": ')[1].rstrip('}'))
            if 'override_apply' in c:
                out.append((r['time'], temp, period))
    return out


def test_early_alarm_starts_period_2_early_and_keeps_its_length():
    # Learned: 8 + 15 x (21 - 19) = 38 minutes before a 06:00 alarm.
    w = world(alarm=T(6, 0))
    w.advance(T(8, 0))
    t = timers(w)
    assert t[0][0] == T(5, 22) and t[0][1] == 21.0, t
    # Period 2 runs for its usual 30 minutes from the alarm, then period 3's
    # temperature until period 3's usual start.
    assert t[0][0] + __import__('datetime').timedelta(minutes=t[0][2]) == T(6, 30), t
    assert t[1][0] == T(6, 30) and t[1][1] == 20.0, t
    assert w.override() == 'Idle' and w.plan() == {}


def test_late_alarm_holds_period_1_until_the_late_start():
    w = world(alarm=T(8, 30), room=20.5)
    w.advance(T(9, 30))
    t = timers(w)
    # Held at period 1 (16) from just before period 2 until the start
    # (08:30 less 8 + 15 x 0.5 = 15 minutes), then period 2 for its length.
    assert t[0][0] == T(6, 59) and t[0][1] == 16.0, t
    assert t[1][1] == 21.0 and T(8, 10) <= t[1][0] <= T(8, 20), t


def test_warm_on_time_off_starts_five_minutes_before_the_alarm():
    w = world(alarm=T(6, 0), warm_on_time_enabled=False)
    w.advance(T(6, 30))
    assert timers(w)[0][0] == T(5, 55), timers(w)


def test_no_second_late_hold_after_a_morning_and_a_trip_out():
    # 5 November: a 05:15 morning, everyone out and back, then a 07:30 alarm.
    w = world(alarm=T(5, 15), room=20.3)
    w.advance(T(5, 16))
    w.set_alarm(T(7, 30))
    w.advance(T(6, 23))
    w.set('zone.home', '0')
    w.set_occupied('living_room', False)
    w.states['binary_sensor.living_room_occupancy'].last_changed = T(6, 0)
    w.advance(T(6, 29))
    w.set('zone.home', '1')
    w.set_occupied('living_room', True)
    w.advance(T(8, 30))
    late = [x for x in timers(w) if x[0] >= T(6, 29)]
    assert not any(x[1] == 16.0 for x in late), late


def test_everyone_out_before_the_alarm_still_gets_the_morning():
    w = world(alarm=T(6, 0))
    w.advance(T(5, 0))
    w.set('zone.home', '0')
    w.set_occupied('living_room', False)
    w.states['binary_sensor.living_room_occupancy'].last_changed = T(4, 30)
    w.advance(T(5, 15))
    w.set('zone.home', '1')
    w.set_occupied('living_room', True)
    w.advance(T(6, 10))
    assert any(x[1] == 21.0 and T(5, 15) <= x[0] <= T(5, 30) for x in timers(w)), timers(w)


def test_getting_up_with_no_alarm_starts_the_morning():
    w = world(getting_up_enabled=True)
    w.advance(T(6, 15))
    w.set('binary_sensor.awake', 'on')
    w.advance(T(6, 20))
    t = timers(w)
    assert t and t[0][0] == T(6, 16) and t[0][1] == 21.0, t


def test_bedtime_starts_the_night_temperature_early():
    w = world(start=T(21, 0), bedtime_enabled=True, room=20.0)
    w.set('binary_sensor.awake', 'on')
    w.advance(T(21, 40))
    w.set('binary_sensor.awake', 'off')
    w.advance(T(22, 0))
    t = timers(w)
    assert t and t[0][1] == 16.0 and T(21, 55) <= t[0][0] <= T(21, 57), t


def test_warm_on_time_starts_a_warmer_evening_period_early():
    # Downstairs at 19 C before the 17:00 period at 20 C: the room is at or
    # below 20 - 0.6, so it starts 8 + 15 x 1 = 23 minutes early.
    w = world(schedules=DOWN, start=T(15, 0))
    w.advance(T(16, 30))
    w.set_room(19.0)
    w.advance(T(17, 10))
    t = timers(w)
    assert t and t[0][0] == T(16, 37) and t[0][1] == 20.0, t


def test_warm_on_time_leaves_an_already_warm_room_alone():
    w = world(schedules=DOWN, start=T(15, 0), room=19.5)
    w.advance(T(17, 10))
    assert not timers(w), timers(w)




def test_no_thermostat_call_while_zha_is_reloading_then_a_catch_up():
    # ZHA reloads from 05:00: every thermostat entity bar the climate entity
    # goes unavailable, and they come back one by one, the schedule group
    # first. A ZHA call to an unavailable entity can wait forever and hold up
    # every queued run, so no run touches the thermostat until all are back.
    # The room cools and the thermostat heats and idles meanwhile, unreported.
    # Then a catch-up starts the morning that fell due during the reload.
    w = world(alarm=T(7, 0), room=15.8)
    w.advance(T(5, 0))
    ents = [e for e in w.devices['dev'] if not e.startswith('climate.')]
    for e in ents:
        w.set(e, 'unavailable')
    w.room['loss'] = 1.0
    calls = len(w.log)
    heating = set()
    w.advance(T(6, 0), on_minute=lambda w: heating.add(w.room['heating']))
    assert heating == {True, False}, 'the thermostat should heat and idle during the reload'
    assert w.states['sensor.t_hvac_action'].state == 'unavailable'
    w.restore('select.t_schedule_group')
    # A run in the meantime, here started by hand, stops at its start.
    r = w.run('catch-up')
    assert r['result'].startswith('stopped: The thermostat'), r['result']
    w.advance(T(6, 30))
    assert len(w.log) == calls, w.log[calls:]
    for e in ents:
        w.restore(e)
    assert w.states['sensor.t_hvac_action'].state == ('heating' if w.room['heating'] else 'idle')
    w.advance(T(6, 31))
    assert [t[0] for t in timers(w)] == [T(6, 31)], timers(w)
