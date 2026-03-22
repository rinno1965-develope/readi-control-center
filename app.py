# --- (IMPORT UGUALI) ---
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
        raise ValueError("config.json: manca 'imap'")

    cfg["imap"]["email_user"] = os.environ.get("READI_IMAP_USER")
    cfg["imap"]["email_pass"] = os.environ.get("READI_IMAP_PASS")

    if not cfg["imap"]["email_user"] or not cfg["imap"]["email_pass"]:
        raise ValueError("Credenziali IMAP mancanti")

# =========================
# PARSER (UGUALE)
# =========================
TAKEOFF_RE = re.compile(r"\b(takeoff|taken off)\b", re.IGNORECASE)
LANDED_RE = re.compile(r"\b(landed)\b", re.IGNORECASE)
NOGO_RE = re.compile(r"\bno go volo\b", re.IGNORECASE)
GOVOLO_RE = re.compile(r"\bgo volo\b", re.IGNORECASE)

def decode_subject(raw):
    if not raw:
        return ""
    parts = decode_header(raw)
    return "".join([
        p.decode(enc or "utf-8", errors="ignore") if isinstance(p, bytes) else p
        for p, enc in parts
    ])

def is_notam_subject(s):
    return s.upper().startswith("NOTAM")

def parse_subject(subject, aliases):
    s = subject.lower()

    if "takeoff" in s:
        event = "TAKEOFF"
    elif "landed" in s:
        event = "LANDED"
    elif "no go volo" in s:
        event = "NO_GO"
    elif "go volo" in s:
        event = "GO"
    else:
        return None

    for drone, alias_list in aliases.items():
        for a in alias_list:
            if a.lower() in s:
                return drone, event, ""

    return None

# =========================
# FETCH (FIX CRITICO)
# =========================
def fetch_data(cfg):
    model = {}
    notams = []

    try:
        mail = imaplib.IMAP4_SSL(cfg["imap"]["server"], 993)
        mail.login(cfg["imap"]["email_user"], cfg["imap"]["email_pass"])
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        ids = data[0].split()[-200:]

        for num in ids:
            status, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subj = decode_subject(msg.get("Subject", ""))

            if is_notam_subject(subj):
                notams.append({"Messaggio": subj})
                continue

            parsed = parse_subject(subj, cfg["aliases"])
            if not parsed:
                continue

            drone, event, _ = parsed

            model[drone] = {
                "state": event,
                "last": subj,
                "time": now_local()
            }

        mail.logout()

    except Exception as e:
        st.error(str(e))

    return model, notams

# =========================
# INIT
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

st.set_page_config(layout="wide")

st_autorefresh(interval=5000, key="refresh")

# =========================
# FETCH UNA SOLA VOLTA
# =========================
model, notams = fetch_data(cfg)

# =========================
# HEADER
# =========================
col1, col2 = st.columns([1,6])

with col1:
    st.image("aiview.png", width=120)

with col2:
    st.title("ReADI Control Center AiviewGroup-OPS")

# =========================
# GRID RESPONSIVE (FIX MOBILE)
# =========================
cards_html = ""

for drone, info in model.items():

    color = "#39d98a"
    if info["state"] == "NO_GO":
        color = "#f7c948"
    if info["state"] == "TAKEOFF":
        color = "#ff3b3b"

    cards_html += f"""
    <div style="border:2px solid {color}; padding:12px; border-radius:10px;">
        <b>{drone}</b><br><br>
        <div style="background:{color}; padding:10px; text-align:center;">
            {info["state"]}
        </div>
        <div style="font-size:12px;">
            {info["last"]}
        </div>
    </div>
    """

components.html(f"""
<style>
.grid {{
 display:grid;
 grid-template-columns: repeat(5,1fr);
 gap:10px;
}}
@media(max-width:900px){{
 .grid {{grid-template-columns: repeat(2,1fr);}}
}}
</style>

<div class="grid">
{cards_html}
</div>
""", height=800)

# =========================
# NOTAM
# =========================
st.subheader("NOTAM")

if notams:
    st.write(notams)
else:
    st.info("Nessun NOTAM")
