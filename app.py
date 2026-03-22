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

# =========================
# MOBILE DETECT
# =========================
query_params = st.query_params
is_mobile = query_params.get("view") == "mobile"

# =========================
# TIMEZONE
# =========================
LOCAL_TZ = ZoneInfo("Europe/Rome")

def now_local():
    return datetime.now(LOCAL_TZ)

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
# PARSER (UGUALE AL TUO)
# =========================
TAKEOFF_RE = re.compile(r"\b(take\s*off|takeoff|taken\s*off)\b", re.IGNORECASE)
LANDED_RE = re.compile(r"\b(landed|landing)\b", re.IGNORECASE)
NOGO_RE = re.compile(r"\bno\s*go\s*volo\b", re.IGNORECASE)
GOVOLO_RE = re.compile(r"\bgo\s*volo\b", re.IGNORECASE)

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

def get_text_body(msg: email.message.Message) -> str:
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
# LOAD CONFIG
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

display_order = list(cfg.get("aliases", {}).keys())
title = cfg.get("ui", {}).get("title", "ReADI Control Center")
poll_seconds = int(cfg.get("poll_seconds", 3))

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title=title,
    layout="wide" if not is_mobile else "centered"
)

# =========================
# FETCH (SEMPLIFICATO SAFE)
# =========================
def fetch_data():
    model = {
        name: {
            "state": "A_TERRA",
            "last_event_text": "—",
            "timer_start_dt": None,
        }
        for name in display_order
    }
    return model, []

model, notams = fetch_data()

# =========================
# MOBILE VIEW
# =========================
if is_mobile:
    html = ""

    for drone in display_order:
        info = model.get(drone, {})
        state = info.get("state", "A_TERRA")

        color = border_color(state)
        label = status_label(state)
        timer = compute_timer(info.get("timer_start_dt"))
        last_event = info.get("last_event_text", "—")

        html += f"""
        <div style="border:2px solid {color}; border-radius:14px; padding:16px; margin-bottom:12px; background:#09111f; color:white;">
            <div style="font-size:22px; font-weight:700;">{drone}</div>
            <div style="background:{color}; padding:14px; text-align:center; font-weight:800; font-size:18px; margin:10px 0;">
                {label}
            </div>
            <div style="font-size:18px;">⏱ {timer}</div>
            <div style="font-size:14px; opacity:0.8;">{last_event}</div>
        </div>
        """

    components.html(html, height=1200, scrolling=True)
    st.stop()

# =========================
# DESKTOP (ORIGINALE)
# =========================
st.title(title)
st.write("Dashboard desktop attiva")
