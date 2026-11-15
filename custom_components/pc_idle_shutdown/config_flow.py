"""Config flow, options flow and PC subentry flow."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, OptionsFlow, SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector, EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig,
    NumberSelectorMode, SelectSelector, SelectSelectorConfig, SelectSelectorMode, TextSelector,
    TimeSelector,
)

from .const import (
    ACTIONS, CRITERIA, DEFAULT_CRITERIA, DEFAULTS, DOMAIN, OPT_ACTION, OPT_BOOT_GRACE, OPT_CPU_LIMIT,
    OPT_CPU_MIN, OPT_CRITERIA, OPT_DAYS, OPT_DRY_RUN, OPT_ENABLED, OPT_FROM, OPT_IDLE_MIN, OPT_IGNORED,
    OPT_NEW_ENABLED, OPT_NOTIFY, OPT_TO, OPT_WARN_MIN, PC_ACTION, PC_AGENT, PC_CRITERIA, PC_ENABLED,
    PC_ANGEPASST, PC_EXEC, PC_EXEC_LOGIC, PC_EXTRA, PC_IDLE_MIN, PC_OWN_CRITERIA, PC_PAUSE,
    PC_RULE_ACTIVE, PC_RULE_LOGIC, PC_TEMPLATE, PC_WARN, SUBENTRY_PC, SUBENTRY_TEMPLATE, TPL_AUTO, TPL_REF,
    WEEKDAYS,
)
from . import rules as R

START_EXEMPT = "start_ausnahmen"
EXEMPT = "ausnahmen"


def _num(lo: int, hi: int, unit: str | None = "min") -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=lo, max=hi, step=1, mode=NumberSelectorMode.BOX,
                                               unit_of_measurement=unit))


def _select(options: list[str], key: str, multiple: bool = False, dropdown: bool = True) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(
        options=options, translation_key=key, multiple=multiple,
        mode=SelectSelectorMode.DROPDOWN if dropdown else SelectSelectorMode.LIST))


def _pc_select(choices: dict[str, str], multiple: bool = True) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(
        options=[{"value": k, "label": v} for k, v in sorted(choices.items(), key=lambda kv: kv[1].lower())],
        multiple=multiple, mode=SelectSelectorMode.LIST))


def _global_schema(o: dict) -> vol.Schema:
    g = {**DEFAULTS, OPT_CRITERIA: DEFAULT_CRITERIA, **o}
    return vol.Schema({
        vol.Required(OPT_ENABLED, default=g[OPT_ENABLED]): BooleanSelector(),
        vol.Required(OPT_DRY_RUN, default=g[OPT_DRY_RUN]): BooleanSelector(),
        vol.Required(OPT_IDLE_MIN, default=g[OPT_IDLE_MIN]): _num(5, 1440),
        vol.Required(OPT_WARN_MIN, default=g[OPT_WARN_MIN]): _num(0, 60),
        vol.Required(OPT_ACTION, default=g[OPT_ACTION]): _select(ACTIONS, "aktion"),
        vol.Required(OPT_CRITERIA, default=g[OPT_CRITERIA]): _select(CRITERIA, "kriterien", True, False),
        vol.Required(OPT_CPU_LIMIT, default=g[OPT_CPU_LIMIT]): _num(1, 100, "%"),
        vol.Required(OPT_CPU_MIN, default=g[OPT_CPU_MIN]): _num(1, 60),
        vol.Required(OPT_BOOT_GRACE, default=g[OPT_BOOT_GRACE]): _num(0, 240),
        vol.Required(OPT_FROM, default=g[OPT_FROM]): TimeSelector(),
        vol.Required(OPT_TO, default=g[OPT_TO]): TimeSelector(),
        vol.Required(OPT_DAYS, default=g[OPT_DAYS]): _select(WEEKDAYS, "wochentage", True, False),
        vol.Optional(OPT_NOTIFY, description={"suggested_value": g[OPT_NOTIFY]}): TextSelector(),
        vol.Required(OPT_NEW_ENABLED, default=g[OPT_NEW_ENABLED]): BooleanSelector(),
    })


def _clean_time(v: Any) -> str:
    return str(v or "00:00")[:5]


def _agents(hass) -> dict[str, str]:
    from . import agent_entries
    return {serial: e.title for serial, e in agent_entries(hass).items()}


class IdleShutdownConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IdleShutdownOptionsFlow:
        return IdleShutdownOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PC: PcSubentryFlow, SUBENTRY_TEMPLATE: TemplateSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        agents = _agents(self.hass)
        if user_input is not None:
            exempt = user_input.pop(START_EXEMPT, [])
            user_input[OPT_FROM] = _clean_time(user_input.get(OPT_FROM))
            user_input[OPT_TO] = _clean_time(user_input.get(OPT_TO))
            return self.async_create_entry(title="PC-Leerlauf-Abschaltung",
                                           data={START_EXEMPT: exempt}, options=user_input)
        schema = vol.Schema({
            vol.Required(OPT_IDLE_MIN, default=DEFAULTS[OPT_IDLE_MIN]): _num(5, 1440),
            vol.Required(OPT_WARN_MIN, default=DEFAULTS[OPT_WARN_MIN]): _num(0, 60),
            vol.Required(OPT_ACTION, default=DEFAULTS[OPT_ACTION]): _select(ACTIONS, "aktion"),
            vol.Required(OPT_DRY_RUN, default=False): BooleanSelector(),
            vol.Optional(START_EXEMPT, default=[]): _pc_select(agents),
        })
        return self.async_show_form(step_id="user", data_schema=schema,
                                    description_placeholders={"anzahl": str(len(agents)),
                                                              "rechner": ", ".join(sorted(agents.values())) or "–"})


class IdleShutdownOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["einstellungen", EXEMPT]
        if self.config_entry.options.get(OPT_IGNORED):
            menu.append("nicht_verwaltet")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_einstellungen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[OPT_FROM] = _clean_time(user_input.get(OPT_FROM))
            user_input[OPT_TO] = _clean_time(user_input.get(OPT_TO))
            user_input.setdefault(OPT_NOTIFY, "")
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        return self.async_show_form(step_id="einstellungen", data_schema=_global_schema(dict(self.config_entry.options)))

    async def async_step_ausnahmen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The list of PCs that stay on even when idle."""
        entry = self.config_entry
        subs = {s.subentry_id: s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_PC}
        if user_input is not None:
            keep_on = set(user_input.get(EXEMPT, []))
            for sid, sub in subs.items():
                want = sid not in keep_on
                if bool(sub.data.get(PC_ENABLED, True)) != want:
                    self.hass.config_entries.async_update_subentry(entry, sub, data={**sub.data, PC_ENABLED: want})
            return self.async_create_entry(data=dict(entry.options))
        current = [sid for sid, s in subs.items() if not s.data.get(PC_ENABLED, True)]
        schema = vol.Schema({vol.Optional(EXEMPT, default=current): _pc_select({k: s.title for k, s in subs.items()})})
        return self.async_show_form(step_id=EXEMPT, data_schema=schema)

    async def async_step_nicht_verwaltet(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        ignored = list(self.config_entry.options.get(OPT_IGNORED, []))
        if user_input is not None:
            keep = [s for s in ignored if s not in set(user_input.get(OPT_IGNORED, []))]
            # removed from the ignore list -> discovery adds them again
            return self.async_create_entry(data={**self.config_entry.options, OPT_IGNORED: keep})
        agents = _agents(self.hass)
        names = {s: agents.get(s, s) for s in ignored}
        schema = vol.Schema({vol.Optional(OPT_IGNORED, default=[]): _pc_select(names)})
        return self.async_show_form(step_id="nicht_verwaltet", data_schema=schema)


LOGIC = ["alle", "eine"]
PICK = "entitaet"
OTHER = "__andere__"


def _warn_num() -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=-1, max=60, step=1, mode=NumberSelectorMode.BOX,
                                               unit_of_measurement="min"))


