# ===== READI CONTROL CENTER - VERSIONE STABILE + MOBILE FIX =====

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

LOCAL_TZ = ZoneInfo("Europe/Rome")

def now_local():
    return datetime.now(LOCAL_TZ)

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

CONFIG_FILE = "config.json"

def safe_load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_config_has_keys(cfg: dict):
    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

TAKEOFF_RE = re.compile(r"\b(take\s*off|takeoff)\b", re.IGNORECASE)
LANDED_RE = re.compile(r"\b(landed)\b", re.IGNORECASE)
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
    s = subject.lower()

    if NOGO_RE.search(s):
        event = "NO_GO"
    elif GOVOLO_RE.search(s):
        event = "GO"
    elif TAKEOFF_RE.search(s):
        event = "TAKEOFF"
    elif LANDED_RE.search(s):
        event = "LANDED"
    else:
        return None

    for drone, alias_list in aliases.items():
        for alias in alias_list:
            if alias.lower() in s:
                return drone, event, ""
    return None

def compute_timer(start_dt):
    if not start_dt:
        return "—"
    delta = now_local() - start_dt
    sec = int(delta.total_seconds())
    return f"{sec//60:02d}:{sec%60:02d}"

def border_color(state):
    return "#ff3b3b" if state=="IN_VOLO" else "#f7c948" if state=="NO_GO" else "#39d98a"

def status_label(state):
    return "IN VOLO" if state=="IN_VOLO" else "NO GO" if state=="NO_GO" else "A TERRA"

def fetch_data(cfg):
    aliases = cfg.get("aliases", {})
    model = {k: {"state":"A_TERRA","timer":None,"last":"—"} for k in aliases}

    try:
        mail = imaplib.IMAP4_SSL(cfg["imap"]["server"])
        mail.login(cfg["imap"]["email_user"], cfg["imap"]["email_pass"])
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-100:]

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subj = decode_subject(msg.get("Subject",""))

            parsed = parse_subject(subj, aliases)
            if not parsed:
                continue

            drone, event, _ = parsed
            now = now_local()

            if event=="TAKEOFF":
                model[drone]["state"]="IN_VOLO"
                model[drone]["timer"]=now
            elif event=="LANDED":
                model[drone]["state"]="A_TERRA"
                model[drone]["timer"]=None
            elif event=="NO_GO":
                model[drone]["state"]="NO_GO"

    except:
        pass

    return model

cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

display_order = list(cfg.get("aliases", {}).keys())
title = cfg.get("ui", {}).get("title","ReADI Control Center")

st.set_page_config(page_title=title, layout="wide")
st.title(title)

model = fetch_data(cfg)

cards_html=""

for drone in display_order:
    info = model[drone]
    state = info["state"]
    color = border_color(state)
    label = status_label(state)
    timer = compute_timer(info["timer"])

    cards_html += f"""
    <div style="border:2px solid {color};border-radius:12px;padding:14px;background:#09111f;color:white;">
        <div style="font-size:18px;font-weight:700;">{drone}</div>
        <div style="background:{color};padding:10px;text-align:center;margin-top:10px;font-weight:700;">
            {label}
        </div>
        <div style="margin-top:8px;font-size:12px;">Timer: {timer}</div>
    </div>
    """

# 🔥 FIX RESPONSIVE CORRETTO
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

/* DESKTOP */
.grid {{
    display:grid;
    grid-template-columns: repeat(5, 1fr);
    gap:16px;
    margin-top:8px;
    margin-bottom:20px;
}}

/* TABLET */
@media (max-width: 1100px) {{
    .grid {{
        grid-template-columns: repeat(3, 1fr);
    }}
}}

/* MOBILE */
@media (max-width: 700px) {{
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
