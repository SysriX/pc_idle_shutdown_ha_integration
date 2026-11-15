"""Idle detection and shutdown logic for all HASS.Agent PCs."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    AGENT_DOMAIN, CRIT_CAMMIC, CRIT_CPU, CRIT_DISPLAY, CRIT_INPUT, CRIT_MEDIA, CRIT_RDP,
    CRIT_USERS, DEFAULT_CRITERIA, DEFAULTS, EVENT, KEY_CAM, KEY_CPU, KEY_IDLE, KEY_LOCKED,
    KEY_MIC, KEY_RDP, KEY_SESSION, KEY_SLEEP_BLOCKED, KEY_UPTIME, KEY_USERS, OPT_ACTION,
    OPT_BOOT_GRACE, OPT_CPU_LIMIT, OPT_CPU_MIN, OPT_CRITERIA, OPT_DAYS, OPT_DRY_RUN, OPT_ENABLED,
    OPT_FROM, OPT_IDLE_MIN, OPT_NOTIFY, OPT_TO, OPT_WARN_MIN, OPT_WINDOWS, PC_ACTION, PC_AGENT, PC_CRITERIA,
    PC_ENABLED, PC_EXEC, PC_EXEC_LOGIC, PC_EXTRA, PC_IDLE_MIN, PC_OWN_CRITERIA, PC_PAUSE,
    PC_RULE_ACTIVE, PC_RULE_LOGIC, PC_WARN, ROOM_CODES, SIGNAL_UPDATE, ST_ACTIVE, ST_ARMED,
    ST_EXEMPT, ST_IDLE, ST_NOT_ARMED, ST_OFFLINE, ST_OUTSIDE, ST_PAUSED, ST_RULE_PAUSED, ST_SHUTDOWN,
    ST_WARNING, SUBENTRY_PC, TICK_SECONDS, WEEKDAYS,
)
from . import rules

_LOGGER = logging.getLogger(__name__)

TRUTHY = {"on", "true", "yes", "1", "locked", "active", "playing", "home", "open"}
# after a shutdown command: how long we wait for the PC to go offline before trying again
RETRY_AFTER = timedelta(minutes=10)
# activity within this time after the command still cancels a pending shutdown (agent delay is 60 s)
CANCEL_WINDOW = timedelta(seconds=75)


def opt(entry: ConfigEntry, key: str) -> Any:
    if key == OPT_CRITERIA:
        return entry.options.get(OPT_CRITERIA, DEFAULT_CRITERIA)
    return entry.options.get(key, DEFAULTS.get(key))


def _truthy(state) -> bool | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    return str(state.state).strip().lower() in TRUTHY


def _number(state) -> float | None:
    if state is None:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _parse_time(text: str) -> time:
    try:
        h, m = str(text or "00:00").split(":")[:2]
        return time(int(h), int(m))
    except (TypeError, ValueError):
        return time(0, 0)


def windows(entry: ConfigEntry) -> list[dict]:
    """Time windows (shared by all PCs). Older single from/to/days setting is read as one window."""
    if OPT_WINDOWS in entry.options:
        return list(entry.options.get(OPT_WINDOWS) or [])
    days = opt(entry, OPT_DAYS) or WEEKDAYS
    t_from, t_to = str(opt(entry, OPT_FROM))[:5], str(opt(entry, OPT_TO))[:5]
    if t_from == t_to and set(days) == set(WEEKDAYS):
        return []
    return [{"id": "alt", "name": "Zeitfenster", "von": t_from, "bis": t_to, "tage": list(days), "aktiv": True}]


def window_matches(win: dict, now: datetime) -> bool:
    days = win.get("tage") or []
    t_from, t_to = _parse_time(win.get("von")), _parse_time(win.get("bis"))
    cur = now.time()
    if t_from == t_to:                         # whole day
        return WEEKDAYS[now.weekday()] in days
    if t_from < t_to:
        return t_from <= cur < t_to and WEEKDAYS[now.weekday()] in days
    # over midnight: the part after midnight belongs to the day it started on
    if cur >= t_from:
        return WEEKDAYS[now.weekday()] in days
    if cur < t_to:
        return WEEKDAYS[(now.weekday() - 1) % 7] in days
    return False


def active_windows(entry: ConfigEntry, now: datetime) -> list[dict]:
    return [w for w in windows(entry) if w.get("aktiv", True) and window_matches(w, now)]


def in_window(entry: ConfigEntry, now: datetime) -> bool:
    """True if rules may act now: inside one enabled window, or no window is enabled at all."""
    enabled = [w for w in windows(entry) if w.get("aktiv", True)]
    if not enabled:
        return True
    return any(window_matches(w, now) for w in enabled)


@dataclass
class PcState:
    """Runtime state of one PC."""

    subentry_id: str
    serial: str
    name: str = ""
    room: str = "haus"
    agent_entry_id: str | None = None
    online: bool = False
    status: str = ST_OFFLINE
    reasons: list[str] = field(default_factory=list)
    last_activity: datetime = field(default_factory=dt_util.utcnow)
    inactive_since: datetime | None = None
    shutdown_at: datetime | None = None
    warned: bool = False
    command_sent: datetime | None = None
    last_command: str | None = None
    cpu: deque = field(default_factory=lambda: deque(maxlen=120))
    rule_mode: bool = False
    fire: bool = False
    exec_since: datetime | None = None
    conditions: list[dict] = field(default_factory=list)
    entities: dict[str, str | None] = field(default_factory=dict)

    @property
    def inactive_minutes(self) -> float:
        if self.inactive_since is None:
            return 0.0
        return max(0.0, (dt_util.utcnow() - self.inactive_since).total_seconds() / 60)


class IdleShutdownManager:
    """Watches all PCs and shuts them down when idle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.pcs: dict[str, PcState] = {}      # subentry_id -> state
        self._unsub = None

    # ------------------------------------------------------------------ setup
    async def async_start(self) -> None:
        self.sync_subentries()
        await self._async_tick()
        self._unsub = async_track_time_interval(self.hass, self._tick, timedelta(seconds=TICK_SECONDS))

    async def async_unload(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def sync_subentries(self) -> None:
        """Keep runtime states in line with the PC subentries."""
        have = {s.subentry_id: s for s in self.entry.subentries.values() if s.subentry_type == SUBENTRY_PC}
        for sid in list(self.pcs):
            if sid not in have:
                self.pcs.pop(sid)
        for sid, sub in have.items():
            if sid not in self.pcs:
                self.pcs[sid] = PcState(subentry_id=sid, serial=sub.data[PC_AGENT], name=sub.title)
            self.pcs[sid].name = sub.title

    @callback
    def set_pc(self, subentry_id: str, **changes: Any) -> None:
        """Change settings of one PC (stored in its subentry)."""
        sub = self.entry.subentries.get(subentry_id)
        if sub is not None:
            self.hass.config_entries.async_update_subentry(self.entry, sub, data={**sub.data, **changes})

    @callback
    def set_window(self, win_id: str, **changes: Any) -> None:
        """Change one time window (e.g. switch it on/off)."""
        wins = [dict(w, **changes) if w.get("id") == win_id else dict(w) for w in windows(self.entry)]
        self.set_opt(**{OPT_WINDOWS: wins})

    @callback
    def set_opt(self, **changes: Any) -> None:
        """Change global settings (entry options)."""
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, **changes})

    def sub(self, pc: PcState) -> ConfigSubentry | None:
        return self.entry.subentries.get(pc.subentry_id)

    def pc_cfg(self, pc: PcState, key: str, default: Any = None) -> Any:
        sub = self.sub(pc)
        return (sub.data if sub else {}).get(key, default)

    # ----------------------------------------------------------- effective cfg
    def idle_limit(self, pc: PcState) -> int:
        own = int(self.pc_cfg(pc, PC_IDLE_MIN, 0) or 0)
        return own if own > 0 else int(opt(self.entry, OPT_IDLE_MIN))

    def action(self, pc: PcState) -> str:
        a = self.pc_cfg(pc, PC_ACTION, "global") or "global"
        return opt(self.entry, OPT_ACTION) if a == "global" else a

    def criteria(self, pc: PcState) -> list[str]:
        if self.pc_cfg(pc, PC_OWN_CRITERIA, False):
            return list(self.pc_cfg(pc, PC_CRITERIA, []) or [])
        return list(opt(self.entry, OPT_CRITERIA) or [])

    def warn_minutes(self, pc: PcState) -> int:
        own = self.pc_cfg(pc, PC_WARN, None)
        if own is not None and int(own) >= 0:
            return int(own)
        return max(0, int(opt(self.entry, OPT_WARN_MIN)))

    def is_rule_mode(self, pc: PcState) -> bool:
        return bool(self.pc_cfg(pc, PC_EXEC) or self.pc_cfg(pc, PC_RULE_ACTIVE) or self.pc_cfg(pc, PC_PAUSE))

    def enabled(self, pc: PcState) -> bool:
        return bool(self.pc_cfg(pc, PC_ENABLED, True))

    # --------------------------------------------------------------- lookups
    def agent_entry(self, pc: PcState) -> ConfigEntry | None:
        for e in self.hass.config_entries.async_entries(AGENT_DOMAIN):
            if e.unique_id == pc.serial:
                return e
        return None

    def agent_device(self, pc: PcState) -> dr.DeviceEntry | None:
        if not pc.agent_entry_id:
            return None
        devs = dr.async_entries_for_config_entry(dr.async_get(self.hass), pc.agent_entry_id)
        return devs[0] if devs else None

    def _resolve(self, pc: PcState) -> None:
        reg = er.async_get(self.hass)
        s = pc.serial

        def eid(platform: str, uid: str) -> str | None:
            return reg.async_get_entity_id(platform, AGENT_DOMAIN, uid)

        pc.entities = {
            "idle": eid("sensor", f"sensor_{s}_{KEY_IDLE}"),
            "locked": eid("sensor", f"sensor_{s}_{KEY_LOCKED}"),
            "users": eid("sensor", f"sensor_{s}_{KEY_USERS}"),
            "rdp": eid("sensor", f"sensor_{s}_{KEY_RDP}"),
            "cpu": eid("sensor", f"sensor_{s}_{KEY_CPU}"),
            "cam": eid("sensor", f"sensor_{s}_{KEY_CAM}"),
            "mic": eid("sensor", f"sensor_{s}_{KEY_MIC}"),
            "sleep_blocked": eid("sensor", f"sensor_{s}_{KEY_SLEEP_BLOCKED}"),
            "uptime": eid("sensor", f"sensor_{s}_{KEY_UPTIME}"),
            "session": eid("sensor", f"sensor_{s}_{KEY_SESSION}"),
            "media": eid("media_player", f"media_player_{s}"),
            "notify": eid("notify", f"notify_{s}"),
            "shutdown": eid("button", f"button_{s}_shutdown"),
            "hibernate": eid("button", f"button_{s}_hibernate"),
            "sleep": eid("button", f"button_{s}_sleep"),
            "cancel": eid("button", f"button_{s}_restart_cancel"),
        }
        dev = self.agent_device(pc)
        area = (dev.area_id if dev else None) or ""
        pc.room = ROOM_CODES.get(area, "haus")

    def _st(self, pc: PcState, key: str):
        eid = pc.entities.get(key)
        return self.hass.states.get(eid) if eid else None

    # ------------------------------------------------------------------ tick
    @callback
    def _tick(self, _now=None) -> None:
        self.hass.async_create_task(self._async_tick())

    async def _async_tick(self) -> None:
        now = dt_util.utcnow()
        for pc in list(self.pcs.values()):
            try:
                await self._evaluate(pc, now)
            except Exception:  # noqa: BLE001 - one PC must not stop the others
                _LOGGER.exception("Fehler bei Rechner %s", pc.name)
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_refresh(self) -> None:
        await self._async_tick()

    def _activity(self, pc: PcState, now: datetime) -> tuple[list[str], datetime | None]:
        """Return reasons that keep the PC 'in use' right now, and the last input time."""
        crit = self.criteria(pc)
        reasons: list[str] = []
        last_input: datetime | None = None

        users = _number(self._st(pc, "users"))
        locked = _truthy(self._st(pc, "locked"))
        session = self._st(pc, "session")
        session_state = session.state if session else None

        if CRIT_INPUT in crit:
            idle = _number(self._st(pc, "idle"))
            if idle is not None:
                last_input = now - timedelta(seconds=max(0.0, idle))
                if idle < 60:
                    reasons.append("eingabe")
            elif (users or 0) > 0 and locked is not True and session_state not in ("disconnected",):
                # idle time unknown (tray app closed) but somebody is logged in and not locked:
                # be safe and treat as in use
                reasons.append("eingabe_unbekannt")

        if CRIT_RDP in crit:
            rdp = _number(self._st(pc, "rdp"))
            if (rdp or 0) > 0 and session_state not in ("disconnected",) and locked is not True:
                reasons.append("rdp")

        if CRIT_USERS in crit and (users or 0) > 0:
            reasons.append("benutzer")

        if CRIT_CPU in crit:
            cpu = _number(self._st(pc, "cpu"))
            if cpu is not None:
                pc.cpu.append((now, cpu))
            window = now - timedelta(minutes=max(1, int(opt(self.entry, OPT_CPU_MIN))))
            samples = [v for t, v in pc.cpu if t >= window]
            if samples and sum(samples) / len(samples) >= float(opt(self.entry, OPT_CPU_LIMIT)):
                reasons.append("cpu")

        if CRIT_MEDIA in crit:
            media = self._st(pc, "media")
            if media is not None and media.state == "playing":
                reasons.append("medien")

        if CRIT_CAMMIC in crit:
            if _truthy(self._st(pc, "cam")) or _truthy(self._st(pc, "mic")):
                reasons.append("kamera_mikrofon")

        if CRIT_DISPLAY in crit:
            sb = self._st(pc, "sleep_blocked")
            if sb is not None and sb.attributes.get("display_required") is True:
                reasons.append("anzeige_sperre")

        for eid in self.pc_cfg(pc, PC_EXTRA, []) or []:
            st = self.hass.states.get(eid)
            if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            num = _number(st)
            if (num is not None and num > 0) or str(st.state).lower() in TRUTHY:
                reasons.append(f"entitaet:{eid}")

        uptime = _number(self._st(pc, "uptime"))
        grace = int(opt(self.entry, OPT_BOOT_GRACE))
        if uptime is not None and grace > 0 and uptime < grace * 60:
            reasons.append("gerade_gestartet")

        return reasons, last_input

    async def _evaluate(self, pc: PcState, now: datetime) -> None:
        agent = self.agent_entry(pc)
        pc.agent_entry_id = agent.entry_id if agent else None
        self._resolve(pc)

        btn = self._st(pc, "shutdown")
        online = (agent is not None and agent.state is ConfigEntryState.LOADED
                  and btn is not None and btn.state != STATE_UNAVAILABLE)
        if online and not pc.online:
            # PC (re)appeared: start counting from now
            pc.last_activity = now
            pc.warned = False
            pc.cpu.clear()
            if pc.command_sent and now - pc.command_sent > timedelta(minutes=2):
                pc.command_sent = None
        pc.online = online

        if not online:
            pc.reasons = []
            pc.shutdown_at = None
            pc.inactive_since = None
            pc.warned = False
            pc.status = ST_SHUTDOWN if pc.command_sent else ST_OFFLINE
            pc.exec_since = None
            pc.fire = False
            pc.rule_mode = self.is_rule_mode(pc)
            if pc.rule_mode:
                self._rule_results(pc)
            return

        pc.rule_mode = self.is_rule_mode(pc)
        if pc.rule_mode:
            await self._evaluate_rules(pc, now)
        else:
            pc.conditions = []
            await self._evaluate_standard(pc, now)

    # ------------------------------------------------------------- rule mode
    def _rule_results(self, pc: PcState) -> tuple[list[bool], list[bool], bool]:
        pc.conditions = []
        res: dict[str, list[bool]] = {PC_RULE_ACTIVE: [], PC_EXEC: []}
        for group in (PC_RULE_ACTIVE, PC_EXEC):
            for cond in self.pc_cfg(pc, group, []) or []:
                ok, cur = rules.check(self.hass, cond, pc.online)
                res[group].append(ok)
                pc.conditions.append({"gruppe": "aktiv_wenn" if group == PC_RULE_ACTIVE else "ausfuehren_wenn",
                                      "bedingung": rules.describe(self.hass, cond), "entitaet": cond.get("entity"),
                                      "ist": cur, "erfuellt": ok})
        paused = False
        pause = self.pc_cfg(pc, PC_PAUSE)
        if pause:
            st = self.hass.states.get(pause)
            paused = st is not None and str(st.state).lower() in TRUTHY
        return res[PC_RULE_ACTIVE], res[PC_EXEC], paused

    async def _stop_pending(self, pc: PcState, now: datetime) -> None:
        pc.exec_since = None
        pc.fire = False
        pc.shutdown_at = None
        if pc.warned or pc.command_sent:
            await self._cancel(pc, now)

    async def _evaluate_rules(self, pc: PcState, now: datetime) -> None:
        act, exe, paused = self._rule_results(pc)
        pc.reasons = []
        armed = rules.combine(act, self.pc_cfg(pc, PC_RULE_LOGIC, "alle"))
        if not self.enabled(pc):
            pc.status = ST_EXEMPT
        elif not opt(self.entry, OPT_ENABLED):
            pc.status = ST_PAUSED
        elif paused:
            pc.status = ST_RULE_PAUSED
        elif not in_window(self.entry, dt_util.as_local(now)):
            pc.status = ST_OUTSIDE
        elif not armed:
            pc.status = ST_NOT_ARMED
        elif not exe:
            # no own execute conditions: built-in idle logic decides, rule only arms it
            await self._evaluate_standard(pc, now)
            return
        else:
            pc.status = ""
        if pc.status:
            pc.inactive_since = None
            await self._stop_pending(pc, now)
            return

        pc.fire = rules.combine(exe, self.pc_cfg(pc, PC_EXEC_LOGIC, "alle"))
        if not pc.fire:
            await self._stop_pending(pc, now)
            pc.inactive_since = None
            pc.status = ST_ARMED
            return
        if pc.exec_since is None:
            pc.exec_since = now
        pc.inactive_since = pc.exec_since
        pc.shutdown_at = pc.exec_since + timedelta(minutes=self.warn_minutes(pc))
        if pc.command_sent:
            if opt(self.entry, OPT_DRY_RUN) or now - pc.command_sent < RETRY_AFTER:
                pc.status = ST_SHUTDOWN
                return
            pc.command_sent = None
            pc.exec_since = now
            pc.shutdown_at = now + timedelta(minutes=self.warn_minutes(pc))
        if now >= pc.shutdown_at:
            await self._shutdown(pc, now, "regel")
            return
        if not pc.warned:
            await self._warn(pc, pc.shutdown_at - now)
        pc.status = ST_WARNING

    # ---------------------------------------------------------- standard mode
    async def _evaluate_standard(self, pc: PcState, now: datetime) -> None:
        reasons, last_input = self._activity(pc, now)
        pc.reasons = reasons
        # input alone is no "blocker": its time is taken from the idle counter
        blockers = [r for r in reasons if r != "eingabe"]
        if blockers:
            pc.last_activity = now
        since = pc.last_activity
        if last_input is not None and last_input > since:
            since = last_input
        pc.inactive_since = since

        limit = timedelta(minutes=self.idle_limit(pc))
        warn = timedelta(minutes=self.warn_minutes(pc))
        inactive = now - since
        pc.shutdown_at = since + limit

        active_now = bool(reasons) or inactive < timedelta(minutes=1)

        # activity came back after a warning or a command -> cancel
        if (pc.warned or pc.command_sent) and inactive < max(timedelta(minutes=1), limit - warn):
            await self._cancel(pc, now)

        if not self.enabled(pc):
            pc.status = ST_EXEMPT
            pc.shutdown_at = None
            return
        if not opt(self.entry, OPT_ENABLED):
            pc.status = ST_PAUSED
            pc.shutdown_at = None
            return
        if not in_window(self.entry, dt_util.as_local(now)):
            pc.status = ST_OUTSIDE if not active_now else ST_ACTIVE
            pc.shutdown_at = None
            return

        if pc.command_sent:
            # dry run: report once per idle phase, a real command is retried after RETRY_AFTER
            if opt(self.entry, OPT_DRY_RUN) or now - pc.command_sent < RETRY_AFTER:
                pc.status = ST_SHUTDOWN
                return
            pc.command_sent = None      # still online after the retry time: try again

        if inactive >= limit:
            await self._shutdown(pc, now, "inaktiv")
            return
        if warn and inactive >= limit - warn:
            if not pc.warned:
                await self._warn(pc, limit - inactive)
            pc.status = ST_WARNING
            return
        pc.status = ST_ACTIVE if active_now else ST_IDLE

    # --------------------------------------------------------------- actions
    async def _notify_pc(self, pc: PcState, title: str, message: str) -> None:
        eid = pc.entities.get("notify")
        if not eid:
            return
        try:
            await self.hass.services.async_call(
                "notify", "send_message", {"entity_id": eid, "title": title, "message": message}, blocking=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Benachrichtigung an %s fehlgeschlagen: %s", pc.name, err)

    async def _notify_ha(self, message: str) -> None:
        target = (opt(self.entry, OPT_NOTIFY) or "").strip()
        if not target:
            return
        domain, _, service = target.partition(".")
        if not service:
            domain, service = "notify", domain
        try:
            await self.hass.services.async_call(domain, service, {"title": "PC-Abschaltung", "message": message},
                                                blocking=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Benachrichtigung %s fehlgeschlagen: %s", target, err)

    def _fire(self, pc: PcState, kind: str, **extra) -> None:
        self.hass.bus.async_fire(EVENT, {"type": kind, "pc": pc.name, "serial": pc.serial,
                                         "dry_run": bool(opt(self.entry, OPT_DRY_RUN)), **extra})

    async def _warn(self, pc: PcState, remaining: timedelta) -> None:
        pc.warned = True
        mins = max(1, round(remaining.total_seconds() / 60))
        verb = {"shutdown": "heruntergefahren", "hibernate": "in den Ruhezustand versetzt",
                "sleep": "in den Energiesparmodus versetzt"}.get(self.action(pc), "heruntergefahren")
        dry = opt(self.entry, OPT_DRY_RUN)
        _LOGGER.info("%s: Warnung, Abschaltung in %s min%s", pc.name, mins, " (Probelauf)" if dry else "")
        if not dry:
            await self._notify_pc(pc, "Automatische Abschaltung",
                                  f"Dieser Rechner wird wegen Inaktivität in {mins} Minuten {verb}. "
                                  "Maus oder Tastatur benutzen, um das zu verhindern.")
        self._fire(pc, "warning", minutes=mins)

    async def _shutdown(self, pc: PcState, now: datetime, why: str) -> None:
        action = self.action(pc)
        button = pc.entities.get(action) or pc.entities.get("shutdown")
        pc.command_sent = now
        pc.last_command = action
        pc.status = ST_SHUTDOWN
        dry = bool(opt(self.entry, OPT_DRY_RUN))
        mins = round(pc.inactive_minutes)
        if dry:
            _LOGGER.warning("Probelauf: %s würde jetzt abgeschaltet (%s, %s min inaktiv)", pc.name, action, mins)
            await self._notify_ha(f"Probelauf: {pc.name} würde jetzt abgeschaltet ({mins} min inaktiv).")
        else:
            _LOGGER.warning("%s wird abgeschaltet (%s, %s min inaktiv, Grund: %s)", pc.name, action, mins, why)
            if button:
                await self.hass.services.async_call("button", "press", {"entity_id": button}, blocking=False)
            await self._notify_ha(f"{pc.name} wurde nach {mins} Minuten Inaktivität abgeschaltet.")
        self._fire(pc, "shutdown", action=action, reason=why, minutes=mins)

    async def _cancel(self, pc: PcState, now: datetime) -> None:
        was_cmd = pc.command_sent
        pc.exec_since = None
        pc.warned = False
        if was_cmd and not opt(self.entry, OPT_DRY_RUN) and pc.last_command == "shutdown" \
                and now - was_cmd < CANCEL_WINDOW and pc.entities.get("cancel"):
            await self.hass.services.async_call("button", "press", {"entity_id": pc.entities["cancel"]},
                                                blocking=False)
            await self._notify_pc(pc, "Automatische Abschaltung", "Abschaltung abgebrochen.")
        pc.command_sent = None
        self._fire(pc, "cancelled")

    # ---------------------------------------------------------- user actions
    async def async_reset_timer(self, subentry_id: str) -> None:
        pc = self.pcs.get(subentry_id)
        if pc:
            pc.last_activity = dt_util.utcnow()
            await self._cancel(pc, dt_util.utcnow())
            await self._async_tick()

    async def async_shutdown_now(self, subentry_id: str) -> None:
        pc = self.pcs.get(subentry_id)
        if pc and pc.online:
            await self._shutdown(pc, dt_util.utcnow(), "manuell")
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)
