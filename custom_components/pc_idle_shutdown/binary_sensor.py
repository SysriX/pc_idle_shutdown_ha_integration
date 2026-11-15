"""Binary sensor per PC: in use."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .const import ST_ACTIVE
from .entity import PcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    for pc in mgr.pcs.values():
        async_add_entities([PcInUse(mgr, pc)], config_subentry_id=pc.subentry_id)


class PcInUse(PcEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, mgr, pc) -> None:
        super().__init__(mgr, pc, "in_use", "binary_sensor")

    @property
    def is_on(self) -> bool | None:
        pc = self.pc
        if pc is None or not pc.online:
            return None if pc is None else False
        if pc.rule_mode and pc.conditions and any(c["gruppe"] == "ausfuehren_wenn" for c in pc.conditions):
            return not pc.fire
        return pc.status == ST_ACTIVE or bool(pc.reasons)

    @property
    def extra_state_attributes(self) -> dict:
        pc = self.pc
        return {"gruende": pc.reasons} if pc else {}
