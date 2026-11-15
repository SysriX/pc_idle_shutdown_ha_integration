"""Numbers: idle time (global and per PC), warning time."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime

from .const import OPT_IDLE_MIN, OPT_WARN_MIN, PC_IDLE_MIN
from .entity import HubEntity, PcEntity
from .manager import opt


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    async_add_entities([
        HubNumber(mgr, "cfg_idle_minutes", OPT_IDLE_MIN, 5, 1440, "mdi:timer-sand"),
        HubNumber(mgr, "cfg_warn_minutes", OPT_WARN_MIN, 0, 60, "mdi:bell-alert"),
    ])
    for pc in mgr.pcs.values():
        async_add_entities([PcNumber(mgr, pc)], config_subentry_id=pc.subentry_id)


class HubNumber(HubEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, mgr, key: str, option: str, lo: int, hi: int, icon: str) -> None:
        super().__init__(mgr, key, "number")
        self._option = option
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_icon = icon

    @property
    def native_value(self) -> float:
        return float(opt(self.mgr.entry, self._option))

    async def async_set_native_value(self, value: float) -> None:
        self.mgr.set_opt(**{self._option: int(value)})


class PcNumber(PcEntity, NumberEntity):
    """Own idle time of a PC, 0 = use the global value."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1
    _attr_native_min_value = 0
    _attr_native_max_value = 1440
    _attr_icon = "mdi:timer-sand"

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "cfg_idle_minutes", "number")

    @property
    def native_value(self) -> float | None:
        pc = self.pc
        return float(self.mgr.pc_cfg(pc, PC_IDLE_MIN, 0) or 0) if pc else None

    @property
    def extra_state_attributes(self) -> dict:
        pc = self.pc
        return {"effektiv_minuten": self.mgr.idle_limit(pc)} if pc else {}

    async def async_set_native_value(self, value: float) -> None:
        self.mgr.set_pc(self.sid, **{PC_IDLE_MIN: int(value)})
