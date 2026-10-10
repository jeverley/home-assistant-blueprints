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
- **Routine:** moves the start of the morning heating to match the next waking alarm. The routine start is the alarm minus the lead time. Every run fetches today's schedule for the active group and counts the configured periods (period 1 is fixed at 00:00, and counting stops at the first unset period).
  - **Early alarm** (routine start before period 2): today's morning starts early, at the schedule's own temperatures.

    | Configured periods | Typical schedule | What happens |
    | --- | --- | --- |
    | 1 | Period 1 all day | Nothing to start early, so nothing happens |
    | 2 or 3 | Night, day (and evening setback) | Period 2 starts early and runs until its usual start, so period 3 (the evening setback) is never pulled into the morning |
    | 4 or more | Night, morning, daytime, ... | The morning shifts earlier. Period 2 runs for its usual length from the early start, then period 3 runs until its usual start, when the device schedule carries on |

  - **Late alarm** (routine start after period 2): just before period 2's usual start, period 1's temperature is held until the routine start. With 2 or 3 periods, the device schedule then carries on with period 2. With 4 or more, period 2 then runs for its usual length (never past period 4), so period 3 starts later and later periods keep their usual times.

  - **Someone up early:** if there is continuous movement somewhere in the home areas for the wake duration (3 minutes by default) after the earliest wake time (05:00 by default), the routine starts now, as if the alarm were early. Movement can pass from room to room, as long as at least one motion sensor stays on. With no alarm set, this still starts the morning early. During a late hold, it ends the hold and, with 4 or more periods, runs period 2 for its usual length from now. Turn off **Start when someone is up** to only follow the alarm.

  Each stage is a Timer override on the thermostat, so it keeps running if Home Assistant restarts.
- **Skips:** the routine only acts when the alarm is today. It is skipped when period 2 is not warmer than period 1, when a schedule temperature cannot be read, when an override is already running, or when nobody is in the home areas.
- **Catch up:** the early and late windows are checked again when Home Assistant starts and when automations reload, so a restart inside either window still applies it.
- **Resilience:** runs in queued mode (max 10, silent), re-applies the schedule group when its select recovers from `unavailable` or `unknown`, and stops with an error in the trace if the device is missing an expected entity. If the fetch fails, schedule group switching still runs, but the routine does not.

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
| Routine | next alarm sensor, lead time (30 min), start when someone is up (on), wake duration (3 min), earliest wake time (05:00) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Heated areas | Bedroom | Living room |
| Home areas | Every area | Every area |
| Lead time | 30 min | 10 min |
| Start when someone is up | Off (follows the alarm only) | On |

Temperatures come from each thermostat's own schedule, so set the morning periods on the device.

### Requirements and caveats

- Needs ZHA support for the TP-WGZBA schedule and override entities, added in [zigpy/zha-device-handlers PR #5201](https://github.com/zigpy/zha-device-handlers/pull/5201). Entities are matched by their default entity ID endings (for example `select.*_schedule_group`, `sensor.*_override_mode`, `select.*_schedule_period_2_time`), so keep those. Renaming the device part is fine.
- The option strings (`Schedule 1/2/3`, `Boost`, `Timer`, `Idle` and the day names) and entity types come from that ZHA support.
- The Device work mode must be Schedule for the on-device schedule to apply. The blueprint does not check it.
- If the routine start falls before midnight (an alarm just after 00:00), the routine is skipped, because the fetched schedule would be for the wrong day.
- Checking the Timer target rules out most manual Timers. A manual Timer at exactly the expected temperature, ending inside a routine window, would still be followed by the next stage.
- With 4 or more periods, the follow-on stages (period 3 after an early alarm, period 2 after a late hold) only run when the Timer that ended has the expected target: period 2's temperature after an early start, period 1's after a late hold. If Home Assistant is down when that Timer ends, the follow-on stage does not run and the device falls back to its normal schedule.
- During a late hold and its period 2 stage, schedule group switching for the heated areas waits until they end, and anyone up before the routine start stays at period 1's temperature.
- Heated areas and home areas are both required. If either is empty, the automation stops with an error.
- The routine needs someone anywhere in the home areas, so a downstairs thermostat heats while people are still in bed upstairs. It cannot be limited to one room, so a spare bedroom thermostat sharing the same alarm sensor would also heat whenever someone is home.
- Wake detection uses the motion sensors (device class `motion`) in the home areas. A single short movement, like turning over in bed, does not last the wake duration, but a restless sleeper with a sensitive bedroom sensor could. Pet-immune sensors help. A wake-up starts heating only in that automation's thermostat, so a bedroom automation with **Start when someone is up** off keeps following the alarm while a downstairs one starts when someone is up.
- Occupancy for the heated and home areas uses occupancy sensors (device class `occupancy`) only. For an area with only a motion sensor, create an occupancy sensor from it, for example a template binary sensor with a delay off.
- The trigger ids `prewarm`, `late-hold`, `wake`, `override-ended`, `catch-up` and `new-day` are fixed because the actions depend on them.

### Known issue

On firmware 0x00001004 the thermostat setpoint can drop to 5 °C at 00:00 each night under the on-device schedule, even with a 16 °C period at 00:00. This is a firmware issue, also reported in [Koenkk/zigbee2mqtt#33317](https://github.com/Koenkk/zigbee2mqtt/issues/33317). Raising the Frost proof temperature might mitigate it, but this is unconfirmed and still to be tested.
