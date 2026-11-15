"""Sensors: hub overview, per PC status / inactive minutes / planned shutdown."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime

from .const import (
    PC_ANGEPASST, PC_PAUSE, PC_TEMPLATE,
    OPT_DRY_RUN, OPT_ENABLED, ST_ACTIVE, ST_EXEMPT, ST_IDLE, ST_OFFLINE, ST_SHUTDOWN, ST_WARNING,
    ST_ARMED, STATES,
)
from .entity import HubEntity, PcEntity
from .manager import in_window, opt
from homeassistant.util import dt as dt_util



async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    async_add_entities([HubStatus(mgr)])
    for pc in mgr.pcs.values():
        async_add_entities([
            PcStatus(mgr, pc), PcInactive(mgr, pc), PcShutdownAt(mgr, pc),
        ], config_subentry_id=pc.subentry_id)


class HubStatus(HubEntity, SensorEntity):
    """Number of PCs that are online and managed, list in attributes."""

    _attr_icon = "mdi:desktop-tower-monitor"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "status", "sensor")

    @property
    def native_value(self) -> int:
        return sum(1 for p in self.mgr.pcs.values() if p.online)

    @property
    def extra_state_attributes(self) -> dict:
        pcs = sorted(self.mgr.pcs.values(), key=lambda p: p.name.lower())
        return {
            "aktiv": bool(opt(self.mgr.entry, OPT_ENABLED)),
            "probelauf": bool(opt(self.mgr.entry, OPT_DRY_RUN)),
            "im_zeitfenster": in_window(self.mgr.entry, dt_util.now()),
            "rechner": {p.name: p.status for p in pcs},
            "ausgenommen": [p.name for p in pcs if p.status == ST_EXEMPT or not self.mgr.enabled(p)],
            "in_benutzung": [p.name for p in pcs if p.status == ST_ACTIVE],
            "inaktiv": [p.name for p in pcs if p.status in (ST_IDLE, ST_WARNING)],
            "regel_bereit": [p.name for p in pcs if p.status == ST_ARMED],
            "abgeschaltet": [p.name for p in pcs if p.status == ST_SHUTDOWN],
            "offline": [p.name for p in pcs if p.status == ST_OFFLINE],
        }


class PcStatus(PcEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES
    _attr_icon = "mdi:desktop-classic"

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "status", "sensor")

    @property
    def native_value(self) -> str | None:
        pc = self.pc
        return pc.status if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        pc = self.pc
        if pc is None:
            return {}
        m = self.mgr
        return {
            "rechner": pc.name,
            "online": pc.online,
            "gruende": pc.reasons,
            "inaktiv_minuten": round(pc.inactive_minutes, 1),
            "grenze_minuten": m.idle_limit(pc),
            "aktion": m.action(pc),
            "kriterien": m.criteria(pc),
            "abschalten": m.enabled(pc),
            "letzter_befehl": pc.command_sent.isoformat() if pc.command_sent else None,
            "probelauf": bool(opt(m.entry, OPT_DRY_RUN)),
            "entitaeten": {k: v for k, v in pc.entities.items() if v},
            "regelmodus": pc.rule_mode,
            "vorlage": (m.entry.subentries[t].title if (t := m.pc_cfg(pc, PC_TEMPLATE)) in m.entry.subentries else None),
            "angepasst": bool(m.pc_cfg(pc, PC_ANGEPASST, False)),
            "pause_entitaet": m.pc_cfg(pc, PC_PAUSE) or None,
            "warn_minuten": m.warn_minutes(pc),
            "bedingungen": pc.conditions,
        }


class PcInactive(PcEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:timer-sand"

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "inactive_minutes", "sensor")

    @property
    def native_value(self) -> float | None:
        pc = self.pc
        if pc is None or not pc.online:
            return None
        return round(pc.inactive_minutes, 1)


class PcShutdownAt(PcEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "shutdown_at", "sensor")

    @property
    def native_value(self):
        pc = self.pc
        if not pc or not pc.online:
            return None
        if pc.rule_mode:
            return pc.shutdown_at if pc.status == ST_WARNING else None
        return pc.shutdown_at if pc.status in (ST_ACTIVE, ST_IDLE, ST_WARNING) else None
