# Home Assistant Blueprints

Blueprints I've created for my own personal use, support is not guaranteed.

## Sonoff TP-WGZBA smart schedule

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjeverley%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsonoff_tp_wgzba_smart_schedule.yaml)

File: [`blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml`](blueprints/automation/sonoff_tp_wgzba_smart_schedule.yaml). Requires Home Assistant 2026.10.0 or later.

Built for Sonoff TP-WGZBA Zigbee thermostats on ZHA. Create one automation per thermostat (zone) and pick the thermostat device. The blueprint finds the device's schedule and override entities itself.

### What it does

- **Occupancy:** switches the thermostat's active schedule group using the native occupancy and zone triggers and conditions.
  - Schedule 1 when the heated areas are occupied.
  - Schedule 2 when the heated areas are empty. A running Boost or Timer override is left alone.
  - Schedule 3 when nobody is home (the home zone is empty and every home area is clear). Any running override is ended first.
- **Routine:** moves the start of the morning heating to match the next waking alarm. The routine start is the alarm minus the lead time. Routine runs (and a refresh just after midnight) fetch today's schedule for the active group from the thermostat and counts the configured periods (period 1 is fixed at 00:00, and counting stops at the first unset period).
  - **Early alarm** (routine start before period 2): today's morning starts early, at the schedule's own temperatures.

    | Configured periods | Typical schedule | What happens |
    | --- | --- | --- |
    | 1 | Period 1 all day | Nothing to start early, so nothing happens |
    | 2 or 3 | Night, day (and evening setback) | Period 2 starts early and runs until its usual start, so period 3 (the evening setback) is never pulled into the morning |
    | 4 or more | Night, morning, daytime, ... | The morning shifts earlier. Period 2 runs for its usual length from the early start, then period 3 runs until its usual start, when the device schedule carries on |

  - **Late alarm** (routine start after period 2): just before period 2's usual start, period 1's temperature is held until the routine start. With 2 or 3 periods, the device schedule then carries on with period 2. With 4 or more, period 2 then runs for its usual length (never past period 4), so period 3 starts later and later periods keep their usual times.

  - **Someone up early:** when the wake sensor turns on (and stays on for the wake duration, if set), the routine starts now, as if the alarm were early. With no alarm set, this still starts the morning early. During a late hold, it ends the hold and, with 4 or more periods, runs period 2 for its usual length from now. Leave the wake sensor empty to only follow the alarm.

  Each stage is a Timer override on the thermostat, so it keeps running if Home Assistant restarts.
- **Skips:** alarm-based changes only happen when the alarm is today; a wake-up works with no alarm or a later one. The routine is skipped when period 2 is not warmer than period 1, when a schedule temperature cannot be read, when an override is already running, or when nobody is in the home areas.
- **Catch up:** the early and late windows are checked again when Home Assistant starts and when automations reload, so a restart inside either window still applies it.
- **Resilience:** runs in queued mode (max 10, silent), re-applies the schedule group when its select recovers from `unavailable` or `unknown`, and stops with an error in the trace if the device is missing an expected entity. Fetch errors are tolerated: if the thermostat is not answering, any stage applied from older data fails too, and schedule group switching still runs. A 30 second wait after ending or applying an override lets the thermostat report its new state.

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
| Thermostat | the TP-WGZBA device |
| Occupancy | heated areas, home areas, home zone (default `zone.home`), occupied delay (1 min), empty delay (5 min) |
| Routine | next alarm sensor, lead time (30 min), wake sensor (none), wake duration (0) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Heated areas | Bedroom | Living room |
| Home areas | Every area | Every area |
| Lead time | 30 min | 10 min |
| Wake sensor | None (follows the alarm only) | Someone up helper |

Temperatures come from each thermostat's own schedule, so set the morning periods on the device.

### Wake sensor

Any binary sensor or input boolean that turns on when someone is up. A wake-up starts heating only in that automation's thermostat, so a bedroom automation with no wake sensor keeps following the alarm while a downstairs one starts when someone is up.

Motion sensors alone are a poor signal: they have gaps as you move between rooms, and a restless sleeper or a trip to the bathroom can look like getting up. Build a helper that smooths this out. Both of these can be set up in the UI under **Settings** > **Devices & services** > **Helpers**:

