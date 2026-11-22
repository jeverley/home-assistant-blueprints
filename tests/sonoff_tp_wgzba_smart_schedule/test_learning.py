"""Learning the warm-up time: when a measurement starts, how it ends, and what
is learned. Each test runs a morning in the simulator and checks the result."""
from sim import World, T, house

LEARNED = [2.0, 8.0, 15.0]  # weight, dead time (min), minutes per degree


def morning(room=19.0, alarm=T(7, 0), until=T(7, 50), learned=LEARNED, events=None, **kw):
    """An alarm morning from 04:00. events: {(h, m): f(world)} applied before
    that minute's triggers are checked."""
    w = house(room=room, alarm=alarm, learned=learned, **kw)

    def hook(w):
        f = (events or {}).get((w.now.hour, w.now.minute))
        if f:
            f(w)
    w.advance(until, on_minute=hook)
    return w


def close(a, b, tol):
    return abs(a - b) <= tol


def test_normal_morning_ends_at_the_target_and_learns_the_true_rate():
    w = morning(room=19.0)
    v = w.learned()
    assert v[0] == 2.6, v
    # The room warms at 15 min/C after an 8 minute lag: one morning moves the
    # averages towards those, and the rate should come out at about 15.
    assert close(v[2], 15.0, 0.6), v
    assert w.measuring() is None


def test_the_morning_reaches_the_target_by_the_alarm():
    reached = {}

    def watch(w):
        if 'at' not in reached and w.room['temp'] >= 21.0:
            reached['at'] = w.now
    w = house(room=19.0, alarm=T(7, 0), learned=[3.0, 8.0, 15.0])
    w.advance(T(7, 30), on_minute=watch)
    assert T(6, 57) <= reached['at'] <= T(7, 2), reached


def test_a_dip_in_the_reading_is_ignored():
    def dip(w):
        w.set_room(w.room['temp'] - 0.3)

    def back(w):
        w.set_room(w.room['temp'] + 0.3)
    plain = morning(room=19.0).learned()
    dipped = morning(room=19.0, events={(6, 45): dip, (6, 46): back}).learned()
    assert dipped == plain, (plain, dipped)


def test_cut_short_by_our_timer_ends_at_the_highest_report_not_a_later_fall():
    # A slow room (2 C/h) that peaks, then falls 0.3 and stalls, before our
    # Timer hands over to the cooler period 3 at 07:30.
    def fall(w):
        w.room['rate'] = 0.0
        w.set_room(w.room['temp'] - 0.3)
    w = morning(room=18.6, rate=2.0, until=T(8, 10), events={(7, 16): fall})
    v = w.learned()
    # 2 C/h is 30 min/C. Measured to the fall it would be far slower.
    rate = LEARNED[2] + (v[2] - LEARNED[2]) * 2.6  # this morning's own rate
    assert close(rate, 30.0, 3.0), (v, rate)


def test_high_threshold_zero_ends_at_the_stop_point():
    w = morning(room=19.0)
    w2 = house(room=19.0, alarm=T(7, 0), learned=LEARNED, high_threshold=0)
    w2.advance(T(7, 50))
    assert w2.learned() and w2.learned()[0] == 2.6, w2.learned()
    assert close(w2.learned()[2], w.learned()[2], 1.0), (w.learned(), w2.learned())


def test_an_idle_well_below_the_stop_point_is_dropped():
    # An open window keeps the thermostat off.
    w = morning(room=19.0, events={(6, 47): lambda w: w.thermostat_stops()})
    assert w.learned() == LEARNED, w.learned()
    assert w.measuring() is None


def test_a_rise_of_only_0_3_is_not_measured():
    w = morning(room=20.7, until=T(7, 10))
    assert w.learned() == LEARNED
    assert not any(r['id'] == 'warming' for r in w.runs)


def test_a_target_changed_by_hand_during_our_timer_is_dropped():
    for value in (22, 20):
        def hand(w, value=value):
            w.set('number.t_override_target_temperature', str(value))
            w.refresh()
        w = morning(room=19.0, events={(6, 45): hand})
        assert w.learned() == LEARNED, (value, w.learned())


