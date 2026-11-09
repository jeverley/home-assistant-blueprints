"""A small simulator for the Sonoff TP-WGZBA smart schedule blueprint.

It loads the blueprint with a set of inputs, models just enough of Home
Assistant (states, the template functions the blueprint uses, its triggers,
conditions and actions) and of the thermostat (its stored schedules, the
override Timer, its heating hysteresis, the room warming and cooling, and its
temperature reports), and runs the automation as time passes.

It is a test aid, not a Home Assistant emulator: only what the blueprint uses
is modelled. Times are local (Europe/London).
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, StrictUndefined, Undefined

TZ = ZoneInfo('Europe/London')
REPO = Path(__file__).resolve().parents[2]
BLUEPRINT = REPO / 'blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml'


def T(h, m=0, s=0, day=12, month=10, year=2026):
    """A local time on the simulated day (12 October 2026 by default)."""
    return dt.datetime(year, month, day, h, m, s, tzinfo=TZ)


# --- Blueprint loading -------------------------------------------------------

class Input(str):
    pass


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor('!input', lambda loader, node: Input(node.value))


def load_blueprint(path=BLUEPRINT):
    return yaml.load(Path(path).read_text(), Loader=_Loader)


def input_defaults(bp):
    out = {}
    for section in bp['blueprint']['input'].values():
        for key, spec in section.get('input', {}).items():
            out[key] = spec.get('default')
    return out


def resolve(obj, inputs):
    """Replace !input tags with their values."""
    if isinstance(obj, Input):
        return inputs[str(obj)]
    if isinstance(obj, dict):
        return {k: resolve(v, inputs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve(v, inputs) for v in obj]
    return obj


def duration_seconds(d):
    if d is None:
        return 0
    if isinstance(d, dict):
        return d.get('hours', 0) * 3600 + d.get('minutes', 0) * 60 + d.get('seconds', 0)
    if isinstance(d, str):
        h, m, s = (int(x) for x in d.split(':'))
        return h * 3600 + m * 60 + s
    return float(d)


# --- States ------------------------------------------------------------------

class State:
    def __init__(self, entity_id, state, attributes, when):
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})
        self.last_changed = when
        self.last_updated = when
        self.domain = entity_id.split('.')[0]
        self.name = self.attributes.get('friendly_name', entity_id)

    def __repr__(self):
        return f'<State {self.entity_id}={self.state}>'


class Stop(Exception):
    def __init__(self, message, error=False):
        super().__init__(message)
        self.error = error


def native(text):
    """Home Assistant renders templates to native types where it can."""
    s = text.strip()
    if s == '':
        return ''
    if s in ('True', 'False', 'None'):
        return {'True': True, 'False': False, 'None': None}[s]
    if s[0] in '[{(\'"' or re.fullmatch(r'-?\d+(\.\d+)?', s):
        try:
            return ast.literal_eval(s)
        except Exception:
            return s
    return s


# --- The world -----------------------------------------------------------------

SCHEDULE_GROUPS = ('Schedule 1', 'Schedule 2', 'Schedule 3')
DEFAULT_SCHEDULES = {
    'Schedule 1': [('00:00', 16), ('07:00', 21), ('07:30', 20), ('22:30', 16)],
    'Schedule 2': [('00:00', 16), ('07:00', 19), ('07:30', 18), ('22:30', 16)],
    'Schedule 3': [('00:00', 12)],
}


class World:
    """The simulated house, thermostat and Home Assistant.

    schedules: {group: [(HH:MM, temp), ...]}, the same every day.
    inputs: blueprint inputs overriding the defaults.
    room: initial room temperature; rate (C/h while heating, after lag
    minutes), loss (C/h while idle).
    """

    def __init__(self, schedules=None, inputs=None, start=None, room=19.0, rate=4.0, lag=8.0, loss=0.1,
                 group='Schedule 1', reporting=True, fresh_on_apply=True, blueprint=BLUEPRINT):
        self.bp_raw = load_blueprint(blueprint)
        self.inputs = input_defaults(self.bp_raw)
        self.inputs.update({
            'thermostat_device': 'dev', 'state_helper': 'input_text.state', 'home_zone': 'zone.home',
            'alarm_sensor': 'sensor.alarm', 'awake_sensors': ['binary_sensor.awake'],
            'heated_areas': ['living_room'], 'proximity_devices': [],
        })
        self.inputs.update(inputs or {})
        self.bp = resolve(self.bp_raw, self.inputs)
        self.now = start or T(0, 0)
        self.states: dict[str, State] = {}
        self.devices = {'dev': []}
        self.device_names = {'dev': 'Thermostat'}
        self.areas = {'living_room': [], 'garden': []}
        self.integrations = {'proximity': []}
        self.schedules = schedules or DEFAULT_SCHEDULES
        self.log: list[str] = []
        self.runs: list[dict] = []
        self.reporting = reporting
        self.fresh_on_apply = fresh_on_apply
        self.timer_end = None
        self.room = dict(temp=room, rate=rate, lag=lag, loss=loss, heating=False, since=self.now,
                         rep=None, rep_t=None)
        self.trigger_state: dict[int, dict] = {}
        self.env = self._make_env()
        self._build_entities(group)

    # entities
    def set(self, entity_id, state, attributes=None, when=None, force_update=False):
        when = when or self.now
        state = str(state) if not isinstance(state, str) else state
        old = self.states.get(entity_id)
        if old is None:
            self.states[entity_id] = State(entity_id, state, attributes, when)
            return
        changed = old.state != state
        new_attrs = old.attributes if attributes is None else dict(attributes)
        if changed:
            old.last_changed = when
        if changed or new_attrs != old.attributes or force_update:
            old.last_updated = when
        old.state = state
        old.attributes = new_attrs

    def add(self, entity_id, state, attributes=None, device='dev', area=None):
        self.set(entity_id, state, attributes)
        if device:
            self.devices.setdefault(device, []).append(entity_id)
        if area:
            self.areas.setdefault(area, []).append(entity_id)

    def _build_entities(self, group):
        a = self.add
        a('select.t_schedule_group', group, {'options': list(SCHEDULE_GROUPS)})
        a('select.t_schedule_operating_day', self.now.strftime('%A'))
        a('button.t_schedule_fetch', 'unknown')
        for i in range(1, 13):
            a(f'select.t_schedule_period_{i}_time', 'NULL')
            a(f'number.t_schedule_period_{i}_temp', '5.0')
        a('select.t_override_mode', 'Boost', {'options': ['Boost', 'Timer']})
        a('number.t_override_target_temperature', '30.0')
        a('number.t_override_period', '30')
        a('button.t_override_apply', 'unknown')
        a('button.t_override_exit', 'unknown')
        a('sensor.t_override_mode', 'Idle')
        a('sensor.t_device_work_mode_state', 'Schedule')
        a('number.t_heating_high_threshold', '0.2')
        a('number.t_heating_low_threshold', '-0.6')
        a('sensor.t_hvac_action', 'idle')
        a('climate.t', 'heat', {'current_temperature': round(self.room['temp'], 1), 'temperature': None,
                               'hvac_action': 'idle'})
        a('input_text.state', '', {'max': 255}, device=None)
        a('zone.home', '1', {'friendly_name': 'Home'}, device=None)
        a('sensor.alarm', 'unknown', device=None)
        a('binary_sensor.awake', 'unknown', device=None)
        a('binary_sensor.living_room_occupancy', 'on', {'device_class': 'occupancy'}, device=None, area='living_room')
        a('binary_sensor.garden_occupancy', 'off', {'device_class': 'occupancy'}, device=None, area='garden')
        self.load_periods()
        self._report(force=True)
        self._update_climate()

    # thermostat
    def schedule_temp(self, group=None, when=None):
        when = when or self.now
        periods = self.schedules[group or self.states['select.t_schedule_group'].state]
        cur = periods[0][1]
        for hhmm, temp in periods:
            h, m = map(int, hhmm.split(':'))
            if (when.hour, when.minute) >= (h, m):
                cur = temp
        return cur

    def setpoint(self):
        if self.states['sensor.t_override_mode'].state in ('Timer', 'Boost'):
            return float(self.states['number.t_override_target_temperature'].state)
        return float(self.schedule_temp())

    def load_periods(self):
        """What a schedule fetch does: the active group's periods for the operating day."""
        periods = self.schedules[self.states['select.t_schedule_group'].state]
        for i in range(1, 13):
            if i <= len(periods):
                self.set(f'select.t_schedule_period_{i}_time', periods[i - 1][0])
                self.set(f'number.t_schedule_period_{i}_temp', f'{float(periods[i - 1][1]):.1f}')
            else:
                self.set(f'select.t_schedule_period_{i}_time', 'NULL')
                self.set(f'number.t_schedule_period_{i}_temp', '5.0')

    def _update_climate(self):
        st = self.states['climate.t']
        attrs = dict(st.attributes, temperature=self.setpoint(), hvac_action=self.states['sensor.t_hvac_action'].state)
        self.set('climate.t', 'heat', attrs)

    def _set_heating(self, on):
        r = self.room
        if r['heating'] != on:
            r['heating'], r['since'] = on, self.now
            self.set('sensor.t_hvac_action', 'heating' if on else 'idle')
            self._update_climate()

    def _report(self, force=False):
        r = self.room
        v = round(r['temp'] + 1e-9, 1)
        if force or not self.reporting or r['rep'] is None or abs(v - r['rep']) >= 0.3 - 1e-9 \
                or (self.now - r['rep_t']).total_seconds() >= 900:
            r['rep'], r['rep_t'] = v, self.now
            st = self.states['climate.t']
            self.set('climate.t', 'heat', dict(st.attributes, current_temperature=v), force_update=True)

    def control(self):
        """The thermostat's own hysteresis, by its own (unreported) reading."""
        sp = self.setpoint()
        hi = float(self.states['number.t_heating_high_threshold'].state)
        lo = float(self.states['number.t_heating_low_threshold'].state)
        t = self.room['temp']
        if not self.room['heating'] and t <= sp + lo + 1e-9:
            self._set_heating(True)
        elif self.room['heating'] and t >= sp + hi - 1e-9:
            self._set_heating(False)

    def physics_minute(self):
        r = self.room
        if r['heating']:
            if (self.now - r['since']).total_seconds() >= r['lag'] * 60:
                r['temp'] += r['rate'] / 60
        else:
            r['temp'] -= r['loss'] / 60

    def press(self, entity_id):
        self.set(entity_id, self.now.isoformat())
        if entity_id == 'button.t_schedule_fetch':
            self.load_periods()
        elif entity_id == 'button.t_override_apply':
            mode = self.states['select.t_override_mode'].state
            self.set('sensor.t_override_mode', mode)
            self.timer_end = self.now + dt.timedelta(minutes=float(self.states['number.t_override_period'].state))
            self._update_climate()
            if self.fresh_on_apply and not self.room['heating'] and self.room['temp'] < self.setpoint() - 1e-9:
                self._set_heating(True)
        elif entity_id == 'button.t_override_exit':
            if self.states['sensor.t_override_mode'].state != 'Idle':
                self.set('sensor.t_override_mode', 'Idle')
                self.timer_end = None
                self._update_climate()

    # template environment
    def _make_env(self):
        env = Environment(extensions=['jinja2.ext.loopcontrols'])
        w = self

        def fl(v, default=Undefined):
            try:
                return float(v)
            except (TypeError, ValueError):
                if isinstance(default, type) and default is Undefined:
                    raise ValueError(f'float got {v!r}')
                return default

        def it(v, default=Undefined, base=10):
            try:
                return int(float(v)) if not isinstance(v, str) or '.' in v or 'e' in v.lower() else int(v, base)
            except (TypeError, ValueError):
                if isinstance(default, type) and default is Undefined:
                    raise ValueError(f'int got {v!r}')
                return default

        def as_dt(v, default=Undefined):
            if isinstance(v, dt.datetime):
                return v
            try:
                d = dt.datetime.fromisoformat(str(v))
                return d if d.tzinfo else d.replace(tzinfo=TZ)
            except (TypeError, ValueError):
                if isinstance(default, type) and default is Undefined:
                    raise ValueError(f'as_datetime got {v!r}')
                return default

        def as_ts(v, default=Undefined):
            if isinstance(v, dt.datetime):
                return v.timestamp()
            d = as_dt(v, None)
            if d is None:
                if isinstance(default, type) and default is Undefined:
                    raise ValueError(f'as_timestamp got {v!r}')
                return default
            return d.timestamp()

        def ts_custom(v, fmt='%Y-%m-%d %H:%M:%S', local=True, default=Undefined):
            try:
                d = dt.datetime.fromtimestamp(float(v), TZ if local else dt.timezone.utc)
            except (TypeError, ValueError):
                return default
            return d.strftime(fmt)

        def from_json(v, default=Undefined):
            try:
                return json.loads(v)
            except Exception:
                if isinstance(default, type) and default is Undefined:
                    raise
                return default

        def rnd(v, precision=0, method='common', default=Undefined):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return default
            if method == 'ceil':
                return math.ceil(v * 10 ** precision) / 10 ** precision
            if method == 'floor':
                return math.floor(v * 10 ** precision) / 10 ** precision
            out = round(v, precision)
            return int(out) if precision == 0 else out

        def as_timedelta(v):
            h, m, s = (float(x) for x in str(v).split(':'))
            return dt.timedelta(hours=h, minutes=m, seconds=s)

        class States:
            def __call__(self, e):
                st = w.states.get(e)
                return st.state if st else 'unknown'

            def __getitem__(self, e):
                return w.states.get(e)

            def __getattr__(self, domain):
                return SimpleNamespace(**{k.split('.', 1)[1]: v for k, v in w.states.items() if k.startswith(domain + '.')})

        def state_attr(e, a):
            st = w.states.get(e)
            return st.attributes.get(a) if st else None

        def is_state(e, v):
            st = w.states.get(e)
            return st is not None and (st.state in v if isinstance(v, list) else st.state == v)

        def is_state_attr(e, a, v):
            return state_attr(e, a) == v

        def has_value(e):
            st = w.states.get(e)
            return st is not None and st.state not in ('unknown', 'unavailable')

        def expand(*args):
            out = []
            for a in args:
                for e in ([a] if isinstance(a, str) else a):
                    if isinstance(e, State):
                        out.append(e)
                    elif e in w.states:
                        out.append(w.states[e])
            return sorted(out, key=lambda s: s.entity_id)

        def entity_name(e):
            st = w.states.get(e)
            return st.attributes.get('friendly_name', e) if st else None

        def device_attr(dev, attr):
            if attr == 'name':
                for d, ents in w.devices.items():
                    if dev == d or dev in ents:
                        return w.device_names.get(d)
            return None

        def flatten(v, levels=None):
            out = []
            for x in v:
                out.extend(flatten(x) if isinstance(x, (list, tuple)) else [x])
            return out

        def today_at(s='00:00'):
            h, m = map(int, s[:5].split(':'))
            return w.now.replace(hour=h, minute=m, second=0, microsecond=0)

        g = env.globals
        g.update(states=States(), state_attr=state_attr, is_state=is_state, is_state_attr=is_state_attr,
                 has_value=has_value, expand=expand, entity_name=entity_name,
                 device_entities=lambda d: list(w.devices.get(d, [])), device_attr=device_attr,
                 integration_entities=lambda i: list(w.integrations.get(i, [])),
                 areas=lambda: list(w.areas), area_entities=lambda a: list(w.areas.get(a, [])),
                 now=lambda: w.now, today_at=today_at, timedelta=dt.timedelta, as_datetime=as_dt,
                 as_timestamp=as_ts, as_timedelta=as_timedelta, float=fl, int=it, min=min, max=max,
                 dict=dict, range=range)
        f = env.filters
        f.update(float=fl, int=it, as_datetime=as_dt, as_local=lambda d: d.astimezone(TZ), as_timestamp=as_ts,
                 timestamp_custom=ts_custom, from_json=from_json, to_json=lambda v: json.dumps(v, separators=(',', ':')),
                 round=rnd, flatten=flatten, bool=lambda v, default=None: str(v).lower() in ('1', 'true', 'on', 'yes'),
                 area_entities=lambda a: list(w.areas.get(a, [])), entity_name=entity_name,
                 is_state=is_state, has_value=has_value)
        t = env.tests
        t.update(match=lambda s, p: isinstance(s, str) and re.match(p, s) is not None,
                 search=lambda s, p: isinstance(s, str) and re.search(p, s) is not None,
                 contains=lambda s, v: v in s, is_state=is_state, has_value=has_value,
                 is_state_attr=is_state_attr, list=lambda v: isinstance(v, list))
        env._cache = {}
        return env

    def render(self, template, ctx):
        if not isinstance(template, str):
            return template
        if '{' not in template:
            return template
        tpl = self.env._cache.get(template)
        if tpl is None:
            tpl = self.env._cache[template] = self.env.from_string(template)
        return native(tpl.render(**ctx))

    def render_data(self, obj, ctx):
        if isinstance(obj, str):
            return self.render(obj, ctx)
        if isinstance(obj, dict):
            return {k: self.render_data(v, ctx) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.render_data(v, ctx) for v in obj]
        return obj

    # running the automation
    def trigger_variables(self):
        ctx = {}
        for k, v in self.bp['trigger_variables'].items():
            ctx[k] = self.render(v, ctx) if isinstance(v, str) else v
        return ctx

    def run(self, trigger_id, label=''):
        """Run the automation once for the given trigger id."""
        ctx = self.trigger_variables()
        ctx['trigger'] = {'id': trigger_id, 'platform': 'sim'}
        for k, v in self.bp['variables'].items():
            ctx[k] = self.render_data(v, ctx)
        start = len(self.log)
        result = 'done'
        try:
            for c in self.bp.get('conditions') or []:
                if not self._cond(c, ctx):
                    raise Stop('condition')
            self._seq(self.bp['actions'], ctx)
        except Stop as e:
            result = ('error: ' if e.error else 'stopped: ') + str(e)
        run = {'time': self.now, 'id': trigger_id, 'label': label, 'result': result, 'calls': self.log[start:],
               'ctx': ctx}
        self.runs.append(run)
        return run

    def _cond(self, c, ctx):
        kind = c.get('condition')
        if kind == 'template':
            return bool(self.render(c['value_template'], ctx))
        if kind == 'or':
            return any(self._cond(x, ctx) for x in c['conditions'])
        if kind == 'and':
            return all(self._cond(x, ctx) for x in c['conditions'])
        if kind in ('occupancy.is_detected', 'occupancy.is_not_detected'):
            areas = c['target']['area_id']
            ents = [e for a in areas for e in self.areas.get(a, []) if self._is_occupancy(e)]
            hold = duration_seconds((c.get('options') or {}).get('for'))
            on = [e for e in ents if self.states[e].state == 'on'
                  and (self.now - self.states[e].last_changed).total_seconds() >= hold]
            off = [e for e in ents if self.states[e].state == 'off'
                   and (self.now - self.states[e].last_changed).total_seconds() >= hold]
            behavior = (c.get('options') or {}).get('behavior', 'any')
            if kind == 'occupancy.is_detected':
                return bool(on) if behavior == 'any' else bool(ents) and len(on) == len(ents)
            return bool(ents) and len(off) == len(ents) if behavior == 'all' else bool(off)
        raise ValueError(f'condition {kind}')

    def _is_occupancy(self, e):
        st = self.states.get(e)
        return st is not None and e.startswith('binary_sensor.') and st.attributes.get('device_class') == 'occupancy'

    def _seq(self, steps, ctx):
        for s in steps:
            keys = [k for k in s if k not in ('alias', 'enabled', 'continue_on_error')]
            if 'variables' in s and keys == ['variables']:
                for k, v in s['variables'].items():
                    ctx[k] = self.render_data(v, ctx)
            elif 'if' in s:
                if all(self._cond(c, ctx) for c in s['if']):
                    self._seq(s['then'], ctx)
                elif 'else' in s:
                    self._seq(s['else'], ctx)
            elif 'choose' in s:
                for option in s['choose']:
                    if all(self._cond(c, ctx) for c in option['conditions']):
                        if 'variables' in option:
                            for k, v in option['variables'].items():
                                ctx[k] = self.render_data(v, ctx)
                        self._seq(option['sequence'], ctx)
                        break
                else:
                    if 'default' in s:
                        self._seq(s['default'], ctx)
            elif 'condition' in s:
                if not self._cond(s, ctx):
                    raise Stop('condition')
            elif 'stop' in s:
                raise Stop(self.render(s['stop'], ctx), bool(s.get('error')))
            elif 'sequence' in s:
                if 'variables' in s:
                    for k, v in s['variables'].items():
                        ctx[k] = self.render_data(v, ctx)
                self._seq(s['sequence'], ctx)
            elif 'action' in s:
                target = self.render_data(s.get('target', {}), ctx)
                data = self.render_data(s.get('data', {}), ctx)
                self.call(s['action'], target, data)
            elif 'wait_template' in s:
                pass  # the simulated thermostat answers at once
            else:
                raise ValueError(f'step {s}')

    def call(self, action, target, data):
        e = target.get('entity_id') if target else None
        e = e[0] if isinstance(e, list) else e
        self.log.append(f"{self.now:%H:%M} {action} {e} {json.dumps(data) if data else ''}".rstrip())
        domain, service = action.split('.')
        if action == 'input_text.set_value':
            v = data['value']
            v = json.dumps(v, separators=(',', ':')) if isinstance(v, (dict, list)) else str(v)
            if len(v) > int(self.states[e].attributes.get('max', 255)):
                raise Stop(f'{e} value longer than its maximum', True)
            self.set(e, v)
        elif action == 'select.select_option':
            self.set(e, data['option'])
            if e == 'select.t_schedule_group':
                self._update_climate()
        elif action == 'number.set_value':
            self.set(e, str(data['value']))
        elif action == 'button.press':
            self.press(e)
        else:
            raise ValueError(action)

    # triggers
    def _trigger_true(self, i, t, tv):
        kind = t['trigger']
        if kind == 'template':
            return bool(self.render(t['value_template'], tv))
        if kind in ('occupancy.detected', 'occupancy.cleared'):
            ents = [e for a in t['target']['area_id'] for e in self.areas.get(a, []) if self._is_occupancy(e)]
            behavior = (t.get('options') or {}).get('behavior', 'any')
            on = [e for e in ents if self.states[e].state == 'on']
            if kind == 'occupancy.detected':
                return bool(on) if behavior in ('any', 'first') else bool(ents) and len(on) == len(ents)
            return bool(ents) and not on
        if kind in ('zone.occupancy_detected', 'zone.occupancy_cleared'):
            n = int(float(self.states['zone.home'].state or 0))
            return n > 0 if kind == 'zone.occupancy_detected' else n == 0
        if kind == 'time':
            h, m, s = (int(x) for x in t['at'].split(':'))
            return (self.now.hour, self.now.minute) == (h, m)
        return False

    def check_triggers(self, fire=True):
        """Evaluate the triggers; run the automation for each that turned true
        (and stayed true for its 'for'). Repeats after runs, as Home Assistant
        re-renders template triggers when what they read changes."""
        for _ in range(10):
            tv = self.trigger_variables()
            fired = []
            for i, t in enumerate(self.bp['triggers']):
                if t['trigger'] in ('homeassistant', 'event'):
                    continue
                st = self.trigger_state.setdefault(i, {'value': None, 'since': None, 'done': False})
                v = self._trigger_true(i, t, tv)
                hold = duration_seconds(t.get('for') if 'for' in t else (t.get('options') or {}).get('for'))
                if v and not st['value']:
                    st.update(value=True, since=self.now, done=False)
                elif not v:
                    st.update(value=False, since=None, done=False)
                if v and not st['done'] and (self.now - st['since']).total_seconds() >= hold:
                    st['done'] = True
                    if fire and st['since'] is not None:
                        fired.append(t.get('id') or str(i))
            if not fired:
                return
            for tid in fired:
                self.run(tid)

    def prime(self):
        """Take the triggers' current values without firing, as at startup."""
        self.check_triggers(fire=False)
        for st in self.trigger_state.values():
            if st['value']:
                st['done'] = True

    def advance(self, until, step=60, on_minute=None):
        """Advance time to `until`, a minute at a time: room physics, the
        thermostat's control and reports, its Timer, then the triggers."""
        while self.now < until:
            self.now = min(self.now + dt.timedelta(seconds=step), until)
            if self.timer_end and self.now >= self.timer_end:
                self.timer_end = None
                self.set('sensor.t_override_mode', 'Idle')
                self._update_climate()
            self.physics_minute()
            self.control()
            self._report()
            self._update_climate()
            if on_minute:
                on_minute(self)
            self.check_triggers()

    # convenience
    def helper(self):
        raw = self.states['input_text.state'].state
        return json.loads(raw) if raw.startswith('{') else {}

    def learned(self):
        return self.helper().get('l', {}).get('v')

    def measuring(self):
        return self.helper().get('l', {}).get('m')

    def plan(self):
        return self.helper().get('r', {})

    def group(self):
        return self.states['select.t_schedule_group'].state

    def override(self):
        return self.states['sensor.t_override_mode'].state

    def set_alarm(self, when):
        self.set('sensor.alarm', when.isoformat() if when else 'unknown')

    def set_occupied(self, area, on):
        e = f'binary_sensor.{area}_occupancy'
        self.set(e, 'on' if on else 'off')

    def set_room(self, temp):
        self.room['temp'] = temp
        self._report(force=True)
        self._update_climate()

    def add_person(self, name, distance_m=0, direction='arrived', device='prox'):
        self.device_names.setdefault(device, 'Home')
        for k, v, attrs in ((f'sensor.home_{name}_distance', distance_m, {'unit_of_measurement': 'm'}),
                            (f'sensor.home_{name}_direction_of_travel', direction, {})):
            self.add(k, v, attrs, device=device)
            self.integrations['proximity'].append(k)

    def move(self, name, distance_m, direction):
        self.set(f'sensor.home_{name}_distance', str(distance_m))
        self.set(f'sensor.home_{name}_direction_of_travel', direction)
