# Home Assistant Blueprints

Blueprints I've created for my own personal use, support is not guaranteed.

## Zigbee thermostat, occupancy and alarm aware schedule

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjeverley%2Fhome-assistant-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fzigbee_thermostat_occupancy_alarm_schedule.yaml)

File: [`blueprints/automation/zigbee_thermostat_occupancy_alarm_schedule.yaml`](blueprints/automation/zigbee_thermostat_occupancy_alarm_schedule.yaml). Requires Home Assistant 2026.10.0 or later.

Built for Sonoff TP-WGZBA Zigbee thermostats on ZHA with a custom quirk (`tp_wgzba.py`) that exposes the schedule, override and work mode entities. Create one automation per thermostat (zone). Occupancy can be watched for an area or a whole floor, so a thermostat can follow just its room or everything on its level.

### What it does

- **Occupancy:** switches the thermostat's active schedule group using the native occupancy and zone triggers and conditions.
  - Schedule 1: this area is occupied.
  - Schedule 2: this area is empty.
  - Schedule 3: nobody is home (the home zone is empty and every area in the house is clear). Any running override is exited first.
- **Pre-warm:** inside the pre-warm window before the next waking alarm, sets a Timer override at the pre-warm temperature. The period runs until the alarm or the first heating slot, whichever is earlier. The home zone must be occupied and, if `require_presence` is on, someone must be in this area.
- **Hold:** when the Timer override ends, optionally holds a working temperature until the first heating slot, capped by the maximum hold.
- **First heating slot:** read from the device. The blueprint sets the operating day to today, presses the schedule fetch button, waits up to 10 s for the "Schedule period 2 time" select to report again, then uses period 2 (period 1 is fixed at 00:00). If the read fails, pre-warm and hold are skipped.
- **Resilience:** runs in queued mode (max 10, silent), re-applies the schedule group when its select recovers from `unavailable` or `unknown`, and caps override periods at 1439 minutes or the maximum hold.

### Inputs

| Section | Inputs |
| --- | --- |
| Thermostat entities | schedule group, operating day, fetch button, period 2 time, override mode, override target, override period, override apply, override exit, override mode sensor |
| Occupancy | this area or floor, all areas or floors in the house, home zone (default `zone.home`), occupied delay (1 min), empty delay (5 min) |
| Pre-warm and hold | next alarm sensor, lead time (30 min), pre-warm temperature (21 °C), require presence (on), hold enabled (on), hold temperature (20 °C), maximum hold (180 min) |

### Example configurations

| Setting | Bedroom | Living room |
| --- | --- | --- |
| Area or floor | Upstairs floor (or the bedroom area) | Downstairs floor (or the living room area) |
| Pre-warm lead time | 30 min | 10 min |
| Pre-warm temperature | 21 °C | 20 °C |
| Require presence | On | Off |
| Hold | On, 20 °C | Off |

### Caveats

- Not yet tested against live hardware. Check:
  - the native occupancy and zone trigger and condition syntax on Home Assistant 2026.10;
  - the select option strings (`Schedule 1/2/3`, `Timer`, `Boost`, `Idle` and the day names);
  - that the fetch wait works, which needs `last_reported` to update even when the fetched value is unchanged.
- The occupancy inputs use target selectors, so the UI also offers devices and entities. Only areas and floors were intended.
- The device work mode must be set to Schedule. The blueprint does not check it.
- The option strings and entity types are specific to the custom ZHA quirk.
- The trigger ids `prewarm` and `override-ended` are fixed because the actions depend on them.
