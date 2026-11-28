"""Windows: the thermostat's external contact sensor is turned on while a
window in the heated areas is open, so it suspends its heating, and off again
once every window has closed."""
from sim import T, house
from test_routine import UP, LEARNED, timers

SWITCH = 'switch.t_external_contact_sensor'


def world(room=19.0, alarm=T(7, 0), **inputs):
    return house(schedules=UP, room=room, alarm=alarm, learned=LEARNED, inputs=inputs)


def contact(w):
    return w.states[SWITCH].state


def switch_calls(w, runs=None):
    return [c for r in (runs if runs is not None else w.runs) for c in r['calls'] if 'external_contact' in c]


def test_a_window_open_during_the_warm_up_suspends_heating_and_closing_resumes():
    # The morning starts at 06:22. The window opens at 06:30, during the
    # warm-up: after the 2 minute window delay the contact sensor is turned
    # on, the heating stops and the measurement is dropped. Nothing is written
    # to the thermostat while it is on. Closing the window at 06:40 turns it
    # off, and the heating and the routine's Timer carry on.
    w = world()
    w.advance(T(6, 30))
    assert w.measuring() is not None and w.room['heating']
    w.set_window('living_room', True)
    w.advance(T(6, 31))
    assert contact(w) == 'off', 'not before the window delay'
    w.advance(T(6, 33))
    assert contact(w) == 'on' and not w.room['heating']
    assert w.helper().get('o'), w.helper()
    assert w.measuring() is None and w.learned() == LEARNED, w.helper()
    n, calls = len(w.runs), len(w.log)
    w.advance(T(6, 40))
    assert contact(w) == 'on', 'stays on while the window is open'
    assert all(r['result'].startswith('stopped: A window is still open') for r in w.runs[n:]), \
        [(r['id'], r['result']) for r in w.runs[n:]]
    assert not [c for c in w.log[calls:] if 'input_text' not in c], w.log[calls:]
    w.set_window('living_room', False)
    w.advance(T(6, 41))
    assert contact(w) == 'off' and w.room['heating']
    assert 'o' not in w.helper(), w.helper()
    assert w.states['sensor.t_override_mode'].state == 'Timer'


def test_a_window_open_for_less_than_the_delay_changes_nothing():
    w = world()
    w.advance(T(6, 30))
    m = w.measuring()
    w.set_window('living_room', True)
    w.advance(T(6, 31))
    w.set_window('living_room', False)
    w.advance(T(6, 40))
    assert contact(w) == 'off'
    assert w.measuring() is not None and w.measuring()[:3] == m[:3]
    assert not switch_calls(w)


def test_it_works_whatever_the_thermostats_mode():
    # In Manual mode too: suspending heating with a window open does not
    # depend on the schedule.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_work_mode('Manual')
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert contact(w) == 'on'
    w.set_window('living_room', False)
    w.advance(T(10, 4))
    assert contact(w) == 'off'
    assert w.states['select.t_device_work_mode'].state == 'Manual'


def test_a_contact_sensor_you_turn_on_is_left_alone():
    # You turn the contact sensor on yourself. A window opening and closing
    # does not turn it off.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set(SWITCH, 'on')
    w.advance(T(10, 5))
    w.set_window('living_room', True)
    w.advance(T(10, 10))
    w.set_window('living_room', False)
    w.advance(T(10, 15))
    assert contact(w) == 'on'
    assert 'o' not in w.helper(), w.helper()
    assert not switch_calls(w)


def test_turned_off_with_the_window_open_stays_off_and_carries_on():
    # The contact sensor is on for a window, then you turn it off with the
    # window still open. It is not turned on again, runs carry on (the room
    # empties and Schedule 2 follows), and closing the window clears the note
    # without touching the contact sensor, with a catch-up run.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert contact(w) == 'on'
    w.set(SWITCH, 'off')
    w.advance(T(10, 10))
    assert contact(w) == 'off', 'not turned on again while the same window is open'
    w.set_occupied('living_room', False)
    w.advance(T(10, 20))
    assert w.group() == 'Schedule 2', 'runs carry on'
    n = len(w.runs)
    w.set_window('living_room', False)
    w.advance(T(10, 21))
    assert contact(w) == 'off' and 'o' not in w.helper(), w.helper()
    assert not switch_calls(w, w.runs[n:])
    assert any(r['result'] == 'done' for r in w.runs[n:]), [(r['id'], r['result']) for r in w.runs[n:]]
    # A window opening again later turns it on as before.
    w.set_window('living_room', True)
    w.advance(T(10, 24))
    assert contact(w) == 'on'


def test_a_window_closed_while_zha_reloads_is_still_caught():
    # On for a window. ZHA reloads, and the window closes meanwhile: once the
    # thermostat is back, a catch-up turns the contact sensor off.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert contact(w) == 'on'
    w.thermostat_offline()
    w.set_window('living_room', False)
    w.advance(T(10, 10))
    assert w.helper().get('o'), 'nothing written while the thermostat is unavailable'
    w.thermostat_online()
    w.advance(T(10, 11))
    assert contact(w) == 'off'
    assert 'o' not in w.helper(), w.helper()


def test_window_control_off_leaves_the_contact_sensor_alone():
    w = world(alarm=None, window_control_enabled=False)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 30))
    assert contact(w) == 'off'


def test_turning_window_control_off_undoes_a_contact_sensor_it_turned_on():
    # On for a window, then Window control is turned off with the window
    # still open: the next run turns the contact sensor off.
    w = world(alarm=None)
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert contact(w) == 'on'
    w.set_input('window_control_enabled', False)
    w.run('catch-up')
    w.advance(T(10, 4))
    assert contact(w) == 'off' and 'o' not in w.helper(), w.helper()


def test_a_window_delay_written_as_text_works():
    w = world(alarm=None, window_delay='00:02:00')
    w.advance(T(10, 0))
    w.set_window('living_room', True)
    w.advance(T(10, 3))
    assert contact(w) == 'on'
