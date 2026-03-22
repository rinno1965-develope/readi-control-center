# ====== IDENTICO AL TUO + FIX MOBILE ======

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
    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

# =========================
# PARSER
# =========================
TAKEOFF_RE = re.compile(r"takeoff", re.IGNORECASE)
LANDED_RE = re.compile(r"landed", re.IGNORECASE)
NOGO_RE = re.compile(r"no go volo", re.IGNORECASE)
GOVOLO_RE = re.compile(r"go volo", re.IGNORECASE)

def decode_subject(s):
    return decode_header(s)[0][0].decode("utf-8") if isinstance(decode_header(s)[0][0], bytes) else s

def parse_subject(subject):
    s = subject.lower()
    if "no go" in s:
        return "NO_GO"
    if "go volo" in s:
        return "GO"
    if "takeoff" in s:
        return "IN_VOLO"
    if "landed" in s:
        return "A_TERRA"
    return None

# =========================
# FETCH
# =========================
def fetch_data():
    model = {d: {"state": "A_TERRA"} for d in display_order}

    try:
        mail = imaplib.IMAP4_SSL(cfg["imap"]["server"])
        mail.login(cfg["imap"]["email_user"], cfg["imap"]["email_pass"])
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-100:]

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subj = decode_subject(msg.get("Subject", ""))

            event = parse_subject(subj)
            if not event:
                continue

            for drone in display_order:
                if drone.lower() in subj.lower():
                    model[drone]["state"] = event
    except:
        pass

    return model

# =========================
# LOAD CONFIG
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

display_order = list(cfg.get("aliases", {}).keys())
title = cfg.get("ui", {}).get("title", "ReADI Control Center")

# =========================
# UI BASE
# =========================
st.set_page_config(page_title=title, layout="wide")

st.title(title)

model = fetch_data()

# =========================
# CARDS HTML
# =========================
cards_html = ""

for drone in display_order:
    state = model[drone]["state"]

    color = "#39d98a"
    label = "A TERRA"

    if state == "IN_VOLO":
        color = "#ff3b3b"
        label = "IN VOLO"
    elif state == "NO_GO":
        color = "#f7c948"
        label = "NO GO"

    cards_html += f"""
    <div style="
        border:2px solid {color};
        border-radius:12px;
        padding:14px;
        background:#09111f;
        color:white;
    ">
        <div style="font-size:18px; font-weight:700;">
            {drone}
        </div>

        <div style="
            background:{color};
            color:#000;
            padding:10px;
            text-align:center;
            font-weight:700;
            margin-top:10px;
        ">
            {label}
        </div>
    </div>
    """

# =========================
# 💣 RESPONSIVE FIX QUI
# =========================
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

/* ===== RESPONSIVE ===== */
.grid {{
    display:grid;
    gap:16px;
    margin-top:8px;
    margin-bottom:20px;
    grid-template-columns: repeat(5, 1fr);
}}

@media (max-width: 900px) {{
    .grid {{
        grid-template-columns: repeat(2, 1fr);
    }}
}}

@media (max-width: 600px) {{
    .grid {{
        grid-template-columns: 1fr;
    }}
}}
</style>

<div class="grid">
{cards_html}
</div>
"""

components.html(full_cards_html, height=1200, scrolling=True)
