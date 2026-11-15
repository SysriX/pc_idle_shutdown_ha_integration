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
- **Dry run**, several time windows (shared by all PCs, each with its own switch), grace time after boot, optional notify service for Home Assistant.

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

## Time windows

*Configure → Time windows* defines when the rules are active – for **all PCs at once**:

- Any number of windows, each with name, weekdays, from and until (e.g. *Mon–Thu 18:00–07:00*, *Fri 15:00–07:00*,
  *Sat/Sun whole day*). Until before from = over midnight (belongs to the start day), from = until = whole day.
- Every window has its own switch `switch.pc_auto_idle_off_window_<name>_cfg_enabled` to turn it off temporarily.
- Rules only act inside an enabled window. With no window enabled they apply around the clock.
- The hub sensor shows `zeitfenster`, `aktive_zeitfenster` and `im_zeitfenster`.

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

All entity IDs start with `pc_auto_idle_off` (no room prefix).

House-wide device *PC-Abschaltung*:

| Entity | Meaning |
|---|---|
| `switch.pc_auto_idle_off_cfg_enabled` | master switch |
| `switch.pc_auto_idle_off_cfg_dry_run` | dry run |
| `number.pc_auto_idle_off_cfg_idle_minutes` | idle time (built-in logic) |
| `number.pc_auto_idle_off_cfg_warn_minutes` | warning time |
| `sensor.pc_auto_idle_off_online_count` | PCs online, lists and time windows in attributes |
| `switch.pc_auto_idle_off_window_<name>_cfg_enabled` | one per time window |

Per PC, device *Abschaltung &lt;PC&gt;* (`<pc>` = PC name, e.g. `xcs_desktop`):

| Entity | Meaning |
|---|---|
| `sensor.pc_auto_idle_off_<pc>_status` | status, conditions in attributes |
| `sensor.pc_auto_idle_off_<pc>_idle_minutes` | idle for |
| `sensor.pc_auto_idle_off_<pc>_shutdown_at` | planned shutdown |
| `binary_sensor.pc_auto_idle_off_<pc>_in_use` | in use |
| `switch.pc_auto_idle_off_<pc>_cfg_enabled` | shut down automatically (off = exception) |
| `number.pc_auto_idle_off_<pc>_cfg_idle_minutes` | own idle time (0 = global) |
| `button.pc_auto_idle_off_<pc>_reset_timer` | reset timer |
| `button.pc_auto_idle_off_<pc>_shutdown_now` | shut down now |

Event `pc_idle_shutdown_event` with `type` = `warning` | `shutdown` | `cancelled` for your own automations.

## License

MIT