def _fmt(v: Any) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


class RuleEditor:
    """Condition editor shared by templates and PCs (menu based, works on a copy)."""

    _work: dict
    _target: str = PC_RULE_ACTIVE
    _pick: dict
    is_template = False

    # -- to be provided by the flow
    def _serial(self) -> str | None:
        raise NotImplementedError

    def _menu(self) -> list[str]:
        raise NotImplementedError

    def _title(self) -> str:
        raise NotImplementedError

    def _online(self) -> bool:
        return True

    # -- overview text
    def _overview(self) -> str:
        w = self._work
        lines = []
        for group, head, logic in ((PC_RULE_ACTIVE, "Regel aktiv, wenn", PC_RULE_LOGIC),
                                   (PC_EXEC, "Regel ausführen, wenn", PC_EXEC_LOGIC)):
            word = "eine der Bedingungen" if w.get(logic) == "eine" else "alle Bedingungen"
            lines.append(f"**{head}** ({word}):")
            conds = w.get(group) or []
            if not conds:
                lines.append("- (keine)" if group == PC_RULE_ACTIVE else
                         "- (keine: eingebaute Leerlauf-Logik entscheidet)")
            for c in conds:
                text = R.describe(self.hass, c, by_key=self.is_template)
                if not self.is_template:
                    ok, cur = R.check(self.hass, c, self._online())
                    text = f"{'✅' if ok else '❌'} {text}  (jetzt: {cur})"
                lines.append(f"- {text}")
            lines.append("")
        if not self.is_template:
            pause = w.get(PC_PAUSE)
            lines.append(f"**Pausiert durch:** {R.friendly(self.hass, pause) if pause else '(nichts)'}")
            if w.get(PC_TEMPLATE):
                tpl = self._get_entry().subentries.get(w[PC_TEMPLATE])
                state = "angepasst – Änderungen der Vorlage werden nicht übernommen" if w.get(PC_ANGEPASST) \
                    else "folgt der Vorlage"
                lines.append(f"**Vorlage:** {tpl.title if tpl else 'gelöscht'} ({state})")
        else:
            lines.append("**Automatisch auf Rechner ohne Vorlage anwenden:** "
                         + ("ja" if self._work.get(TPL_AUTO) else "nein"))
        return "\n".join(lines)

    async def async_step_menu(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(step_id="menu", menu_options=self._menu(),
                                    description_placeholders={"titel": self._title(), "uebersicht": self._overview()})

    async def async_step_bed_aktiv(self, user_input: dict[str, Any] | None = None):
        self._target = PC_RULE_ACTIVE
        return await self.async_step_bed_entitaet()

    async def async_step_bed_ausfuehren(self, user_input: dict[str, Any] | None = None):
        self._target = PC_EXEC
        return await self.async_step_bed_entitaet()

    async def async_step_bed_entitaet(self, user_input: dict[str, Any] | None = None):
        serial = self._serial()
        ents = R.pc_entities(self.hass, serial) if serial else []
        if user_input is not None:
            choice = user_input[PICK]
            if choice == OTHER:
                return await self.async_step_bed_fremd()
            if choice == R.ONLINE:
                self._pick = {"key": R.ONLINE, "entity": R.ONLINE}
            elif self.is_template:
                self._pick = {"key": choice, "entity": R.resolve_key(self.hass, serial, choice) if serial else None}
            else:
                key = next((k for k, e in ents if e == choice), f"{R.FIXED}{choice}")
                self._pick = {"key": key, "entity": choice}
            return await self.async_step_bed_wert()
        options = [{"value": R.ONLINE, "label": R.friendly(self.hass, R.ONLINE)}]
        options += [{"value": k if self.is_template else e, "label": R.label(self.hass, e)} for k, e in ents]
        options.append({"value": OTHER, "label": "Andere Entität (nicht vom Rechner) …"})
        schema = vol.Schema({vol.Required(PICK): SelectSelector(SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="bed_entitaet", data_schema=schema, description_placeholders={
            "gruppe": "Regel aktiv, wenn" if self._target == PC_RULE_ACTIVE else "Regel ausführen, wenn",
            "rechner": next((n for s, n in _agents(self.hass).items() if s == serial), "–")})

    async def async_step_bed_fremd(self, user_input: dict[str, Any] | None = None):
        if user_input is not None and user_input.get(PICK):
            eid = user_input[PICK]
            self._pick = {"key": f"{R.FIXED}{eid}", "entity": eid}
            return await self.async_step_bed_wert()
        schema = vol.Schema({vol.Required(PICK): EntitySelector(EntitySelectorConfig())})
        return self.async_show_form(step_id="bed_fremd", data_schema=schema)

    async def async_step_bed_wert(self, user_input: dict[str, Any] | None = None):
        eid = self._pick.get("entity")
        k = R.kind(self.hass, eid) if eid else "text"
        ops = R.ops_for(k)
        errors: dict[str, str] = {}
        if user_input is not None and "op" in user_input:
            op = user_input["op"]
            val = user_input.get("wert")
            if op not in R.NO_VALUE and (val is None or str(val).strip() == ""):
                errors["wert"] = "wert_fehlt"
            else:
                cond = {"key": self._pick["key"], "name": R.friendly(self.hass, eid) if eid else self._pick["key"],
                        "op": op, "value": None if op in R.NO_VALUE else _fmt(val)}
                if not self.is_template:
                    cond["entity"] = eid
                    self._work[PC_ANGEPASST] = True
                self._work[self._target] = [*(self._work.get(self._target) or []), cond]
                return await self.async_step_menu()
        fields: dict = {vol.Required("op", default=ops[0]): SelectSelector(SelectSelectorConfig(
            options=ops, translation_key="op", mode=SelectSelectorMode.DROPDOWN))}
        st = self.hass.states.get(eid) if eid and eid != R.ONLINE else None
        if k == "num":
            unit = st.attributes.get("unit_of_measurement") if st else None
            cfg = NumberSelectorConfig(mode=NumberSelectorMode.BOX, step="any")
            if unit:
                cfg["unit_of_measurement"] = unit
            fields[vol.Optional("wert")] = NumberSelector(cfg)
        elif k == "enum":
            fields[vol.Optional("wert")] = SelectSelector(SelectSelectorConfig(
                options=R.enum_options(self.hass, eid), custom_value=True, mode=SelectSelectorMode.DROPDOWN))
        elif k == "text":
            fields[vol.Optional("wert", description={"suggested_value": st.state if st else None})] = TextSelector()
        art = {"num": "Zahl", "bool": "an/aus", "enum": "Auswahl", "text": "Text"}[k]
        return self.async_show_form(step_id="bed_wert", data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders={
                                        "name": R.friendly(self.hass, eid) if eid else self._pick.get("key", "–"),
                                        "aktuell": R.current(self.hass, eid) if eid and eid != R.ONLINE else "–",
                                        "art": art})

    async def async_step_bed_entfernen(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            drop = set(user_input.get("bedingungen", []))
            for group in (PC_RULE_ACTIVE, PC_EXEC):
                conds = self._work.get(group) or []
                keep = [c for i, c in enumerate(conds) if f"{group}|{i}" not in drop]
                if len(keep) != len(conds):
                    self._work[group] = keep
                    if not self.is_template:
                        self._work[PC_ANGEPASST] = True
            return await self.async_step_menu()
        options = []
        for group, head in ((PC_RULE_ACTIVE, "aktiv wenn"), (PC_EXEC, "ausführen wenn")):
            for i, c in enumerate(self._work.get(group) or []):
                options.append({"value": f"{group}|{i}",
                                "label": f"{head}: {R.describe(self.hass, c, by_key=self.is_template)}"})
        if not options:
            return await self.async_step_menu()
        schema = vol.Schema({vol.Optional("bedingungen", default=[]): SelectSelector(SelectSelectorConfig(
            options=options, multiple=True, mode=SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="bed_entfernen", data_schema=schema)


def _template_defaults(hass) -> dict:
    agents = _agents(hass)
    return {"name": "Neue Vorlage", TPL_REF: next(iter(sorted(agents, key=lambda s: agents[s].lower())), ""),
            PC_RULE_LOGIC: "alle", PC_EXEC_LOGIC: "alle", PC_ACTION: "global", PC_WARN: -1, TPL_AUTO: False,
            PC_RULE_ACTIVE: [], PC_EXEC: []}


class TemplateSubentryFlow(RuleEditor, ConfigSubentryFlow):
    """A template: conditions by entity *type*, applied to any number of PCs."""

    is_template = True
    _apply: list[str] | None = None

    def _serial(self) -> str | None:
        return self._work.get(TPL_REF) or None

    def _title(self) -> str:
        return self._work.get("name") or "Vorlage"

    def _reconf(self) -> bool:
        return self.source == "reconfigure"

    def _menu(self) -> list[str]:
        m = ["einstellungen", "bed_aktiv", "bed_ausfuehren", "bed_entfernen"]
        if self._reconf():
            m.append("anwenden")
        return [*m, "speichern"]

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if not _agents(self.hass):
            return self.async_abort(reason="keine_agenten")
        self._work = _template_defaults(self.hass)
        return await self.async_step_einstellungen()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        sub = self._get_reconfigure_subentry()
        self._work = {**_template_defaults(self.hass), "name": sub.title, **dict(sub.data)}
        return await self.async_step_menu()

    async def async_step_einstellungen(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            user_input[PC_WARN] = int(user_input.get(PC_WARN, -1))
            self._work.update(user_input)
            return await self.async_step_menu()
        w = self._work
        schema = vol.Schema({
            vol.Required("name", default=w["name"]): TextSelector(),
            vol.Required(TPL_REF, default=w.get(TPL_REF) or vol.UNDEFINED): _pc_select(_agents(self.hass), multiple=False),
            vol.Required(PC_RULE_LOGIC, default=w[PC_RULE_LOGIC]): _select(LOGIC, "logik"),
            vol.Required(PC_EXEC_LOGIC, default=w[PC_EXEC_LOGIC]): _select(LOGIC, "logik"),
            vol.Required(PC_ACTION, default=w[PC_ACTION]): _select(["global", *ACTIONS], "aktion"),
            vol.Required(PC_WARN, default=w[PC_WARN]): _warn_num(),
            vol.Required(TPL_AUTO, default=w[TPL_AUTO]): BooleanSelector(),
        })
        return self.async_show_form(step_id="einstellungen", data_schema=schema)

    async def async_step_anwenden(self, user_input: dict[str, Any] | None = None):
        entry = self._get_entry()
        pcs = {s.subentry_id: s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_PC}
        if user_input is not None:
            self._apply = list(user_input.get("rechner", []))
            return await self.async_step_menu()
        tid = self._get_reconfigure_subentry().subentry_id
        current = self._apply if self._apply is not None else [
            sid for sid, s in pcs.items() if s.data.get(PC_TEMPLATE) == tid]
        schema = vol.Schema({vol.Optional("rechner", default=current): _pc_select(
            {sid: s.title + ("  (angepasst)" if s.data.get(PC_ANGEPASST) else "") for sid, s in pcs.items()})})
        return self.async_show_form(step_id="anwenden", data_schema=schema)

    async def async_step_speichern(self, user_input: dict[str, Any] | None = None):
        title = (self._work.pop("name", None) or "Vorlage").strip()
        data = self._work
        if not self._reconf():
            return self.async_create_entry(title=title, data=data)
        entry = self._get_entry()
        sub = self._get_reconfigure_subentry()
        result = self.async_update_and_abort(entry, sub, title=title, data=data)
        if self._apply is not None:
            tpl = entry.subentries[sub.subentry_id]
            for sid in self._apply:
                pc = entry.subentries.get(sid)
                if pc is not None:
                    self.hass.config_entries.async_update_subentry(
                        entry, pc, data=R.template_to_pc(self.hass, tpl, dict(pc.data)))
        return result


class PcSubentryFlow(RuleEditor, ConfigSubentryFlow):
    """Add a PC (one that is not managed) or edit its settings and rules."""

    def _serial(self) -> str | None:
        return self._work.get(PC_AGENT)

    def _title(self) -> str:
        return self._get_reconfigure_subentry().title

    def _online(self) -> bool:
        mgr = getattr(self._get_entry(), "runtime_data", None)
        pc = mgr.pcs.get(self._get_reconfigure_subentry().subentry_id) if mgr else None
        return bool(pc and pc.online)

    def _menu(self) -> list[str]:
        return ["einstellungen", "vorlage_anwenden", "bed_aktiv", "bed_ausfuehren", "bed_entfernen", "speichern"]

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        from . import new_pc_data, pc_subentries
        entry = self._get_entry()
        have = pc_subentries(entry)
        free = {s: n for s, n in _agents(self.hass).items() if s not in have}
        if not free:
            return self.async_abort(reason="keine_rechner")
        if user_input is not None:
            serial = user_input[PC_AGENT]
            ignored = [s for s in entry.options.get(OPT_IGNORED, []) if s != serial]
            if ignored != list(entry.options.get(OPT_IGNORED, [])):
                self.hass.config_entries.async_update_entry(entry, options={**entry.options, OPT_IGNORED: ignored})
            return self.async_create_entry(title=free[serial], unique_id=serial,
                                           data=new_pc_data(serial, user_input.get(PC_ENABLED, True)))
        schema = vol.Schema({
            vol.Required(PC_AGENT): _pc_select(free, multiple=False),
            vol.Required(PC_ENABLED, default=True): BooleanSelector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        from . import new_pc_data
        sub = self._get_reconfigure_subentry()
        self._work = {**new_pc_data(sub.data[PC_AGENT], True), **dict(sub.data)}
        return await self.async_step_menu()

    async def async_step_einstellungen(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        w = self._work
        if user_input is not None:
            user_input.setdefault(PC_PAUSE, "")
            user_input.setdefault(PC_EXTRA, [])
            user_input[PC_IDLE_MIN] = int(user_input.get(PC_IDLE_MIN) or 0)
            user_input[PC_WARN] = int(user_input.get(PC_WARN, -1))
            if (user_input.get(PC_RULE_LOGIC) != w.get(PC_RULE_LOGIC)
                    or user_input.get(PC_EXEC_LOGIC) != w.get(PC_EXEC_LOGIC)):
                w[PC_ANGEPASST] = True
            if w.get(PC_TEMPLATE) and (user_input.get(PC_ACTION) != w.get(PC_ACTION)
                                       or user_input.get(PC_WARN) != w.get(PC_WARN)):
                w[PC_ANGEPASST] = True
            w.update(user_input)
            return await self.async_step_menu()
        schema = vol.Schema({
            vol.Required(PC_ENABLED, default=w.get(PC_ENABLED, True)): BooleanSelector(),
            vol.Optional(PC_PAUSE, description={"suggested_value": w.get(PC_PAUSE) or None}):
                EntitySelector(EntitySelectorConfig()),
            vol.Required(PC_RULE_LOGIC, default=w.get(PC_RULE_LOGIC, "alle")): _select(LOGIC, "logik"),
            vol.Required(PC_EXEC_LOGIC, default=w.get(PC_EXEC_LOGIC, "alle")): _select(LOGIC, "logik"),
            vol.Required(PC_ACTION, default=w.get(PC_ACTION, "global")): _select(["global", *ACTIONS], "aktion"),
            vol.Required(PC_WARN, default=w.get(PC_WARN, -1) if w.get(PC_WARN) is not None else -1): _warn_num(),
            vol.Required(PC_IDLE_MIN, default=w.get(PC_IDLE_MIN, 0)): _num(0, 1440),
            vol.Required(PC_OWN_CRITERIA, default=w.get(PC_OWN_CRITERIA, False)): BooleanSelector(),
            vol.Optional(PC_CRITERIA, default=w.get(PC_CRITERIA) or DEFAULT_CRITERIA):
                _select(CRITERIA, "kriterien", True, False),
            vol.Optional(PC_EXTRA, default=w.get(PC_EXTRA, [])): EntitySelector(EntitySelectorConfig(multiple=True)),
        })
        return self.async_show_form(step_id="einstellungen", data_schema=schema,
                                    description_placeholders={"rechner": self._title()})

    async def async_step_vorlage_anwenden(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        tpls = R.templates(self._get_entry())
        if user_input is not None:
            tid = user_input.get(PC_TEMPLATE) or ""
            if tid and tid in tpls:
                self._work = R.template_to_pc(self.hass, tpls[tid], self._work)
            else:
                self._work.update({PC_TEMPLATE: "", PC_ANGEPASST: False, PC_RULE_ACTIVE: [], PC_EXEC: []})
            return await self.async_step_menu()
        options = [{"value": "", "label": "Keine Vorlage – Regeln entfernen (eingebaute Leerlauf-Logik)"}]
        options += [{"value": tid, "label": t.title} for tid, t in sorted(tpls.items(), key=lambda kv: kv[1].title.lower())]
        cur = self._work.get(PC_TEMPLATE) if self._work.get(PC_TEMPLATE) in tpls else ""
        schema = vol.Schema({vol.Optional(PC_TEMPLATE, default=cur): SelectSelector(SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="vorlage_anwenden", data_schema=schema)

    async def async_step_speichern(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return self.async_update_and_abort(self._get_entry(), self._get_reconfigure_subentry(), data=self._work)
