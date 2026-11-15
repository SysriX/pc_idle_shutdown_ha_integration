"""Switches: master, dry run, per-PC 'shut down when idle'."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import OPT_DRY_RUN, OPT_ENABLED, PC_ENABLED
from homeassistant.util import dt as dt_util

from .entity import HubEntity, PcEntity, slug
from .manager import opt, window_matches, windows


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    # drop switches of deleted time windows
    reg = er.async_get(hass)
    keep = {f"{entry.entry_id}_hub_cfg_window_{w.get('id')}" for w in windows(entry)}
    for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
        if ent.unique_id.startswith(f"{entry.entry_id}_hub_cfg_window_") and ent.unique_id not in keep:
            reg.async_remove(ent.entity_id)
    async_add_entities([
        HubSwitch(mgr, "cfg_enabled", OPT_ENABLED, "mdi:power-sleep"),
        HubSwitch(mgr, "cfg_dry_run", OPT_DRY_RUN, "mdi:test-tube"),
        *[WindowSwitch(mgr, w) for w in windows(entry) if w.get("id")],
    ])
    for pc in mgr.pcs.values():
        async_add_entities([PcSwitch(mgr, pc)], config_subentry_id=pc.subentry_id)


class HubSwitch(HubEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, mgr, key: str, option: str, icon: str) -> None:
        super().__init__(mgr, key, "switch")
        self._option = option
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return bool(opt(self.mgr.entry, self._option))

    async def async_turn_on(self, **kwargs) -> None:
        self.mgr.set_opt(**{self._option: True})

    async def async_turn_off(self, **kwargs) -> None:
        self.mgr.set_opt(**{self._option: False})


class PcSwitch(PcEntity, SwitchEntity):
    """On = PC is shut down when idle; off = PC stays on (exception list)."""

    _attr_icon = "mdi:power-settings"

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "cfg_enabled", "switch")

    @property
    def is_on(self) -> bool:
        pc = self.pc
        return bool(pc and self.mgr.enabled(pc))

    async def async_turn_on(self, **kwargs) -> None:
        self.mgr.set_pc(self.sid, **{PC_ENABLED: True})

    async def async_turn_off(self, **kwargs) -> None:
        self.mgr.set_pc(self.sid, **{PC_ENABLED: False})


class WindowSwitch(HubEntity, SwitchEntity):
    """Switch one time window on or off (applies to all PCs)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, mgr, win: dict) -> None:
        super().__init__(mgr, f"cfg_window_{win['id']}", "switch")
        self._win_id = win["id"]
        self._attr_translation_key = None
        self._attr_name = f"Zeitfenster {win.get('name') or win['id']}"
        self.entity_id = f"switch.haus_sys_idle_shutdown_cfg_window_{slug(win.get('name') or win['id'])}"

    def _win(self) -> dict | None:
        return next((w for w in windows(self.mgr.entry) if w.get("id") == self._win_id), None)

    @property
    def available(self) -> bool:
        return self._win() is not None

    @property
    def is_on(self) -> bool:
        w = self._win()
        return bool(w and w.get("aktiv", True))

    @property
    def extra_state_attributes(self) -> dict:
        w = self._win() or {}
        return {"tage": w.get("tage"), "von": w.get("von"), "bis": w.get("bis"),
                "gerade_gueltig": bool(w) and window_matches(w, dt_util.now())}

    async def async_turn_on(self, **kwargs) -> None:
        self.mgr.set_window(self._win_id, aktiv=True)

    async def async_turn_off(self, **kwargs) -> None:
        self.mgr.set_window(self._win_id, aktiv=False)
