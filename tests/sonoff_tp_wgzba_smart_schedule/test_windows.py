"""Windows: the thermostat turns off while a window in the heated areas is
open, and goes back to its schedule once every window has closed."""
from sim import T, house
from test_routine import UP, LEARNED, timers


def world(room=19.0, alarm=T(7, 0), **inputs):
    return house(schedules=UP, room=room, alarm=alarm, learned=LEARNED, inputs=inputs)


def mode(w):
    return w.states['select.t_device_work_mode'].state


def test_a_window_open_during_the_warm_up_turns_off_and_closing_resumes():
    # The morning starts at 06:22. The window opens at 06:30, during the
    # warm-up: after the 2 minute window delay the thermostat turns off and
    # the measurement is dropped. Closing it at 06:40 puts it back on its
    # schedule, and the routine applies its Timer again.
    w = world()
    w.advance(T(6, 30))
    assert w.measuring() is not None
    w.set_window('living_room', True)
    w.advance(T(6, 31))
    assert mode(w) == 'Schedule', 'not before the window delay'
    w.advance(T(6, 33))
    assert mode(w) == 'Off'
    assert w.helper().get('o'), w.helper()
    assert w.measuring() is None and w.learned() == [2.0, 8.0, 15.0], w.helper()
    assert w.states['sensor.t_override_mode'].state == 'Idle'
    w.advance(T(6, 40))
    assert mode(w) == 'Off', 'stays off while the window is open'
    w.set_window('living_room', False)
    w.advance(T(6, 41))
    assert mode(w) == 'Schedule'
    assert 'o' not in w.helper(), w.helper()
    assert [t for t in timers(w) if t[0] >= T(6, 40)], timers(w)
    assert w.states['sensor.t_override_mode'].state == 'Timer'


def test_a_window_open_for_less_than_the_delay_changes_nothing():
    w = world()
    w.advance(T(6, 30))
    m = w.measuring()
    w.set_window('living_room', True)
    w.advance(T(6, 31))
    w.set_window('living_room', False)
    w.advance(T(6, 40))
    assert mode(w) == 'Schedule'
    assert w.measuring() is not None and w.measuring()[:3] == m[:3]
    assert not any('t_device_work_mode' in c for r in w.runs for c in r['calls'])


def test_an_off_you_set_is_left_alone():
    # You turn the thermostat off yourself. A window opening and closing does
    # not turn it back on.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_work_mode('Off')
    w.advance(T(10, 5))
    w.set_window('living_room', True)
    w.advance(T(10, 10))
    w.set_window('living_room', False)
    w.advance(T(10, 15))
    assert mode(w) == 'Off'
    assert 'o' not in w.helper(), w.helper()


def test_a_mode_you_change_while_off_is_kept():
    # Turned off for a window, then you set it to Manual. Closing the window
    # leaves Manual.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert mode(w) == 'Off'
    w.set_work_mode('Manual')
    w.advance(T(10, 5))
    w.set_window('living_room', False)
    w.advance(T(10, 6))
    assert mode(w) == 'Manual'
    assert 'o' not in w.helper(), w.helper()


def test_turned_back_on_with_the_window_open_stays_on_and_carries_on():
    # Turned off for a window, then you put it back on its schedule with the
    # window still open. It is not turned off again, runs carry on (the room
    # empties and Schedule 2 follows), and closing the window clears the note
    # without touching the mode, with a catch-up run.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert mode(w) == 'Off'
    w.set_work_mode('Schedule')
    w.advance(T(10, 10))
    assert mode(w) == 'Schedule', 'not turned off again while the same window is open'
    w.set_occupied('living_room', False)
    w.advance(T(10, 20))
    assert w.group() == 'Schedule 2', 'runs carry on'
    n = len(w.runs)
    w.set_window('living_room', False)
    w.advance(T(10, 21))
    assert mode(w) == 'Schedule' and 'o' not in w.helper(), w.helper()
    assert not any('t_device_work_mode' in c for r in w.runs[n:] for c in r['calls'])
    assert any(r['result'] == 'done' for r in w.runs[n:]), [(r['id'], r['result']) for r in w.runs[n:]]
    # A window opening again later turns it off as before.
    w.set_window('living_room', True)
    w.advance(T(10, 24))
    assert mode(w) == 'Off'


def test_a_window_delay_written_as_text_works():
    w = world(alarm=None, window_delay='00:02:00')
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert mode(w) == 'Off'


def test_a_window_closed_while_zha_reloads_is_still_caught():
    # Off for a window. ZHA reloads, and the window closes meanwhile: once
    # the thermostat is back, a catch-up puts it back on its schedule.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert mode(w) == 'Off'
    w.thermostat_offline()
    w.set_window('living_room', False)
    w.advance(T(10, 10))
    assert w.helper().get('o'), 'nothing written while the thermostat is unavailable'
    w.thermostat_online()
    w.advance(T(10, 11))
    assert mode(w) == 'Schedule'
    assert 'o' not in w.helper(), w.helper()


def test_window_control_off_leaves_the_thermostat_alone():
    w = world(alarm=None, window_control_enabled=False)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 30))
    assert mode(w) == 'Schedule'


def test_turning_window_control_off_undoes_an_off_it_set():
    # Off for a window, then Window control is turned off with the window
    # still open: the next run puts the thermostat back on its schedule.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert mode(w) == 'Off'
    w.set_input('window_control_enabled', False)
    w.run('catch-up')
    w.advance(T(10, 4))
    assert mode(w) == 'Schedule' and 'o' not in w.helper(), w.helper()
