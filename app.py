# =========================
# IMPORT
# =========================
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
# MOBILE DETECT (BOMBA 💣)
# =========================
query_params = st.query_params

view_param = ""
if "view" in query_params:
    val = query_params["view"]
    if isinstance(val, list):
        view_param = val[0]
    else:
        view_param = val

# URL override
is_mobile = str(view_param).strip().lower() == "mobile"

# fallback session (toggle manuale)
if "force_mobile" not in st.session_state:
    st.session_state["force_mobile"] = False

if st.session_state["force_mobile"]:
    is_mobile = True


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

    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

    if not cfg["imap"]["email_user"] or not cfg["imap"]["email_pass"]:
        raise ValueError("Credenziali IMAP mancanti")


# =========================
# LOAD CONFIG PRIMA
# =========================
try:
    cfg = safe_load_json(CONFIG_FILE)
    ensure_config_has_keys(cfg)
except Exception as e:
    st.set_page_config(page_title="ReADI Control Center", layout="wide")
    st.error(f"Errore config: {e}")
    st.stop()

display_order = list(cfg.get("aliases", {}).keys())
title = cfg.get("ui", {}).get("title", "ReADI Control Center")
poll_seconds = int(cfg.get("poll_seconds", 3))


# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title=title,
    layout="centered" if is_mobile else "wide"
)


# =========================
# LOGIN
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
    return (subject or "").upper().startswith("NOTAM")

def get_text_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode("utf-8", errors="ignore")
    return ""

def clean_body(text: str) -> str:
    return text.split("\nOn ")[0].strip()

def parse_subject(subject: str, aliases: dict):
    s = subject.lower()

    if "no go volo" in s:
        return "NO_GO"
    if "go volo" in s:
        return "GO"
    if "takeoff" in s:
        return "TAKEOFF"
    if "landed" in s:
        return "LANDED"
    return None


# =========================
# HELPERS
# =========================
def compute_timer(start_dt):
    if not start_dt:
        return "—"
    delta = now_local() - start_dt
    sec = int(delta.total_seconds())
    return f"{sec//60:02d}:{sec%60:02d}"

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
# FETCH (REALE)
# =========================
def fetch_control_center_data(cfg: dict):
    imap_cfg = cfg["imap"]
    aliases = cfg.get("aliases", {})

    model = {name: {"state": "A_TERRA", "last_event_text": "—", "timer_start_dt": None} for name in display_order}
    notams = []

    try:
        mail = imaplib.IMAP4_SSL(imap_cfg["server"], int(imap_cfg.get("port", 993)))
        mail.login(imap_cfg["email_user"], imap_cfg["email_pass"])
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        ids = data[0].split()[-200:]

        for num in ids:
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            subj = decode_subject(msg.get("Subject", ""))

            parsed = parse_subject(subj, aliases)
            if not parsed:
                continue

            drone, event = None, parsed

            for d in display_order:
                if d.lower() in subj.lower():
                    drone = d
                    break

            if not drone:
                continue

            if event == "TAKEOFF":
                model[drone]["state"] = "IN_VOLO"
                model[drone]["timer_start_dt"] = now_local()

            elif event == "LANDED":
                model[drone]["state"] = "A_TERRA"
                model[drone]["timer_start_dt"] = None

            elif event == "NO_GO":
                model[drone]["state"] = "NO_GO"

            elif event == "GO":
                model[drone]["state"] = "A_TERRA"

        mail.logout()

    except Exception as e:
        st.warning(f"Errore IMAP: {e}")

    return model, notams


# =========================
# TOGGLE MANUALE
# =========================
if not is_mobile:
    if st.sidebar.button("📱 Forza Mobile"):
        st.session_state["force_mobile"] = True
        st.rerun()


# =========================
# REFRESH
# =========================
st_autorefresh(interval=poll_seconds * 1000, key="refresh")

model, notams = fetch_control_center_data(cfg)


# =========================
# MOBILE VIEW
# =========================
if is_mobile:
    for drone in display_order:
        info = model.get(drone, {})
        st.markdown(f"## {drone}")
        st.markdown(f"**{status_label(info['state'])}**")
        st.markdown(f"⏱ {compute_timer(info['timer_start_dt'])}")
        st.markdown("---")

    st.stop()


# =========================
# DESKTOP VIEW
# =========================
st.title(title)

cols = st.columns(5)
for i, drone in enumerate(display_order):
    info = model.get(drone, {})
    with cols[i % 5]:
        st.markdown(f"### {drone}")
        st.markdown(f"**{status_label(info['state'])}**")
        st.markdown(f"⏱ {compute_timer(info['timer_start_dt'])}")