def test_a_thermostat_that_does_not_heat_is_dropped_after_two_minutes():
    # Strict hysteresis firmware: applying our Timer with the room inside the
    # band (above 21 - 0.6) does not start the heating.
    w = morning(room=20.5, fresh_on_apply=False, until=T(7, 0), inputs={'warm_on_time_enabled': True})
    starts = [r for r in w.runs if r['id'] == 'early-alarm']
    assert starts, 'the morning should start'
    assert w.measuring() is None and w.learned() == LEARNED
    drop = [r for r in w.runs if r['id'] == 'warming' and r['time'] > starts[0]['time']]
    assert drop and (drop[0]['time'] - starts[0]['time']).total_seconds() <= 180, drop[:1]


def test_the_first_morning_uses_the_starting_values_and_the_second_its_own():
    w = morning(room=19.0, learned=None, until=T(7, 50))
    first = w.learned()
    assert first and first[0] == 1.0, first
    start = next(r for r in w.runs if r['id'] == 'early-alarm' and any('override_apply' in c for c in r['calls']))
    # Starting values: 10 + 20 x (21 - 19) = 50 minutes before 07:00.
    assert start['time'] == T(6, 10), start['time']


def test_the_helper_stays_within_255_characters():
    w = morning(room=17.0, until=T(6, 30))
    assert len(w.states['input_text.state'].state) <= 255


def test_a_target_report_that_arrives_with_the_idle_confirms_the_stop_point():
    # High threshold 0.5: the first report at or above 21 comes in the same
    # minute as the idle, so the stop point (21.5 at the idle) is the end.
    w = house(room=19.0, alarm=T(7, 0), learned=LEARNED, high_threshold=0.5)
    # At 06:56, clear of period 2's start, with the latest report 20.6.
    w.advance(T(7, 40), on_minute=lambda w: w.thermostat_stops(temp=21.5) if w.now == T(6, 56) else None)
    assert w.learned()[0] == 2.6 and w.measuring() is None, w.helper()


def test_an_idle_handled_after_our_timer_drops_still_ends_at_the_stop_point():
    # High threshold 0: the thermostat stops at 21.0 about 06:45, but the
    # Warmed up run is held up until our Timer hands over to period 3.
    sched = {'Schedule 1': [('00:00', 16), ('06:30', 21), ('06:50', 20), ('22:30', 16)],
             'Schedule 2': [('00:00', 16), ('06:30', 19), ('06:50', 18), ('22:30', 16)],
             'Schedule 3': [('00:00', 12)]}
    w = house(room=19.0, alarm=T(6, 20), learned=LEARNED, high_threshold=0, schedules=sched, rate=2.2)
    w.hold_trigger('warmed')
    seen = {}

    def note(w):
        if 'idle' not in seen and w.states['sensor.t_hvac_action'].state == 'idle' and w.measuring():
            seen['idle'], seen['m'] = w.now.timestamp(), w.measuring()
    w.advance(T(7, 10), on_minute=note)
    m = seen['m']
    # Ended at the stop point (21.0) at the idle, not at the latest report.
    rate = (seen['idle'] - m[3]) / 60 / (21.0 - m[4])
    assert abs(w.learned()[2] - (15.0 + (rate - 15.0) / 2.6)) < 0.11, (w.helper(), m, rate)


def test_a_later_top_up_idle_is_not_taken_for_the_stop_point():
    # The warm-up's own idle was missed. Its latest report is 20.9 at 06:30
    # (within 0.35 of the 21.2 stop point); an idle 46 minutes later belongs
    # to a later top-up, so the measurement is dropped rather than ended at
    # the stop point then. Within 30 minutes it would count.
    for idle_at, counted in ((T(7, 16), False), (T(6, 50), True)):
        w = World(room=20.9, start=T(5, 50), inputs={'getting_up_enabled': False, 'bedtime_enabled': False})
        w.seed(learned=LEARNED, measuring=(T(5, 50), 19.0, 21.0, (T(6, 0), 19.3), (T(6, 30), 20.9)))
        w.set('sensor.t_hvac_action', 'heating', when=T(5, 50))
        w.now = idle_at
        w.set('sensor.t_hvac_action', 'idle')
        w.run('warmed')
        assert (w.learned() != LEARNED) == counted, (idle_at, w.helper())
        assert w.measuring() is None


