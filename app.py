import json
import os
import re
import imaplib
import email
import email.message
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # ✅ AGGIUNTO

import streamlit as st
import streamlit.components.v1 as components


# =========================
# TIMEZONE FIX 🔥
# =========================
LOCAL_TZ = ZoneInfo("Europe/Rome")

def now_local():
    return datetime.now(LOCAL_TZ)


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
        raise ValueError("Credenziali IMAP mancanti.")


# =========================
# REGEX
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


def get_text_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode("utf-8", errors="ignore")
    return ""


def clean_body(text: str) -> str:
    return (text or "").split("\nOn ")[0].strip()


def parse_subject(subject: str, aliases: dict):
    s = subject.lower()

    if NOGO_RE.search(s):
        return None, "NO_GO", subject
    if GOVOLO_RE.search(s):
        return None, "GO", ""
    if TAKEOFF_RE.search(s):
        return None, "TAKEOFF", ""
    if LANDED_RE.search(s):
        return None, "LANDED", ""

    return None


# =========================
# TIME FORMAT
# =========================
def format_dt_for_card(dt_obj):
    if not dt_obj:
        return "—"
    return dt_obj.astimezone(LOCAL_TZ).strftime("%H:%M:%S")


def compute_timer(start_dt):
    if not start_dt:
        return "—"
    delta = now_local() - start_dt.astimezone(LOCAL_TZ)
    sec = int(delta.total_seconds())
    return f"{sec//60:02d}:{sec%60:02d}"


def border_color(state):
    return "#ff3b3b" if state == "IN_VOLO" else "#f7c948" if state == "NO_GO" else "#39d98a"


def status_label(state):
    return "IN VOLO" if state == "IN_VOLO" else "NO GO" if state == "NO_GO" else "A TERRA"


# =========================
# LOAD CONFIG
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

display_order = list(cfg.get("aliases", {}).keys())
poll_seconds = int(cfg.get("poll_seconds", 10))


# =========================
# UI
# =========================
st.set_page_config(layout="wide")

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=poll_seconds * 1000)

st.caption(f"🔄 Ultimo refresh: {now_local().strftime('%H:%M:%S')}")


# =========================
# DATA
# =========================
model = fetch_control_center_data(cfg)[0]


# =========================
# CARDS
# =========================
cards_html = ""

for drone in display_order:
    info = model.get(drone, {})
    state = info.get("state", "A_TERRA")
    color = border_color(state)
    label = status_label(state)
    timer = compute_timer(info.get("timer_start_dt"))

    flash_class = "blink" if state == "IN_VOLO" else ""

    cards_html += f"""
    <div style="border:2px solid {color}; border-radius:12px; padding:14px; background:#09111f; color:white;">
        <div style="font-weight:700;">{drone}</div>
        <div class="{flash_class}" style="background:{color}; padding:10px; text-align:center;">
            {label}
        </div>
        <div>Timer: {timer}</div>
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

<div style="display:grid; grid-template-columns: repeat(5, 1fr); gap:16px;">
{cards_html}
</div>
"""

components.html(full_cards_html, height=900)
