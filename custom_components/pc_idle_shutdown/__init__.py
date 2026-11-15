"""PC Idle Shutdown: shut down HASS.Agent PCs that are no longer in use."""
from __future__ import annotations

import logging
from datetime import timedelta
from types import MappingProxyType

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntry, ConfigEntryChange, ConfigSubentry,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    AGENT_DOMAIN, OPT_IGNORED, OPT_NEW_ENABLED, PC_ACTION, PC_AGENT, PC_CRITERIA,
    PC_ANGEPASST, PC_ENABLED, PC_EXEC, PC_EXEC_LOGIC, PC_EXTRA, PC_IDLE_MIN, PC_OWN_CRITERIA,
    PC_PAUSE, PC_RULE_ACTIVE, PC_RULE_LOGIC, PC_TEMPLATE, PC_WARN, PLATFORMS, SUBENTRY_PC,
)
from .manager import IdleShutdownManager, opt
from .rules import sync_templates

_LOGGER = logging.getLogger(__name__)

type IdleConfigEntry = ConfigEntry[IdleShutdownManager]


def pc_subentries(entry: ConfigEntry) -> dict[str, ConfigSubentry]:
    """Agent serial -> PC subentry."""
    return {s.data[PC_AGENT]: s for s in entry.subentries.values()
            if s.subentry_type == SUBENTRY_PC and s.data.get(PC_AGENT)}


def agent_entries(hass: HomeAssistant) -> dict[str, ConfigEntry]:
    """Agent serial -> HASS.Agent config entry."""
    return {e.unique_id: e for e in hass.config_entries.async_entries(AGENT_DOMAIN) if e.unique_id}


def new_pc_data(serial: str, enabled: bool) -> dict:
    return {PC_AGENT: serial, PC_ENABLED: enabled, PC_IDLE_MIN: 0, PC_ACTION: "global",
            PC_OWN_CRITERIA: False, PC_CRITERIA: [], PC_EXTRA: [],
            PC_TEMPLATE: "", PC_ANGEPASST: False, PC_RULE_LOGIC: "alle", PC_EXEC_LOGIC: "alle",
            PC_RULE_ACTIVE: [], PC_EXEC: [], PC_WARN: -1, PC_PAUSE: ""}


@callback
def async_discover(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create a PC subentry for every HASS.Agent PC that has none yet. True if something was added."""
    have = pc_subentries(entry)
    ignored = set(opt(entry, OPT_IGNORED) or [])
    start_exempt = set(entry.data.get("start_ausnahmen", []))
    added = False
    for serial, agent in agent_entries(hass).items():
        if serial in have or serial in ignored:
            continue
        _LOGGER.info("Neuer Rechner erkannt: %s", agent.title)
        hass.config_entries.async_add_subentry(entry, ConfigSubentry(
            data=MappingProxyType(new_pc_data(serial, bool(opt(entry, OPT_NEW_ENABLED)) and serial not in start_exempt)),
            subentry_type=SUBENTRY_PC, title=agent.title, unique_id=serial))
        added = True
    return added


async def async_setup_entry(hass: HomeAssistant, entry: IdleConfigEntry) -> bool:
    async_discover(hass, entry)
    sync_templates(hass, entry)

    mgr = IdleShutdownManager(hass, entry)
    mgr.known = set(pc_subentries(entry))           # type: ignore[attr-defined]
    entry.runtime_data = mgr
    await mgr.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _agent_changed(change: ConfigEntryChange, changed: ConfigEntry) -> None:
        if changed.domain == AGENT_DOMAIN and change == ConfigEntryChange.ADDED:
            # unique_id may be set a moment later; discovery runs again on the timer
            async_discover(hass, entry)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _agent_changed))
    entry.async_on_unload(async_track_time_interval(
        hass, lambda _now: (async_discover(hass, entry), sync_templates(hass, entry)), timedelta(minutes=5)))
    entry.async_on_unload(entry.add_update_listener(_async_updated))
    entry.async_on_unload(mgr.async_unload)
    return True


async def _async_updated(hass: HomeAssistant, entry: IdleConfigEntry) -> None:
    mgr: IdleShutdownManager = entry.runtime_data
    now = set(pc_subentries(entry))
    removed = mgr.known - now                        # type: ignore[attr-defined]
    added = now - mgr.known                          # type: ignore[attr-defined]
    mgr.known = now                                  # type: ignore[attr-defined]
    if removed:
        # a PC the user deleted stays unmanaged (is not re-created by discovery)
        ignored = sorted(set(opt(entry, OPT_IGNORED) or []) | (removed & set(agent_entries(hass))))
        hass.config_entries.async_update_entry(entry, options={**entry.options, OPT_IGNORED: ignored})
    if added or removed:
        hass.config_entries.async_schedule_reload(entry.entry_id)
        return
    # template changed / PC without template -> take over (fires this listener again)
    if sync_templates(hass, entry):
        return
    mgr.sync_subentries()
    await mgr.async_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: IdleConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