def test_a_later_periods_early_start_raising_the_target_ends_the_measurement():
    sched = {'Schedule 1': [('00:00', 15), ('06:30', 20), ('08:00', 21), ('22:30', 15)],
             'Schedule 2': [('00:00', 15), ('06:30', 19), ('08:00', 20), ('22:30', 15)],
             'Schedule 3': [('00:00', 12)]}
    w = house(room=16.0, rate=1.5, schedules=sched)
    w.advance(T(8, 0))
    v = w.learned()
    assert v and v[0] == 1.0 and abs(v[2] - 40.0) < 2.0, w.helper()



def _timer_ended_then_idle(idle_at=T(7, 31, 25), before_idle=None):
    """Upstairs, 17 November: our Timer from 04:51 to 07:30 at 21, readings
    18.5 at 05:02 to 20.1 at 07:19, then an idle well below the 21.2 stop
    point. before_idle(w) changes something before the idle."""
    from test_routine import UP
    w = World(room=20.1, start=T(4, 51), schedules=UP, inputs={'getting_up_enabled': False, 'bedtime_enabled': False})
    w.set('button.t_override_apply', T(4, 51).isoformat())
    w.set('sensor.t_override_mode', 'Timer', when=T(4, 51))
    w.seed(learned=LEARNED, measuring=(T(4, 51), 18.2, 21.0, (T(5, 2), 18.5), (T(7, 19), 20.1)))
    w.set('sensor.t_hvac_action', 'heating', when=T(4, 51))
    # Our Timer ends at 07:30 and the routine clears its plan, as it does.
    w.now = T(7, 30)
    w.set('sensor.t_override_mode', 'Idle')
    w.refresh()
    if before_idle:
        before_idle(w)
    w.now = idle_at
    w.set('sensor.t_hvac_action', 'idle')
    w.now = max(idle_at, T(7, 31, 25))
    w.run('warmed')
    return w


def test_an_idle_after_our_timer_ends_with_the_target_dropped_counts():
    # The run at 07:30 read the old target, so the measurement went on. The
    # idle came 85 s later: the target had dropped as our Timer ended, so it
    # was cut short and ends at the highest report rather than being dropped.
    w = _timer_ended_then_idle()
    assert w.states['climate.t'].attributes['temperature'] == 20.0
    v = w.learned()
    assert w.measuring() is None and v[0] == 2.6, w.helper()
    # 137 minutes for 1.6 C is 85.6 minutes per degree, capped at 60.
    assert abs(v[2] - (15.0 + (60.0 - 15.0) / 2.6)) < 0.11, v


def test_a_target_lowered_by_hand_after_our_timer_is_not_counted():
    def hand(w):
        w.set('sensor.t_device_work_mode_state', 'Temporary_Manual')
        w.set('number.t_override_target_temperature', '18')
    w = _timer_ended_then_idle(before_idle=hand)
    assert w.learned() == LEARNED and w.measuring() is None, w.helper()


def test_turning_the_thermostat_off_is_not_counted():
    w = _timer_ended_then_idle(before_idle=lambda w: w.set_work_mode('Off'))
    assert w.learned() == LEARNED and w.measuring() is None, w.helper()


def test_an_idle_before_our_timer_ended_is_not_counted():
    # The thermostat went idle at 07:24 for another reason, and the run that
    # read it came after our Timer ended at 07:30.
    w = _timer_ended_then_idle(idle_at=T(7, 24))
    assert w.learned() == LEARNED and w.measuring() is None, w.helper()
