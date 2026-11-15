"""Rule conditions, entity lists of a PC and templates (Vorlagen).

A template stores conditions by *key* – the part of a HASS.Agent unique_id after the
PC serial ("sensor:idle_time_seconds"), so it fits every PC. Applied to a PC, each key
is resolved to that PC's entity_id. Fixed entities ("entity:<entity_id>") stay the same
for all PCs, "agent:online" means "the PC is reachable".
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import (
    AGENT_DOMAIN, PC_ACTION, PC_AGENT, PC_ANGEPASST, PC_EXEC, PC_EXEC_LOGIC, PC_RULE_ACTIVE,
    PC_RULE_LOGIC, PC_TEMPLATE, PC_WARN, SUBENTRY_PC, SUBENTRY_TEMPLATE, TPL_AUTO,
)

ONLINE = "agent:online"
FIXED = "entity:"
SKIP_DOMAINS = {"button", "notify", "event"}

TRUTHY = {"on", "true", "yes", "1", "locked", "active", "playing", "home", "open", "connected"}
OPS_NUM = ["ge", "gt", "le", "lt", "eq", "ne", "unavailable", "available"]
OPS_BOOL = ["on", "off", "unavailable", "available"]
OPS_ENUM = ["eq", "ne", "unavailable", "available"]
OPS_TEXT = ["eq", "ne", "contains", "not_contains", "unavailable", "available"]
OP_SYMBOL = {"ge": "≥", "gt": ">", "le": "≤", "lt": "<", "eq": "=", "ne": "≠", "contains": "enthält",
             "not_contains": "enthält nicht", "on": "ist an", "off": "ist aus",
             "unavailable": "nicht verfügbar", "available": "verfügbar"}
NO_VALUE = {"on", "off", "unavailable", "available"}


# ------------------------------------------------------------------ entity lists
def agent_entry_for(hass: HomeAssistant, serial: str) -> ConfigEntry | None:
    for e in hass.config_entries.async_entries(AGENT_DOMAIN):
        if e.unique_id == serial:
            return e
    return None


def key_of(entity: er.RegistryEntry, serial: str) -> str | None:
    prefix = f"{entity.domain}_{serial}"
    uid = entity.unique_id or ""
    if not uid.startswith(prefix):
        return None
    return f"{entity.domain}:{uid[len(prefix):].lstrip('_')}"


def resolve_key(hass: HomeAssistant, serial: str, key: str) -> str | None:
    """Template key -> entity_id of this PC."""
    if key == ONLINE:
        return ONLINE
    if key.startswith(FIXED):
        return key[len(FIXED):]
    domain, _, suffix = key.partition(":")
    uid = f"{domain}_{serial}" + (f"_{suffix}" if suffix else "")
    return er.async_get(hass).async_get_entity_id(domain, AGENT_DOMAIN, uid)


def pc_entities(hass: HomeAssistant, serial: str) -> list[tuple[str, str]]:
    """(key, entity_id) of all useful entities of a PC, sorted by name."""
    agent = agent_entry_for(hass, serial)
    if agent is None:
        return []
    out = []
    for ent in er.async_entries_for_config_entry(er.async_get(hass), agent.entry_id):
        if ent.domain in SKIP_DOMAINS or ent.disabled_by:
            continue
        key = key_of(ent, serial)
        if key:
            out.append((key, ent.entity_id))
    return sorted(out, key=lambda kv: label(hass, kv[1]).lower())


def friendly(hass: HomeAssistant, eid: str) -> str:
    if eid == ONLINE:
        return "Rechner eingeschaltet / erreichbar"
    st = hass.states.get(eid)
    return (st.attributes.get("friendly_name") if st else None) or eid


def current(hass: HomeAssistant, eid: str) -> str:
    st = hass.states.get(eid)
    if st is None:
        return "–"
    unit = st.attributes.get("unit_of_measurement")
    return f"{st.state} {unit}" if unit else st.state


def label(hass: HomeAssistant, eid: str) -> str:
    return friendly(hass, eid) if eid == ONLINE else f"{friendly(hass, eid)}  ({current(hass, eid)})"


# ------------------------------------------------------------------- value kinds
def kind(hass: HomeAssistant, eid: str) -> str:
    """bool | enum | num | text – decides operators and the value field."""
    if eid == ONLINE:
        return "bool"
    domain = eid.split(".")[0]
    st = hass.states.get(eid)
    if domain in ("binary_sensor", "switch", "input_boolean", "light", "fan", "update"):
        return "bool"
    if st is not None and isinstance(st.attributes.get("options"), list):
        return "enum"
    if domain == "media_player":
        return "enum"
    if st is not None:
        if st.attributes.get("unit_of_measurement") or st.attributes.get("state_class"):
            return "num"
        try:
            float(st.state)
            return "num"
        except (TypeError, ValueError):
            pass
        if str(st.state).lower() in TRUTHY | {"off", "false", "no", "0", "unlocked"}:
            return "bool"
    return "text"


def ops_for(k: str) -> list[str]:
    return {"num": OPS_NUM, "bool": OPS_BOOL, "enum": OPS_ENUM}.get(k, OPS_TEXT)


def enum_options(hass: HomeAssistant, eid: str) -> list[str]:
    st = hass.states.get(eid)
    if st is None:
        return []
    if isinstance(st.attributes.get("options"), list):
        return [str(o) for o in st.attributes["options"]]
    if eid.startswith("media_player."):
        return ["playing", "paused", "idle", "on", "off", "standby"]
    return [st.state]


# --------------------------------------------------------------------- checking
def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check(hass: HomeAssistant, cond: dict, online: bool) -> tuple[bool, str]:
    """Return (fulfilled, current value as text)."""
    eid, op, val = cond.get("entity"), cond.get("op", "eq"), cond.get("value")
    if eid == ONLINE:
        state: str | None = "on" if online else "off"
    elif not eid:
        return False, "Entität fehlt"
    else:
        st: State | None = hass.states.get(eid)
        state = None if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) else str(st.state)
    shown = state if state is not None else "nicht verfügbar"
    if op == "available":
        return state is not None, shown
    if op == "unavailable":
        return state is None, shown
    if state is None:
        return False, shown
    low = state.lower()
    if op == "on":
        return low in TRUTHY, shown
    if op == "off":
        return low not in TRUTHY, shown
    a, b = _num(state), _num(val)
    if op in ("eq", "ne"):
        same = (a == b) if a is not None and b is not None else low == str(val or "").strip().lower()
        return (same if op == "eq" else not same), shown
    if op in ("gt", "ge", "lt", "le"):
        if a is None or b is None:
            return False, shown
        return {"gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[op], shown
    if op == "contains":
        return str(val or "").lower() in low, shown
    if op == "not_contains":
        return str(val or "").lower() not in low, shown
    return False, shown


def combine(results: list[bool], logic: str) -> bool:
    if not results:
        return True
    return any(results) if logic == "eine" else all(results)


def describe(hass: HomeAssistant, cond: dict, by_key: bool = False) -> str:
    target = cond.get("key") if by_key else cond.get("entity")
    name = cond.get("name") or (friendly(hass, target) if target and not by_key else str(target))
    op = cond.get("op", "eq")
    val = "" if op in NO_VALUE else f" {cond.get('value')}"
    return f"{name} {OP_SYMBOL.get(op, op)}{val}"


# -------------------------------------------------------------------- templates
def templates(entry: ConfigEntry) -> dict[str, ConfigSubentry]:
    return {s.subentry_id: s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_TEMPLATE}


def resolve_conditions(hass: HomeAssistant, serial: str, conds: list[dict]) -> list[dict]:
    out = []
    for c in conds or []:
        out.append({"key": c.get("key"), "name": c.get("name"),
                    "entity": resolve_key(hass, serial, c.get("key") or ""),
                    "op": c.get("op"), "value": c.get("value")})
    return out


def template_to_pc(hass: HomeAssistant, tpl: ConfigSubentry, pc_data: dict) -> dict:
    """PC data with the template applied (entities resolved for this PC)."""
    t = tpl.data
    serial = pc_data[PC_AGENT]
    data = {**pc_data,
            PC_TEMPLATE: tpl.subentry_id, PC_ANGEPASST: False,
            PC_RULE_LOGIC: t.get(PC_RULE_LOGIC, "alle"), PC_EXEC_LOGIC: t.get(PC_EXEC_LOGIC, "alle"),
            PC_RULE_ACTIVE: resolve_conditions(hass, serial, t.get(PC_RULE_ACTIVE, [])),
            PC_EXEC: resolve_conditions(hass, serial, t.get(PC_EXEC, []))}
    if t.get(PC_ACTION, "global") != "global":
        data[PC_ACTION] = t[PC_ACTION]
    if t.get(PC_WARN, -1) is not None and int(t.get(PC_WARN, -1)) >= 0:
        data[PC_WARN] = int(t[PC_WARN])
    return data


def sync_templates(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Keep PCs in line with their template (unless edited) and give automatic templates to
    PCs without one. Returns the number of changed PCs."""
    tpls = templates(entry)
    auto = sorted((t for t in tpls.values() if t.data.get(TPL_AUTO)), key=lambda t: t.title.lower())
    changed = 0
    for sub in list(entry.subentries.values()):
        if sub.subentry_type != SUBENTRY_PC or sub.data.get(PC_ANGEPASST):
            continue
        tid = sub.data.get(PC_TEMPLATE)
        tpl = tpls.get(tid) if tid else None
        if tpl is None and not tid and auto:
            tpl = auto[0]
        if tpl is None:
            continue
        new = template_to_pc(hass, tpl, dict(sub.data))
        if new != dict(sub.data):
            hass.config_entries.async_update_subentry(entry, sub, data=new)
            changed += 1
    return changed
