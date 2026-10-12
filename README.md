# Home Assistant Blueprints

Blueprints I've created for my own personal use, support is not guaranteed.

## Sonoff TP-WGZBA smart schedule

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjeverley%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsonoff_tp_wgzba_smart_schedule.yaml)

File: [`blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml`](blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml). Requires Home Assistant 2026.10.0 or later.

Built for Sonoff TP-WGZBA Zigbee thermostats on ZHA. Create one automation per thermostat (zone) and pick the thermostat device. The blueprint finds the device's schedule and override entities itself. Each automation also needs its own **Text helper** for its working state: create one under **Settings** > **Devices & services** > **Helpers** > **Create helper** > **Text**, set its **Maximum length** to 255, and pick it as the **State helper**.

### What it does

- **Occupancy:** switches the thermostat's active schedule group using the native occupancy and zone triggers and conditions.
  - Schedule 1 when the heated areas are occupied.
  - Schedule 2 when the heated areas are empty.
  - Schedules 1 and 2 leave your own Boost or Timer override alone, and switch once it ends. The routine's own Timers (the routine pressed Apply last) don't hold up a switch. Their stage is worked out again from the new group's schedule and the Timer replaced.
  - With **Follow occupancy** turned off, or no heated areas set, Schedule 1 is used whenever someone is home, for areas you want on their occupied schedule all day.
