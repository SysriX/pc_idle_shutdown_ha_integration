"""Base entities."""
from __future__ import annotations

import re

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .manager import IdleShutdownManager, PcState

_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower().translate(_UML)).strip("_") or "pc"


class BaseIdleEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, mgr: IdleShutdownManager) -> None:
        self.mgr = mgr

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()


class HubEntity(BaseIdleEntity):
    """Entity of the house-wide hub device."""

    def __init__(self, mgr: IdleShutdownManager, key: str, platform: str) -> None:
        super().__init__(mgr)
        self._attr_unique_id = f"{mgr.entry.entry_id}_hub_{key}"
        self._attr_translation_key = f"hub_{key}"
        # naming scheme <raum>_<gewerk>_<funktion>_cfg_<param>
        self.entity_id = f"{platform}.haus_sys_idle_shutdown{'' if key == 'status' else '_' + key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{mgr.entry.entry_id}_hub")},
            name="PC-Leerlauf-Abschaltung", manufacturer="SysriX", model="Idle Shutdown")


class PcEntity(BaseIdleEntity):
    """Entity of one PC."""

    def __init__(self, mgr: IdleShutdownManager, pc: PcState, key: str, platform: str) -> None:
        super().__init__(mgr)
        self.sid = pc.subentry_id
        self._attr_unique_id = f"{pc.serial}_{key}"
        self._attr_translation_key = key
        mgr._resolve(pc)
        objekt = slug(pc.name)
        self.entity_id = f"{platform}.{pc.room}_sys_idle_shutdown_{objekt}{'' if key == 'status' else '_' + key}"
        dev = mgr.agent_device(pc) if pc.agent_entry_id else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pc.serial)},
            name=f"{pc.name} Leerlauf", manufacturer="SysriX", model="Idle Shutdown",
            suggested_area=None if dev is None else _area_name(mgr, dev.area_id))

    @property
    def pc(self) -> PcState | None:
        return self.mgr.pcs.get(self.sid)

    @property
    def available(self) -> bool:
        return self.pc is not None


def _area_name(mgr: IdleShutdownManager, area_id: str | None) -> str | None:
    if not area_id:
        return None
    from homeassistant.helpers import area_registry as ar
    area = ar.async_get(mgr.hass).async_get_area(area_id)
    return area.name if area else None
