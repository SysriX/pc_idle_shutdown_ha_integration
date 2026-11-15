"""Buttons per PC: reset timer, shut down now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import PcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    mgr = entry.runtime_data
    for pc in mgr.pcs.values():
        async_add_entities([
            PcButton(mgr, pc, "reset_timer", "mdi:timer-refresh"),
            PcButton(mgr, pc, "shutdown_now", "mdi:power"),
        ], config_subentry_id=pc.subentry_id)


class PcButton(PcEntity, ButtonEntity):
    def __init__(self, mgr, pc, key: str, icon: str) -> None:
        super().__init__(mgr, pc, key, "button")
        self._key = key
        self._attr_icon = icon

    async def async_press(self) -> None:
        if self._key == "reset_timer":
            await self.mgr.async_reset_timer(self.sid)
        else:
            await self.mgr.async_shutdown_now(self.sid)
