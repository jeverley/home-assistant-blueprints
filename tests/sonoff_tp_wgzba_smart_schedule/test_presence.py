"""Occupancy and geofencing: the schedule group as areas and people come and
go, and pre-heating on the way home."""
import datetime as dt

from sim import World, T


def world(start=T(12, 0), **inputs):
    inputs.setdefault('getting_up_enabled', False)
    inputs.setdefault('bedtime_enabled', False)
    w = World(start=start, inputs=inputs, room=20.0)
    w.prime()
    w.run('catch-up')
    return w


def leave_home(w):
    w.set('zone.home', '0')
    w.set_occupied('living_room', False)


def test_heated_area_empty_switches_to_schedule_2_and_back():
    w = world()
    assert w.group() == 'Schedule 1'
    w.set_occupied('living_room', False)
    w.advance(T(12, 4))
    assert w.group() == 'Schedule 1', 'not before the empty delay'
    w.advance(T(12, 6))
    assert w.group() == 'Schedule 2'
    w.set_occupied('living_room', True)
    w.advance(T(12, 8))
    assert w.group() == 'Schedule 1'


def test_follow_occupancy_off_stays_on_schedule_1_while_home():
    w = world(follow_occupancy=False)
    w.set_occupied('living_room', False)
    w.advance(T(12, 10))
    assert w.group() == 'Schedule 1'


def test_nobody_home_switches_to_schedule_3():
    w = world()
    leave_home(w)
    w.advance(T(12, 10))
    assert w.group() == 'Schedule 3'
    w.set('zone.home', '1')
    w.advance(T(12, 11))
    assert w.group() in ('Schedule 1', 'Schedule 2')


def geo_world(progress=500):
    w = world(proximity_devices=['prox'], geofencing_progress=progress)
    w.add_person('alex', 0, 'arrived')
    w.prime()
    return w


def drive(w, path, start, step=1):
    """path: [(distance m, direction)], one per minute from start."""
    t = start
    for dist, direction in path:
        t += dt.timedelta(minutes=step)
        w.move('alex', dist, direction)
        w.advance(t)
    return t


def test_heading_home_after_real_progress_pre_heats():
    w = geo_world()
    leave_home(w)
    t = drive(w, [(d, 'away_from') for d in range(500, 6001, 500)], T(12, 0))
    w.advance(t + dt.timedelta(minutes=10))
    assert w.group() == 'Schedule 3'
    assert w.helper().get('g') == [60], w.helper()
    # Back towards home: 5.7 km is not yet 500 m of progress, 5.4 km is.
    t = drive(w, [(5700, 'towards')], w.now)
    assert w.group() == 'Schedule 3'
    t = drive(w, [(5400, 'towards')], t)
    assert w.group() == 'Schedule 2', w.group()


def test_wobbling_near_the_furthest_point_does_not_pre_heat():
    w = geo_world()
    leave_home(w)
    t = drive(w, [(d, 'away_from') for d in range(500, 2501, 500)], T(12, 0))
    wobble = [(2450, 'towards'), (2480, 'away_from'), (2420, 'towards'), (2460, 'stationary')] * 5
    drive(w, wobble, t)
    assert w.group() == 'Schedule 3'


def test_without_the_progress_check_any_heading_home_pre_heats():
    w = geo_world(progress=0)
    leave_home(w)
    t = drive(w, [(d, 'away_from') for d in range(500, 2501, 500)], T(12, 0))
    drive(w, [(2450, 'towards')], t)
    assert w.group() == 'Schedule 2'


def test_the_furthest_point_resets_once_home():
    w = geo_world()
    leave_home(w)
    t = drive(w, [(d, 'away_from') for d in range(500, 3001, 500)], T(12, 0))
    t = drive(w, [(d, 'towards') for d in range(2500, -1, -500)], t)
    w.set('zone.home', '1')
    w.move('alex', 0, 'arrived')
    w.advance(t + dt.timedelta(minutes=2))
    assert 'g' not in w.helper(), w.helper()
