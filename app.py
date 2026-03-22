import json
import os
import re
import imaplib
import email
import email.message
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh


# =========================
# MOBILE DETECT
# =========================
query_params = st.query_params

view_param = ""
if "view" in query_params:
    val = query_params["view"]
    if isinstance(val, list):
        view_param = val[0]
    else:
        view_param = val

is_mobile = str(view_param).strip().lower() == "mobile"


# =========================
# TIMEZONE
# =========================
LOCAL_TZ = ZoneInfo("Europe/Rome")


def now_local():
    return datetime.now(LOCAL_TZ)


# =========================
# CONFIG
# =========================
CONFIG_FILE = "config.json"


def safe_load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_config_has_keys(cfg: dict):
    if "imap" not in cfg:
        raise ValueError("config.json: manca la sezione 'imap'")

    for k in ("server", "port"):
        if k not in cfg["imap"]:
            raise ValueError(f"config.json: imap.{k} mancante")

    # credenziali da env
    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

    if not cfg["imap"]["email_user"] or not cfg["imap"]["email_pass"]:
        raise ValueError(
            "Credenziali IMAP mancanti. Imposta READI_IMAP_USER e READI_IMAP_PASS."
        )


# carico config PRIMA del resto, così set_page_config è pulita e stabile
try:
    cfg = safe_load_json(CONFIG_FILE)
    ensure_config_has_keys(cfg)
except Exception as e:
    # set_page_config prima di ogni altro output streamlit
    st.set_page_config(page_title="ReADI Control Center", layout="wide")
    st.error(f"Errore config: {e}")
    st.stop()

display_order = list(cfg.get("aliases", {}).keys())
title = cfg.get("ui", {}).get("title", "ReADI Control Center")
poll_seconds = int(cfg.get("poll_seconds", 3))

st.set_page_config(
    page_title=title,
    layout="centered" if is_mobile else "wide"
)


# =========================
# LOGIN PANNELLO
# =========================
USERNAME = "admin"
PASSWORD = "readi123"


def login():
    st.title("🔐 Accesso ReADI Control Center")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        if user == USERNAME and pwd == PASSWORD:
            st.session_state["logged"] = True
            st.rerun()
        else:
            st.error("Credenziali errate")


if "logged" not in st.session_state:
    st.session_state["logged"] = False

if not st.session_state["logged"]:
    login()
    st.stop()


# =========================
# PARSER
# =========================
TAKEOFF_RE = re.compile(r"\b(take\s*off|takeoff|taken\s*off)\b", re.IGNORECASE)
LANDED_RE = re.compile(r"\b(landed|landing)\b", re.IGNORECASE)
NOGO_RE = re.compile(r"\b(no\s*go\s*volo)\b", re.IGNORECASE)
GOVOLO_RE = re.compile(r"\b(go\s*volo)\b", re.IGNORECASE)


def decode_subject(raw_subj: str) -> str:
    if not raw_subj:
        return ""
    parts = decode_header(raw_subj)
    out = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            out += part.decode(enc or "utf-8", errors="ignore")
        else:
            out += part
    return out.strip()


def is_notam_subject(subject: str) -> bool:
    s = (subject or "").strip()
    return s.upper().startswith("NOTAM")


