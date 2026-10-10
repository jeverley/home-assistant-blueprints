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
  - Schedule 3 when nobody is home (the home zone is empty and the whole house is clear). Any running override is ended first.
- **Early morning heating:** from the lead time before the next waking alarm, the morning part of today's on-device schedule starts early, at the schedule's own temperatures. The blueprint fetches today's schedule for the active group and counts the configured periods (period 1 is fixed at 00:00, and counting stops at the first unset period).

  | Configured periods | Typical schedule | What happens |
  | --- | --- | --- |
  | 1 | Period 1 all day | Nothing to start early, so nothing happens |
  | 2 or 3 | Night, day (and evening setback) | Period 2 starts early and runs until its usual start, so period 3 (the evening setback) is never pulled into the morning |
  | 4 or more | Night, morning, daytime, ... | The morning shifts earlier. Period 2 runs for its usual length from the early start, then period 3 runs until its usual start, when the device schedule carries on |

  Each stage is a Timer override on the thermostat, so it keeps running if Home Assistant restarts.
- **Skips:** early heating is skipped when the early start (alarm minus lead time) is at or after period 2, since the schedule is already heating by then. It is also skipped when period 2 is not warmer than period 1, when a schedule temperature cannot be read, when an override is already running, or when nobody is in the house.
- **Catch up:** the early heating window is checked again when Home Assistant starts and when automations reload, so a restart inside the window still starts it.
- **Resilience:** runs in queued mode (max 10, silent), re-applies the schedule group when its select recovers from `unavailable` or `unknown`, and stops with an error in the trace if the device is missing an expected entity.

#### Example (4 periods)

Schedule 00:00 16 °C, 06:30 21 °C, 08:00 18 °C, 22:00 16 °C. Alarm 05:30, lead 30 minutes.

| Time | Without the blueprint | With the blueprint |
| --- | --- | --- |
| 05:00 to 06:30 | 16 °C | 21 °C (period 2, its usual 90 minutes) |
| 06:30 to 08:00 | 21 °C | 18 °C (period 3, until its usual start) |
| From 08:00 | 18 °C | 18 °C (device schedule) |

### Inputs

| Section | Inputs |
| --- | --- |
| Thermostat | the TP-WGZBA device |
| Occupancy | heated areas and floors, whole house areas and floors, home zone (default `zone.home`), occupied delay (1 min), empty delay (5 min) |
| Early morning heating | next alarm sensor, lead time (30 min) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Heated areas | Bedroom | Living room |
| Whole house floors | Upstairs, Downstairs | Upstairs, Downstairs |
| Lead time | 30 min | 10 min |

Temperatures come from each thermostat's own schedule, so set the morning periods on the device.

### Requirements and caveats

- Needs the custom ZHA quirk for the TP-WGZBA from [zigpy/zha-device-handlers PR #5201](https://github.com/zigpy/zha-device-handlers/pull/5201). Entities are matched by their default entity ID endings (for example `select.*_schedule_group`, `sensor.*_override_mode`, `select.*_schedule_period_2_time`), so keep those. Renaming the device part is fine.
- The option strings (`Schedule 1/2/3`, `Boost`, `Timer`, `Idle` and the day names) and entity types come from that quirk.
- The Device work mode must be Schedule for the on-device schedule to apply. The blueprint does not check it.
- If the early heating window starts before midnight (an alarm just after 00:00), it is skipped, because the fetched schedule would be for the wrong day.
- The second stage only runs when the Timer that ended still has period 2's temperature as its target, which rules out most manual Timers. A manual Timer at exactly that temperature, ending before period 3, would still be followed by period 3.
- If Home Assistant is down at the moment the first stage ends, the second stage does not run and the device falls back to its normal schedule.
- Heated and whole house each have an areas input and a floors input (both multiple), which are combined. Set at least one of each, or the automation stops with an error.
- Early heating needs someone anywhere in the whole house areas or floors, so a downstairs thermostat heats while people are still in bed upstairs. It cannot be limited to one room, so a spare bedroom thermostat sharing the same alarm sensor would also heat whenever someone is home.
- The trigger ids `prewarm` and `override-ended` are fixed because the actions depend on them.

### Known issue

On firmware 0x00001004 the thermostat setpoint can drop to 5 °C at 00:00 each night under the on-device schedule, even with a 16 °C period at 00:00. This is a firmware issue, also reported in [Koenkk/zigbee2mqtt#33317](https://github.com/Koenkk/zigbee2mqtt/issues/33317). Raising the Frost proof temperature might mitigate it, but this is unconfirmed and still to be tested.