- **Geofencing:**
  - **Away schedule:** Schedule 3 when nobody is home (the home zone is empty and no area is occupied). Any running override is ended first. When off, the group follows Occupancy while nobody is home, and only the routine's own Timer is ended.
  - **Pre-heat:** while nobody is home, once someone heading home is within the geofencing distance, it switches to the pre-heat group (Schedule 2 by default) so the house warms before they arrive. It needs the away schedule. See [Geofencing](#geofencing) below.
- **Routine:** moves the start of the morning heating to match the next waking alarm. The wake-up start is the alarm minus the lead time. Early, late, wake and catch-up runs (and a refresh just after midnight) fetch today's schedule for the active group from the thermostat and counts the configured periods (period 1 is fixed at 00:00, and counting stops at the first unset period).
  - **Early alarm** (wake-up start before period 2): today's morning starts early, at the schedule's own temperatures.

    | Configured periods | Typical schedule | What happens |
    | --- | --- | --- |
    | 1 | Period 1 all day | Nothing to start early, so nothing happens |
    | 2 or 3 | Night, day (and evening setback) | Period 2 starts early and runs until its usual start, so period 3 (the evening setback) is never pulled into the morning |
    | 4 or more | Night, morning, daytime, ... | The morning shifts earlier. Period 2 runs for its usual length from the early start, then period 3 runs until its usual start, when the device schedule carries on |

  - **Late alarm** (wake-up start after period 2): just before period 2's usual start, period 1's temperature is held until the wake-up start. With 2 or 3 periods, the device schedule then carries on with period 2. With 4 or more, period 2 then runs for its usual length (never past period 4), so period 3 starts later and later periods keep their usual times.

  - **Someone up early:** when the awake sensor turns on (and stays on for the **Getting up delay**, if set), the wake-up starts now, as if the alarm were early. With no alarm set, this still starts the morning early. During a late hold, it ends the hold and, with 4 or more periods, runs period 2 for its usual length from now. Leave the awake sensors empty to only follow the alarm.
  - **Bedtime:** when the awake sensor has been off for the **Bedtime delay** during the period just before the evening setback (the last period with 3 or more periods, or period 1 again at midnight with 2), the setback starts early as a Timer at its temperature until its usual start. If someone gets up again before then, the Timer ends. Bedtime checks the home zone rather than the areas, since people asleep may not show on occupancy sensors.
  - Each of these (early alarm, late alarm, wake-up and bedtime) has its own toggle.

  Each stage is a Timer override on the thermostat, so it keeps running if Home Assistant restarts.
- **Skips:** alarm-based changes only happen when the alarm is today; a wake-up works with no alarm or a later one. The wake-up is skipped when period 2 is not warmer than period 1, when a schedule temperature cannot be read, when an override is already running, or when nobody is in any area.
- **Catch up:** a catch-up run re-checks everything (schedule group, then the routine) when Home Assistant starts, when automations reload, 5 minutes after the schedule was last edited, or when you press **Run actions**. When the blueprint changes the schedule group, it plans the routine again for the new group's periods if a routine is running, today's alarm is still ahead or someone is up. A change made by hand is picked up by the next run that plans the routine. Anything deferred or missed is applied then.
- **Resilience:** runs in queued mode (max 25, silent) and never waits on people, so runs finish in seconds. It saves its state to the State helper before any thermostat call that depends on it, so if the thermostat is not answering, the run stops with the error in its trace instead of acting on a schedule it could not read or a half-applied Timer, and the next run picks up from the saved plan. When the schedule group select recovers from `unavailable` or `unknown`, a catch-up runs. It stops with an error in the trace if the device is missing an expected entity or one is disabled. A 30 second wait after ending or applying an override lets the thermostat report its new state, and a Timer is only replaced once ours has ended.

#### Example (4 periods)

Schedule 00:00 16 °C, 06:30 21 °C, 08:00 18 °C, 22:00 16 °C, lead 30 minutes.

| Time | Usual schedule | Alarm 05:30 (early) | Alarm 09:00 (late) |
| --- | --- | --- | --- |
| 05:00 to 06:30 | 16 °C | 21 °C | 16 °C |
| 06:30 to 08:00 | 21 °C | 18 °C | 16 °C (held) |
| 08:00 to 08:30 | 18 °C | 18 °C | 16 °C (held) |
| 08:30 to 10:00 | 18 °C | 18 °C | 21 °C (period 2, its usual 90 minutes) |
| From 10:00 | 18 °C | 18 °C | 18 °C |

### Inputs

| Section | Inputs |
| --- | --- |
| Thermostat | the TP-WGZBA device, state helper (required) |
| Occupancy | follow occupancy (on), heated areas (none), occupied delay (1 min), empty delay (5 min) |
| Geofencing | away schedule (on), home zone (default `zone.home`), pre-heat (on), geofencing distance (5 km), pre-heat schedule group (Schedule 2), geofencing timeout (30 min), Proximity devices (found from the home zone), arriving sensors (none) |
| Routine | next waking alarm sensor (optional, none), lead time (30 min), early alarm (on), late alarm (on), awake sensors (none), getting up (on), getting up delay (0), bedtime (on), bedtime delay (15 min) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Heated areas | Bedroom | Living room |
| Lead time | 30 min | 10 min |
| Awake sensors | Someone up helper | Someone up helper |
| Bedtime | Off | On |
| Pre-heat schedule group | Schedule 2 | Schedule 1 |

Temperatures come from each thermostat's own schedule, so set the morning periods on the device.

### Awake sensors

Any binary sensor or input boolean that is **on while anyone is up**, **off once everyone is asleep**, and **unknown** (or unavailable) when it can't tell. Only an explicit `on` or `off` counts, so unknown never starts the morning or bedtime. It drives both ends of the day:
- Turning on (held for the **Getting up delay**, if set) means someone is up, when **Getting up** is on.
- Turning off (held for the **Bedtime delay**, 15 minutes by default) is bedtime, when **Bedtime** is on. If it turns on again before the usual setback time, the early setback ends.

Each automation uses it only for its own thermostat, so you can turn getting up or bedtime off for a bedroom and keep them for a living room.

The sensor has to tell real getting up from a trip to the bathroom, and real bedtime from a quiet afternoon, by itself. The blueprint has no time window of its own. Motion sensors alone are a poor signal, so build a helper that smooths them out. Both of these can be set up in the UI under **Settings** > **Devices & services** > **Helpers**:

- **Time active in a window (most robust):**
  1. A **Group** (binary sensor) of your home's motion sensors.
  2. A **History stats** sensor on the group: type **time**, state `on`, start `{{ now() - timedelta(minutes=15) }}`, end `{{ now() }}`.
  3. A **Threshold** sensor on the history stats: upper limit 0.08 hours (5 minutes), with a small hysteresis.

  This turns on after about 5 minutes of motion within 15 minutes, wherever it happens, and off about 15 minutes after the house goes quiet. Pauses and moving between rooms only lower the total, and a short bathroom trip stays under the limit. Use it with a **Getting up delay** of zero.
- **Motion held through short pauses (simpler):** a **Template** binary sensor that is on while any motion sensor in the group is on, with **Delay off** set to about 2 minutes. Use it with a **Getting up delay** of around 10 minutes and a longer **Bedtime delay**.

A quiet evening on the sofa can look like everyone asleep to motion sensors. Keep the sensor on while there are other signs of people up, for example by grouping the motion helper with the TV or the living room lights (a **Group** with **All entities** off, so it is on when any member is on), or use a **Bayesian** sensor that combines motion with signals such as phones charging or bedroom lights.

To limit it to the hours when getting up or going to bed is plausible, wrap it in a **Template** binary sensor that is unknown at other times, by returning `none`. For example, to ignore the middle of the night and the daytime:

```jinja
{% set h = now().hour %}
{% if 5 <= h < 11 or h >= 19 or h < 1 %}
  {{ is_state('binary_sensor.someone_moving', 'on') }}
{% else %}
  {{ none }}
{% endif %}
```

A 03:00 trip to the bathroom then does not start the morning, and a quiet afternoon does not start bedtime. When it becomes known again, an `off` still has to last the **Bedtime delay**.

### Geofencing

Geofencing uses the built-in **Proximity** integration. Add it under **Settings** > **Devices & services** > **Add integration** > **Proximity**: track the home zone, add the household's people (they need a location from GPS, such as the companion app), ignore zones like Work if you want, and set a tolerance of 50 to 100 m to steady the direction of travel.

The blueprint finds that Proximity entry by its name, which defaults to the home zone's name, and reads each person's distance and direction of travel sensors. Someone counts as heading home when they are within the geofencing distance and moving `towards` home. If the entry has been renamed, or the zone has, pick it under **Proximity devices**. Distances are converted from Proximity's unit (metres, kilometres or miles).

While nobody is home, someone heading home switches the thermostat to the pre-heat group and records the time in the State helper. Pre-heating carries on until someone gets home, even if they stop on the way, or until the geofencing timeout passes, when it goes back to Schedule 3. If someone is still shown heading home then, it pre-heats again only once they stop and set off again, so a stuck reading cannot keep the house warm. Turn off **Pre-heat** to stop it.

**Arriving sensors** (binary sensors or toggles) count as well as Proximity, for example a template helper that is on when a Waze or Google travel time to home is under 15 minutes.

### Requirements and caveats

- The thermostat's **Device work mode** must be **Schedule** for the schedule groups and the routine to have any effect. Setting it to **Manual** or **Off** pauses the routine until it is set back to Schedule. Choosing the **Heat** HVAC mode on the climate entity (in the climate card or an automation) also sets it to Manual, while changing the target temperature only holds until the next period.
- Needs ZHA support for the TP-WGZBA schedule and override entities, added in [zigpy/zha-device-handlers PR #5201](https://github.com/zigpy/zha-device-handlers/pull/5201). Entities are matched by their default entity ID endings (for example `select.*_schedule_group`, `sensor.*_override_mode`, `sensor.*_device_work_mode_state`, `select.*_schedule_period_2_time`), so keep those. Renaming the device part is fine.
- The option strings (`Schedule 1/2/3`, `Boost`, `Timer`, `Idle` and the day names) and entity types come from that ZHA support.
- The Device work mode must be Schedule for the on-device schedule to apply. The blueprint does not check it.
- If the wake-up start falls before midnight (an alarm just after 00:00), the wake-up is skipped, because the fetched schedule would be for the wrong day.
- The routine's plan in the State helper records intent rather than temperatures: its kind (`morning` or `bedtime`), its start, and the Timer it last applied (`timer_until`, when it should end, `timer_temp`, its temperature, and `timer_applied`, when it pressed the override Apply button). A Timer or Boost only starts from Apply, so the running override is the routine's only while Apply was last pressed by the routine. Changing the target or period without applying does not change that. A plan only counts on its own day. Each run that plans the routine works out the current stage from that and today's periods for the active group, so follow-on stages (period 3 after an early start, period 2 after a late hold), restarts and group changes all use the same rule. A stage needs at least a minute. The routine steps aside whenever you take control, and carries on from its plan afterwards:
  - **Your own Timer or Boost** (you press Apply): left alone, and the routine carries on once it ends.
  - **A temperature change from the climate control or on the thermostat:** its **Device work mode state** shows `Temporary_Manual` until the next period, and the routine applies nothing until it is back on `Schedule`.
  - **Device work mode set to Manual or Off:** the state shows `Manual` or `Off`, and the routine applies nothing until **Device work mode** is set back to Schedule.
  - **The thermostat restarting or dropping off:** the routine puts its Timer back on the next run.
  - **Pressing Exit on the routine's Timer** is the one way to cancel it: that routine does not start again the same day. Nobody home drops the plan. The helper holds JSON with one key per feature, so it is not specific to the routine.
- Without an awake sensor, anyone up during a late hold stays at period 1's temperature until the wake-up start. With one, the morning starts when it reports someone up.
- Someone counts as home when the home zone is occupied or any area's occupancy sensor is on, even one in the garden. The wake-up needs someone in any area, so a downstairs thermostat heats while people are still in bed upstairs. It cannot be limited to one room, so a spare bedroom thermostat sharing the same alarm sensor would also heat whenever someone is home.
- Occupancy for areas uses occupancy sensors (device class `occupancy`) only. For an area with only a motion sensor, create an occupancy sensor from it, for example a template binary sensor with a delay off.
- The trigger ids `early-alarm`, `late-alarm`, `getting-up`, `bedtime`, `override-ended`, `catch-up`, `new-day`, `heading-home` and `geofencing-timeout` are fixed because the actions depend on them.

- Fetching the schedule selects today in the thermostat's **Schedule operating day** select, which replaces whatever day is shown for editing. So while the schedule is being edited (operating day or period entities changed in the last 5 minutes, other than by the blueprint's own fetch, and not as a burst), every run is deferred, with a note in its trace: no fetch, no routine stage and no schedule group change. A catch-up runs 5 minutes after the last change and picks the routine up from its plan. In the meantime a running Timer carries on, and if one ends the thermostat follows its own schedule. A restart, a device rejoining or another fetch changes half or more of them within 30 seconds, so it does not count as editing. Unapplied edits left untouched for more than 5 minutes can be replaced by the next fetch.

### Known issue

On firmware 0x00001004 the thermostat setpoint can drop to 5 °C at 00:00 each night under the on-device schedule, even with a 16 °C period at 00:00. This is a firmware issue, also reported in [Koenkk/zigbee2mqtt#33317](https://github.com/Koenkk/zigbee2mqtt/issues/33317). Raising the Frost proof temperature might mitigate it, but this is unconfirmed and still to be tested.
