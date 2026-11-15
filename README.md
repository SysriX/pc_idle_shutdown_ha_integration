# PC Idle Shutdown for Home Assistant

Automatically shuts down (or hibernates / sleeps) Windows PCs that are no longer in use, based on the sensors of
[HASS.Agent .NET10](https://github.com/v1k70rk4/HASS.Agent.NET10-Integration).

- **Automatic discovery** – every PC set up in the HASS.Agent .NET10 integration is added as a *PC* sub-entry and is
  shut down when idle by default.
- **Exceptions** – PCs that should keep running even when idle: switch off *Shut down when idle* on the PC, or pick
  them under *Configure → Exceptions* (also offered during setup).
- **Per PC settings** – own idle time, action (shut down / hibernate / sleep), own in-use criteria and extra
  entities that keep the PC on (e.g. a backup job sensor).
- **Warning** – a notification on the PC some minutes before; any activity cancels the shutdown (a pending
  Windows shutdown is aborted too).
- **Dry run**, time window and weekdays, grace time after boot, optional notify service for Home Assistant.

## Rules and templates

Instead of the built-in idle logic you can build your own rules from the entities of the PCs:

- **Template** (*Add template* on the integration page): pick a reference PC, then add conditions from the list of
  its entities (shown with their current value). The value field depends on the entity: numbers get ≥ / > / ≤ / < /
  = / ≠, sensors with options get a dropdown of their states, on/off entities get *is on / is off*, text gets
  *equals / contains*. *PC is reachable* and entities that are not from the PC (same for all PCs) are possible too.
  - **Rule active when …** – e.g. *Logged in users ≥ 1* or *RDP sessions ≥ 1* (logic AND or OR).
  - **Run rule when …** – e.g. *Idle time ≥ 600 s* and *PC is reachable*. When these hold, the PC gets the warning,
    and after the warning time the action runs. Activity in between cancels it.
- A template stores only the *kind* of entity (`sensor:idle_time_seconds`), so it fits every PC. Applied to a PC,
  the PC's own entities are filled in.
- **Automatic** templates are applied to every PC without a template, new ones included. PCs keep following
  their template until you edit their conditions (*edited* – template changes are no longer taken over).
- **Per PC** (*Edit PC*): apply or remove a template, add/remove conditions, choose a **pause entity** – the rule
  rests while it is on/true (e.g. an `input_boolean`).
- Without *run* conditions the built-in idle logic below decides, the rule only arms it.

## What counts as "in use" (built-in logic)

| Criterion | Source (HASS.Agent sensor) |
|---|---|
| Mouse / keyboard | `idle_time` – idle time counts down to the shutdown. If the tray app is closed and a user is logged in and not locked, the PC counts as in use (safe default). |
| Remote desktop | `rdp_sessions` > 0 (not disconnected, not locked) |
| CPU load | average of `cpu_usage` above a limit (default 25 % over 5 min) |
| Media | media player `playing` |
| Camera / microphone | `camera_in_use`, `microphone_in_use` |
| Display kept on | `sleep_blocked` with `display_required` (video, presentation) |
| Somebody logged in | `logged_in_users` > 0 (strict, off by default) |

## Installation

1. HACS → Custom repositories → `https://github.com/SysriX/pc_idle_shutdown_ha_integration` (Integration), install.
2. Restart Home Assistant.
3. Settings → Devices & services → Add integration → **PC Idle Shutdown**.

Requires Home Assistant 2025.6 or newer and the HASS.Agent .NET10 integration.

## Entities

House-wide device *PC-Leerlauf-Abschaltung*: `switch.haus_sys_idle_shutdown_cfg_enabled` (master),
`switch.haus_sys_idle_shutdown_cfg_dry_run`, `number.haus_sys_idle_shutdown_cfg_idle_minutes`,
`number.haus_sys_idle_shutdown_cfg_warn_minutes`, `sensor.haus_sys_idle_shutdown` (PCs online, lists in attributes).

Per PC (`<room>_sys_idle_shutdown_<pc>`): status sensor, *idle for*, *planned shutdown*, *in use* binary sensor,
*shut down when idle* switch, *own idle time* number, *reset timer* and *shut down now* buttons.

Event `pc_idle_shutdown_event` with `type` = `warning` | `shutdown` | `cancelled` for your own automations.

## License

MIT
