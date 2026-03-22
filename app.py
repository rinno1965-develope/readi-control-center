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

    cfg["imap"]["email_user"] = cfg["imap"].get("email_user")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass")


# =========================
# PARSER (IL TUO ORIGINALE)
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


def parse_subject(subject: str, aliases: dict):
    s_low = subject.lower()

    for drone, alias_list in aliases.items():
        for alias in alias_list:
            if alias.lower() in s_low:
                if TAKEOFF_RE.search(s_low):
                    return drone, "IN_VOLO"
                if LANDED_RE.search(s_low):
                    return drone, "A_TERRA"
                if NOGO_RE.search(s_low):
                    return drone, "NO_GO"
                if GOVOLO_RE.search(s_low):
                    return drone, "A_TERRA"

    return None


# =========================
# TIMER
# =========================
def compute_timer(start_dt):
    if not start_dt:
        return "—"
    delta = now_local() - start_dt.astimezone(LOCAL_TZ)
    sec = int(delta.total_seconds())
    return f"{sec//60:02d}:{sec%60:02d}"


def border_color(state):
    if state == "IN_VOLO":
        return "#ff3b3b"
    if state == "NO_GO":
        return "#f7c948"
    return "#39d98a"


def status_label(state):
    return state.replace("_", " ")


# =========================
# IMAP
# =========================
def fetch_data(cfg):
    imap_cfg = cfg["imap"]
    aliases = cfg["aliases"]

    model = {d: {"state": "A_TERRA", "timer_start_dt": None} for d in aliases}

    try:
        mail = imaplib.IMAP4_SSL(imap_cfg["server"], imap_cfg["port"])
        mail.login(imap_cfg["email_user"], imap_cfg["email_pass"])
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-300:]

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = decode_subject(msg.get("Subject", ""))

            parsed = parse_subject(subject, aliases)
            if not parsed:
                continue

            drone, state = parsed

            msg_dt = parsedate_to_datetime(msg.get("Date"))
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)

            model[drone]["state"] = state

            if state == "IN_VOLO":
                model[drone]["timer_start_dt"] = msg_dt
            else:
                model[drone]["timer_start_dt"] = None

        mail.logout()

    except Exception as e:
        st.warning(f"IMAP error: {e}")

    return model


# =========================
# LOAD CONFIG
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

display_order = list(cfg["aliases"].keys())
poll_seconds = int(cfg.get("poll_seconds", 3))


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
model = fetch_data(cfg)


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

    flash = "blink" if state == "IN_VOLO" else ""

    cards_html += f"""
    <div style="border:2px solid {color}; padding:12px; border-radius:12px;">
        <b>{drone}</b>
        <div class="{flash}" style="background:{color}; padding:10px; text-align:center;">
            {label}
        </div>
        <div>Timer: {timer}</div>
    </div>
    """


html = f"""
<style>
@keyframes blink {{
  0% {{opacity:1}}
  50% {{opacity:0.2}}
  100% {{opacity:1}}
}}
.blink {{
  animation: blink 1s infinite;
}}
</style>

<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;">
{cards_html}
</div>
"""

components.html(html, height=900)
