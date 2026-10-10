# Home Assistant Blueprints

Blueprints I've created for my own personal use, support is not guaranteed.

## Zigbee thermostat, occupancy and alarm aware schedule

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjeverley%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzigbee_thermostat_occupancy_alarm_schedule.yaml)

File: [`blueprints/automation/zigbee_thermostat_occupancy_alarm_schedule.yaml`](blueprints/automation/zigbee_thermostat_occupancy_alarm_schedule.yaml). Requires Home Assistant 2026.10.0 or later.

Built for Sonoff TP-WGZBA Zigbee thermostats on ZHA. Create one automation per thermostat (zone).

### What it does

- **Occupancy:** switches the thermostat's active schedule group using the native occupancy and zone triggers and conditions.
  - Schedule 1 when this floor is occupied.
  - Schedule 2 when this floor is empty. A running Boost or Timer override is left alone.
  - Schedule 3 when nobody is home (the home zone is empty and every floor is clear). Any running override is ended first.
- **Pre-warm:** inside the pre-warm window before the next waking alarm, sets a Timer override at the pre-warm temperature. The period runs until the alarm or period 2, whichever is sooner, capped at 1439 minutes (the device maximum). If `require_presence` is on, someone must be on this floor.
- **Hold:** when the Timer override ends, optionally holds a working temperature until period 2, capped by the maximum hold (90 minutes by default).
- **Reading period 2:** period 1 is fixed at 00:00, so period 2 is the first heating period. The blueprint selects today as the operating day, presses the schedule fetch button and reads the "Schedule period 2 time" select. The press returns once the device has replied, so there is no wait. If the value is not a valid `HH:MM` time, the pre-warm and hold are skipped.
- **Resilience:** runs in queued mode (max 10, silent) and re-applies the schedule group when its select recovers from `unavailable` or `unknown`.

### Inputs

| Section | Inputs |
| --- | --- |
| Thermostat entities | schedule group, operating day, fetch button, schedule period 2 time, override mode, override target, override period, override apply, override exit, override mode sensor |
| Occupancy | this floor, all floors, home zone (default `zone.home`), occupied delay (1 min), empty delay (5 min) |
| Pre-warm and hold | next alarm sensor, lead time (30 min), pre-warm temperature (21 °C), require presence (on), hold enabled (on), hold temperature (20 °C), maximum hold (90 min) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Floor | Upstairs | Downstairs |
| Pre-warm lead time | 30 min | 10 min |
| Pre-warm temperature | 21 °C | 20 °C |
| Require presence | On | Off |
| Hold | On, 20 °C | Off |

### Requirements and caveats

- Needs the custom ZHA quirk for the TP-WGZBA from [zigpy/zha-device-handlers PR #5201](https://github.com/zigpy/zha-device-handlers/pull/5201). The entity names, option strings (`Schedule 1/2/3`, `Boost`, `Timer`, `Idle` and the day names) and entity types come from that quirk.
- The Device work mode must be Schedule for the on-device schedule to apply. The blueprint does not check it.
- The trigger ids `prewarm` and `override-ended` are fixed because the actions depend on them.

### Known issue

On firmware 0x00001004 the thermostat setpoint can drop to 5 °C at 00:00 each night under the on-device schedule, even with a 16 °C period at 00:00. This is a firmware issue, also reported in [Koenkk/zigbee2mqtt#33317](https://github.com/Koenkk/zigbee2mqtt/issues/33317). Raising the Frost proof temperature might mitigate it, but this is unconfirmed and still to be tested.