- **Time active in a window (most robust):**
  1. A **Group** (binary sensor) of your home's motion sensors.
  2. A **History stats** sensor on the group: type **time**, state `on`, start `{{ now() - timedelta(minutes=15) }}`, end `{{ now() }}`.
  3. A **Threshold** sensor on the history stats: upper limit 0.08 hours (5 minutes), with a small hysteresis.

  This turns on after about 5 minutes of motion within 15 minutes, wherever it happens. Pauses and moving between rooms only lower the total, and a short bathroom trip stays under the limit. Use this as the wake sensor with the wake duration at zero.
- **Motion held through short pauses (simpler):** a **Template** binary sensor that is on while any motion sensor in the group is on, with **Delay off** set to about 2 minutes. Use it with a wake duration of around 10 minutes.

A Bayesian sensor that combines motion with other signals (a phone coming off charge, a bedroom light) also works.

**Limit the wake sensor to morning hours.** The blueprint has no time window of its own, so a wake sensor that turns on at night (a trip to the bathroom, say) starts the morning heating hours early. To limit it, add a **Times of the Day** helper (for example 05:00 to 11:00), then put it and your activity sensor in a **Group** with **All entities** turned on, so the group is on only when both are. Use the group as the wake sensor.

### Requirements and caveats

- Needs ZHA support for the TP-WGZBA schedule and override entities, added in [zigpy/zha-device-handlers PR #5201](https://github.com/zigpy/zha-device-handlers/pull/5201). Entities are matched by their default entity ID endings (for example `select.*_schedule_group`, `sensor.*_override_mode`, `select.*_schedule_period_2_time`), so keep those. Renaming the device part is fine.
- The option strings (`Schedule 1/2/3`, `Boost`, `Timer`, `Idle` and the day names) and entity types come from that ZHA support.
- The Device work mode must be Schedule for the on-device schedule to apply. The blueprint does not check it.
- If the routine start falls before midnight (an alarm just after 00:00), the routine is skipped, because the fetched schedule would be for the wrong day.
- With 4 or more periods, the follow-on stages (period 3 after an early start, period 2 after a late hold) only run when the Timer that ended was the routine's own. After an early start, it must have had period 2's temperature and run for the override period that an automation (not a person in the UI) set, within 2 minutes. After a late hold, it must have had period 1's temperature and ended at the alarm start, within 2 minutes. If Home Assistant is down when a stage ends, its follow-on does not run and the device carries on with its normal schedule.
- During a late hold and its period 2 stage, schedule group switching for the heated areas waits until they end. Without a wake sensor, anyone up before the routine start stays at period 1's temperature. With one, the hold ends when it reports someone up.
- Heated areas and home areas are both required. If either is empty, the automation stops with an error.
- The routine needs someone anywhere in the home areas, so a downstairs thermostat heats while people are still in bed upstairs. It cannot be limited to one room, so a spare bedroom thermostat sharing the same alarm sensor would also heat whenever someone is home.
- Occupancy for the heated and home areas uses occupancy sensors (device class `occupancy`) only. For an area with only a motion sensor, create an occupancy sensor from it, for example a template binary sensor with a delay off.
- The trigger ids `prewarm`, `late-hold`, `wake`, `override-ended`, `catch-up` and `new-day` are fixed because the actions depend on them.

- Fetching the schedule selects today in the thermostat's **Schedule operating day** select, which replaces whatever day is shown for editing. The blueprint only fetches on routine runs, just after midnight, and after it switches schedule group while a late alarm is still ahead. A routine run only fetches once nobody has changed the operating day or a period in the UI for 5 minutes, waiting if needed. After 10 minutes of waiting the run stops with an error in its trace, without fetching or changing anything. Unapplied edits left untouched for longer than 5 minutes can be replaced by the next fetch.

### Known issue

On firmware 0x00001004 the thermostat setpoint can drop to 5 °C at 00:00 each night under the on-device schedule, even with a 16 °C period at 00:00. This is a firmware issue, also reported in [Koenkk/zigbee2mqtt#33317](https://github.com/Koenkk/zigbee2mqtt/issues/33317). Raising the Frost proof temperature might mitigate it, but this is unconfirmed and still to be tested.
