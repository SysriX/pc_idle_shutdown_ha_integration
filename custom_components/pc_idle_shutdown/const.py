"""Constants for PC Idle Shutdown."""
from __future__ import annotations

DOMAIN = "pc_idle_shutdown"
AGENT_DOMAIN = "hass_agent"
SUBENTRY_PC = "pc"
SUBENTRY_TEMPLATE = "vorlage"

SIGNAL_UPDATE = f"{DOMAIN}_update"
EVENT = f"{DOMAIN}_event"

PLATFORMS = ["binary_sensor", "button", "number", "sensor", "switch"]

TICK_SECONDS = 20

# --- global options (entry.options) ---
OPT_ENABLED = "aktiv"                  # master switch
OPT_DRY_RUN = "probelauf"              # only report, never shut down
OPT_IDLE_MIN = "inaktiv_minuten"
OPT_WARN_MIN = "warn_minuten"
OPT_ACTION = "aktion"
OPT_CRITERIA = "kriterien"
OPT_CPU_LIMIT = "cpu_schwelle"
OPT_CPU_MIN = "cpu_minuten"
OPT_BOOT_GRACE = "nach_start_minuten"
OPT_FROM = "zeit_von"
OPT_TO = "zeit_bis"
OPT_DAYS = "wochentage"
OPT_WINDOWS = "zeitfenster"            # list of {id, name, von, bis, tage, aktiv}; none enabled = always
OPT_NOTIFY = "benachrichtigung"        # optional notify service for HA (e.g. notify.mobile_app_x)
OPT_IGNORED = "ignoriert"              # agent unique_ids the user removed (not managed)
OPT_NEW_ENABLED = "neue_abschalten"    # new PCs are switched to auto shutdown

DEFAULTS: dict = {
    OPT_ENABLED: True,
    OPT_DRY_RUN: False,
    OPT_IDLE_MIN: 30,
    OPT_WARN_MIN: 5,
    OPT_ACTION: "shutdown",
    OPT_CPU_LIMIT: 25,
    OPT_CPU_MIN: 5,
    OPT_BOOT_GRACE: 15,
    OPT_FROM: "00:00",
    OPT_TO: "00:00",
    OPT_DAYS: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    OPT_NOTIFY: "",
    OPT_IGNORED: [],
    OPT_WINDOWS: [],
    OPT_NEW_ENABLED: True,
}

# --- per PC (subentry.data) ---
PC_AGENT = "agent_unique_id"
PC_ENABLED = "abschalten"
PC_IDLE_MIN = "inaktiv_minuten"        # 0 = global
PC_ACTION = "aktion"                   # "global" | shutdown | sleep | hibernate
PC_OWN_CRITERIA = "eigene_kriterien"
PC_CRITERIA = "kriterien"
PC_EXTRA = "weitere_entitaeten"        # entities that keep the PC on while active
# rule mode (from a template, editable per PC)
PC_TEMPLATE = "vorlage"                # template subentry id ("" = none)
PC_ANGEPASST = "angepasst"             # edited by hand -> template changes are not taken over
PC_RULE_LOGIC = "aktiv_logik"          # "alle" | "eine"
PC_EXEC_LOGIC = "ausfuehren_logik"
PC_RULE_ACTIVE = "aktiv_wenn"          # conditions: rule is armed
PC_EXEC = "ausfuehren_wenn"            # conditions: rule fires (warning, then action)
PC_WARN = "warn_minuten"               # -1/None = global
PC_PAUSE = "pause_entitaet"            # entity that pauses the rule while on/true

TPL_AUTO = "automatisch"               # apply to every PC without a template
TPL_REF = "referenz"                   # serial of the PC whose entities are offered

ACTIONS = ["shutdown", "hibernate", "sleep"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# activity criteria (what counts as "in use")
CRIT_INPUT = "eingabe"          # keyboard/mouse idle time
CRIT_RDP = "rdp"                # RDP session open
CRIT_USERS = "benutzer"         # somebody logged in (strict: keeps every logged-in PC on)
CRIT_CPU = "cpu"                # CPU load above limit (average)
CRIT_MEDIA = "medien"           # media player playing
CRIT_CAMMIC = "kamera_mikrofon" # camera or microphone in use
CRIT_DISPLAY = "anzeige_sperre" # an app keeps the display on (video, presentation)

CRITERIA = [CRIT_INPUT, CRIT_RDP, CRIT_CPU, CRIT_MEDIA, CRIT_CAMMIC, CRIT_DISPLAY, CRIT_USERS]
DEFAULT_CRITERIA = [CRIT_INPUT, CRIT_RDP, CRIT_CPU, CRIT_MEDIA, CRIT_CAMMIC, CRIT_DISPLAY]

# HASS.Agent .NET10 entity unique_id keys (sensor_<serial>_<key>, button_<serial>_<key>)
KEY_IDLE = "idle_time_seconds"
KEY_LOCKED = "session_locked"
KEY_USERS = "logged_in_users"
KEY_RDP = "rdp_sessions"
KEY_CPU = "cpu_usage"
KEY_CAM = "camera_in_use"
KEY_MIC = "microphone_in_use"
KEY_SLEEP_BLOCKED = "sleep_blocked"
KEY_UPTIME = "uptime_seconds"
KEY_SESSION = "session_state"

# status values
ST_ACTIVE = "aktiv"
ST_IDLE = "inaktiv"
ST_WARNING = "warnung"
ST_SHUTDOWN = "abgeschaltet"
ST_OFFLINE = "offline"
ST_EXEMPT = "ausgenommen"
ST_PAUSED = "pausiert"          # master switch off
ST_OUTSIDE = "ausserhalb_zeit"
ST_ARMED = "bereit"             # rule armed, execute conditions not (yet) met
ST_NOT_ARMED = "regel_inaktiv"  # "active when" conditions not met
ST_RULE_PAUSED = "regel_pausiert"
STATES = [ST_ACTIVE, ST_IDLE, ST_WARNING, ST_SHUTDOWN, ST_OFFLINE, ST_EXEMPT, ST_PAUSED, ST_OUTSIDE,
          ST_ARMED, ST_NOT_ARMED, ST_RULE_PAUSED]

# area_id -> room code of the house naming scheme
ROOM_CODES = {
    "wohnzimmer": "wz", "buro": "bu", "buero": "bu", "kuche": "ku", "kueche": "ku",
    "schlafzimmer": "sz", "flur": "fl", "keller": "ke", "badezimmer": "ba", "bad": "ba",
}