def get_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = str(part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()

        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype.startswith("text/"):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()

        return ""

    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def clean_body(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    for sep in ["\nOn ", "\nIl ", "\nDa: ", "\nFrom: "]:
        if sep in t:
            t = t.split(sep, 1)[0]
    return t.strip()


def parse_subject(subject: str, aliases: dict):
    """
    Return: (drone, event, reason)
    event: TAKEOFF | LANDED | NO_GO | GO
    """
    s = (subject or "").strip()
    s_low = s.lower()

    event = None
    reason = ""

    if NOGO_RE.search(s_low):
        event = "NO_GO"
        idx = s_low.find("no go volo")
        tail = s[idx:] if idx >= 0 else s
        if ":" in tail:
            reason = tail.split(":", 1)[1].strip()
        else:
            reason = tail.replace("NO GO VOLO", "").replace("no go volo", "").strip(" -:").strip()

    elif GOVOLO_RE.search(s_low):
        event = "GO"

    elif TAKEOFF_RE.search(s_low):
        event = "TAKEOFF"

    elif LANDED_RE.search(s_low):
        event = "LANDED"

    else:
        return None

    for drone_name, alias_list in (aliases or {}).items():
        for alias in (alias_list or []):
            if not alias:
                continue
            if str(alias).lower() in s_low:
                return drone_name, event, reason

    return None


# =========================
# HELPERS UI
# =========================
def format_dt_for_card(dt_obj):
    if not dt_obj:
        return "—"
    try:
        return dt_obj.astimezone(LOCAL_TZ).strftime("%H:%M:%S")
    except Exception:
        return "—"


def format_dt_for_table(dt_obj):
    if not dt_obj:
        return ""
    try:
        return dt_obj.astimezone(LOCAL_TZ).strftime("%d/%m %H:%M:%S")
    except Exception:
        return ""


def compute_timer(start_dt):
    if not start_dt:
        return "—"
    try:
        now = now_local()
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=LOCAL_TZ)
        delta = now - start_dt.astimezone(LOCAL_TZ)
        sec = max(0, int(delta.total_seconds()))
        mm = sec // 60
        ss = sec % 60
        hh = mm // 60
        mm = mm % 60
        if hh > 0:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        return f"{mm:02d}:{ss:02d}"
    except Exception:
        return "—"


def border_color(state):
    if state == "IN_VOLO":
        return "#ff3b3b"
    if state == "NO_GO":
        return "#f7c948"
    return "#39d98a"


def status_label(state):
    if state == "IN_VOLO":
        return "IN VOLO"
    if state == "NO_GO":
        return "NO GO"
    return "A TERRA"


# =========================
# IMAP FETCH
# =========================
def fetch_control_center_data(cfg: dict):
    imap_cfg = cfg["imap"]
    aliases = cfg.get("aliases", {})
    ordered = list(aliases.keys())

    model = {
        name: {
            "state": "A_TERRA",
            "last_event_text": "—",
            "event_dt": None,
            "timer_start_dt": None,
        }
        for name in ordered
    }

    notams = []
    connected = False
    error_msg = ""

    try:
        mail = imaplib.IMAP4_SSL(imap_cfg["server"], int(imap_cfg.get("port", 993)))
        mail.login(imap_cfg["email_user"], imap_cfg["email_pass"])
        connected = True
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            try:
                mail.logout()
            except Exception:
                pass
            return model, notams, connected, "Nessuna mail trovata."

        tail_uids = int(cfg.get("tail_uids", 300))
        ids = data[0].split()[-tail_uids:]

        for num in ids:
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_part = msg_data[0]
            if not isinstance(raw_part, tuple) or len(raw_part) < 2:
                continue

            msg = email.message_from_bytes(raw_part[1])
            subj = decode_subject(msg.get("Subject", ""))

            msg_dt = None
            try:
                msg_dt = parsedate_to_datetime(msg.get("Date"))
                if msg_dt and msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            except Exception:
                msg_dt = None

            if is_notam_subject(subj):
                body = clean_body(get_text_body(msg))
                sender = decode_subject(msg.get("From", ""))
                notams.append({
                    "Data/Ora": format_dt_for_table(msg_dt),
                    "PIC": sender,
                    "Messaggio": body if body else subj,
                })
                continue

            parsed = parse_subject(subj, aliases)
            if not parsed:
                continue

            drone, event, reason = parsed

            if drone not in model:
                model[drone] = {
                    "state": "A_TERRA",
                    "last_event_text": "—",
                    "event_dt": None,
                    "timer_start_dt": None,
                }

            hhmmss = format_dt_for_card(msg_dt)

            if event == "TAKEOFF":
                model[drone]["state"] = "IN_VOLO"
                model[drone]["last_event_text"] = f"{hhmmss} — TAKEOFF"
                model[drone]["event_dt"] = msg_dt
                model[drone]["timer_start_dt"] = msg_dt

            elif event == "LANDED":
                model[drone]["state"] = "A_TERRA"
                model[drone]["last_event_text"] = f"{hhmmss} — LANDED"
                model[drone]["event_dt"] = msg_dt
                model[drone]["timer_start_dt"] = None

            elif event == "NO_GO":
                model[drone]["state"] = "NO_GO"
                model[drone]["event_dt"] = msg_dt
                model[drone]["timer_start_dt"] = None
                if reason:
                    model[drone]["last_event_text"] = f"{hhmmss} — {reason}"
                else:
                    model[drone]["last_event_text"] = f"{hhmmss} — NO GO"

            elif event == "GO":
                model[drone]["state"] = "A_TERRA"
                model[drone]["last_event_text"] = f"{hhmmss} — GO VOLO"
                model[drone]["event_dt"] = msg_dt
                model[drone]["timer_start_dt"] = None

        try:
            mail.logout()
        except Exception:
            pass

    except Exception as e:
        error_msg = str(e)

    notams = sorted(notams, key=lambda x: x["Data/Ora"], reverse=True)
    return model, notams[:20], connected, error_msg


# =========================
# GLOBAL STYLE
# =========================
if is_mobile:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 0.4rem;
                padding-left: 0.7rem;
                padding-right: 0.7rem;
                padding-bottom: 1rem;
            }
            header {visibility: hidden;}
            .stApp {
                margin-top: -18px;
                background: #050a14;
            }
            div[data-testid="stDataFrame"] {
                font-size: 12px;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 0rem;
            }
            header {visibility: hidden;}
            .stApp {
                margin-top: -40px;
            }
        </style>
        """,
        unsafe_allow_html=True
    )


# =========================
# REFRESH
# =========================
st_autorefresh(interval=poll_seconds * 1000, key="refresh")

if is_mobile:
    st.caption(f"📱 Mobile view • refresh {poll_seconds}s • {now_local().strftime('%H:%M:%S')}")
else:
    st.caption(f"⏱ Auto-refresh ogni {poll_seconds}s")
    st.caption(f"🔄 Ultimo refresh: {now_local().strftime('%H:%M:%S')}")


# =========================
# HEADER
# =========================
if is_mobile:
    top1, top2 = st.columns([1, 4])
    with top1:
        if st.button("🔄", use_container_width=True):
            model, notams, connected, error_msg = fetch_control_center_data(cfg)
            st.session_state["cc_model"] = model
            st.session_state["cc_notams"] = notams
            st.session_state["cc_connected"] = connected
            st.session_state["cc_error"] = error_msg
            st.session_state["cc_last_refresh"] = now_local()
            st.rerun()

    with top2:
        st.markdown(
            f"<div style='font-size:24px; font-weight:800; color:white; line-height:1.15;'>{title}</div>",
            unsafe_allow_html=True
        )
else:
    col_top_1, col_top_2 = st.columns([1, 6])
    with col_top_1:
        if st.button("🔄 Aggiorna stato", use_container_width=True):
            model, notams, connected, error_msg = fetch_control_center_data(cfg)
            st.session_state["cc_model"] = model
            st.session_state["cc_notams"] = notams
            st.session_state["cc_connected"] = connected
            st.session_state["cc_error"] = error_msg
            st.session_state["cc_last_refresh"] = now_local()
            st.rerun()

    with col_top_2:
        col_logo, col_title = st.columns([1, 6])

        with col_logo:
            try:
                st.image("aiview.png", width=120)
            except Exception:
                st.markdown("")

        with col_title:
            st.markdown(
                f"<h1 style='margin:0; color:white;'>{title}</h1>",
                unsafe_allow_html=True
            )


# =========================
# FETCH DATA
# =========================
model, notams, connected, error_msg = fetch_control_center_data(cfg)

st.session_state["cc_model"] = model
st.session_state["cc_notams"] = notams
st.session_state["cc_connected"] = connected
st.session_state["cc_error"] = error_msg
st.session_state["cc_last_refresh"] = now_local()


# =============================
# CHANGE DETECTION (SUONO)
# =============================
current_snapshot = json.dumps(model, sort_keys=True, default=str)
current_notams = json.dumps(notams, sort_keys=True, default=str)

prev_snapshot = st.session_state.get("prev_snapshot")
prev_notams = st.session_state.get("prev_notams")

changed = False

if prev_snapshot and prev_snapshot != current_snapshot:
    changed = True

if prev_notams and prev_notams != current_notams:
    changed = True

st.session_state["prev_snapshot"] = current_snapshot
st.session_state["prev_notams"] = current_notams

if changed:
    components.html(
        """
        <script>
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var oscillator = ctx.createOscillator();
            var gain = ctx.createGain();

            oscillator.type = "sine";
            oscillator.frequency.setValueAtTime(1500, ctx.currentTime);

            oscillator.connect(gain);
            gain.connect(ctx.destination);

            gain.gain.setValueAtTime(0.05, ctx.currentTime);
            oscillator.start();
            gain.gain.exponentialRampToValueAtTime(0.00001, ctx.currentTime + 0.3);
            oscillator.stop(ctx.currentTime + 0.31);
        } catch (e) {}
        </script>
        """,
        height=0,
    )

model = st.session_state["cc_model"]
notams = st.session_state["cc_notams"]
connected = st.session_state["cc_connected"]
error_msg = st.session_state["cc_error"]
last_refresh = st.session_state["cc_last_refresh"]


# =========================
# STATUS BAR
# =========================
if is_mobile:
    if connected:
        st.caption("🟢 Connesso IMAP")
    else:
        st.caption("🔴 Disconnesso IMAP")

    if error_msg:
        st.warning(f"Errore IMAP: {error_msg}")

    st.caption(f"Ultimo refresh: {last_refresh.strftime('%H:%M:%S')}")
else:
    left, right = st.columns([6, 1])
    with left:
        if connected:
            st.caption("🟢 Connesso IMAP")
        else:
            st.caption("🔴 Disconnesso IMAP")

        if error_msg:
            st.warning(f"Errore IMAP: {error_msg}")

        st.caption(f"Ultimo refresh: {last_refresh.strftime('%H:%M:%S')}")

    with right:
        st.markdown(
            "<div style='text-align:right; font-size:22px;'>🛰️</div>",
            unsafe_allow_html=True
        )


# =========================
# MOBILE CARDS
# =========================
def render_cards_mobile(model_data, ordered_drones):
    cards_html = ""

    for drone in ordered_drones:
        info = model_data.get(drone, {
            "state": "A_TERRA",
            "last_event_text": "—",
            "event_dt": None,
            "timer_start_dt": None,
        })

        state = str(info.get("state", "")).strip().upper()
        color = border_color(state)
        label = status_label(state)
        timer = compute_timer(info.get("timer_start_dt"))
        last_event = info.get("last_event_text", "—")
        flash_class = "blink" if state == "IN_VOLO" else ""

        cards_html += f"""
        <div style="
            border:2px solid {color};
            border-radius:16px;
            padding:14px;
            background:#09111f;
            color:white;
            margin-bottom:12px;
            box-shadow: 0 0 0 1px rgba(255,255,255,0.03) inset;
        ">
            <div style="font-size:22px; font-weight:800; margin-bottom:10px; letter-spacing:0.3px;">
                {drone}
            </div>

            <div class="{flash_class}" style="
                background:{color};
                color:#0b0f14;
                padding:14px;
                font-weight:900;
                text-align:center;
                font-size:20px;
                border-radius:12px;
                margin-bottom:12px;
            ">
                {label}
            </div>

            <div style="font-size:18px; color:#dce7f5; margin-bottom:6px;">
                ⏱ {timer}
            </div>

            <div style="font-size:14px; color:#b6c4d6; font-style:italic; line-height:1.35;">
                Ultimo evento: {last_event}
            </div>
        </div>
        """

    full_html = f"""
    <style>
    @keyframes blink {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.25; }}
        100% {{ opacity: 1; }}
    }}

    .blink {{
        animation: blink 1s infinite;
    }}
    </style>
    <div style="margin-top:8px; margin-bottom:14px;">
        {cards_html}
    </div>
    """

    components.html(full_html, height=max(520, len(ordered_drones) * 170), scrolling=True)


# =========================
# MOBILE VIEW
# =========================
if is_mobile:
    render_cards_mobile(model, display_order)

    global_event = "—"
    latest_dt = None
    for drone, info in model.items():
        event_dt = info.get("event_dt")
        if event_dt and (latest_dt is None or event_dt > latest_dt):
            latest_dt = event_dt
            global_event = f"{drone} — {info.get('last_event_text', '—')}"

    st.markdown(
        f"""
        <div style="
            color:#d6e3f0;
            font-style:italic;
            margin:4px 0 12px 0;
            line-height:1.35;
            font-size:14px;
        ">
            Ultimo evento globale: {global_event}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; margin-bottom:8px;">
            <h3 style="margin:0; color:white;">NOTAM / Comunicazioni PIC</h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    if notams:
        for n in notams[:5]:
            data_ora = n.get("Data/Ora", "")
            pic = n.get("PIC", "")
            msg = n.get("Messaggio", "")
            st.markdown(
                f"""
                <div style="
                    border:1px solid #243249;
                    border-radius:12px;
                    padding:10px 12px;
                    background:#0b1422;
                    color:#dbe6f3;
                    margin-bottom:8px;
                ">
                    <div style="font-size:12px; color:#96abc5; margin-bottom:6px;">{data_ora}</div>
                    <div style="font-size:12px; color:#96abc5; margin-bottom:6px;">{pic}</div>
                    <div style="font-size:14px; line-height:1.4;">{msg}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        st.info("Nessun NOTAM disponibile")

    st.caption("🚀 Developed by Roberto Innocenti — Powered by AiviewGroup")
    st.stop()


# =========================
# DESKTOP CARDS
# =========================
cards_html = ""

for drone in display_order:
    info = model.get(drone, {
        "state": "A_TERRA",
        "last_event_text": "—",
        "event_dt": None,
        "timer_start_dt": None,
    })

    state = str(info.get("state", "")).strip().upper()
    color = border_color(state)
    label = status_label(state)
    timer = compute_timer(info.get("timer_start_dt"))
    last_event = info.get("last_event_text", "—")

    flash_class = "blink" if state == "IN_VOLO" else ""

    cards_html += f"""
    <div style="
        border:2px solid {color};
        border-radius:12px;
        padding:14px;
        background:#09111f;
        color:white;
        min-height:165px;
    ">
        <div style="font-size:18px; font-weight:700; margin-bottom:10px;">
            {drone}
        </div>

        <div class="{flash_class}" style="
            background:{color};
            color:#0b0f14;
            padding:12px;
            font-weight:800;
            text-align:center;
            font-size:16px;
            margin-bottom:14px;
        ">
            {label}
        </div>

        <div style="font-size:13px; color:#c7d2e3; margin-bottom:6px;">
            Timer: {timer}
        </div>

        <div style="font-size:13px; color:#c7d2e3; font-style:italic;">
            Ultimo evento: {last_event}
        </div>
    </div>
    """

full_cards_html = f"""
<style>
@keyframes blink {{
    0% {{ opacity: 1; }}
    50% {{ opacity: 0.2; }}
    100% {{ opacity: 1; }}
}}

.blink {{
    animation: blink 1s infinite;
}}
</style>

<div style="
display:grid;
grid-template-columns: repeat(5, 1fr);
gap:16px;
margin-top:8px;
margin-bottom:20px;
">
{cards_html}
</div>
"""

components.html(full_cards_html, height=900, scrolling=True)


# =========================
# ULTIMO EVENTO GLOBALE
# =========================
global_event = "—"
latest_dt = None

for drone, info in model.items():
    event_dt = info.get("event_dt")
    if event_dt and (latest_dt is None or event_dt > latest_dt):
        latest_dt = event_dt
        global_event = f"{drone} — {info.get('last_event_text', '—')}"

st.markdown(
    f"""
    <div style="
        display:flex;
        justify-content:center;
        align-items:center;
        gap:20px;
        color:#d6e3f0;
        font-style:italic;
        margin:8px 0 18px 0;
        flex-wrap:wrap;
    ">
        <span>Ultimo evento globale: {global_event}</span>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================
# NOTAM
# =========================
st.markdown(
    """
    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:20px; margin-bottom:10px;">
        <h3 style="margin:0;">NOTAM / Comunicazioni PIC</h3>
        <span style="font-size:20px; color:#7f8fa6; font-style:italic;">
            🚀 Developed by Roberto Innocenti — Powered by AiviewGroup
        </span>
    </div>
    """,
    unsafe_allow_html=True
)

if notams:
    st.dataframe(notams, use_container_width=True)
else:
    st.info("Nessun NOTAM disponibile")
