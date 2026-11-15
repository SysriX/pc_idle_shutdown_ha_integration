"""Switches: master, dry run, per-PC 'shut down when idle'."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .const import OPT_DRY_RUN, OPT_ENABLED, PC_ENABLED
from .entity import HubEntity, PcEntity
from .manager import opt


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    async_add_entities([
        HubSwitch(mgr, "cfg_enabled", OPT_ENABLED, "mdi:power-sleep"),
        HubSwitch(mgr, "cfg_dry_run", OPT_DRY_RUN, "mdi:test-tube"),
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
