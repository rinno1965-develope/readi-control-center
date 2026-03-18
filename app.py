import json
import os
import re
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

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
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

IMAP_SERVER = cfg["imap"]["server"]
IMAP_PORT = cfg["imap"]["port"]

EMAIL_USER = os.environ.get("READI_IMAP_USER")
EMAIL_PASS = os.environ.get("READI_IMAP_PASS")

ALIASES = cfg["aliases"]
DRONI = list(ALIASES.keys())

# =========================
# REGEX EVENTI
# =========================
TAKEOFF_RE = re.compile(r"(take\s*off|takeoff)", re.IGNORECASE)
LANDED_RE = re.compile(r"(landed|landing)", re.IGNORECASE)
NOGO_RE = re.compile(r"(no\s*go\s*volo)", re.IGNORECASE)
GOVOLO_RE = re.compile(r"(go\s*volo)", re.IGNORECASE)

# =========================
# UTILS SICURI
# =========================
def decode_subject(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for p, enc in parts:
        try:
            if isinstance(p, bytes):
                out += p.decode(enc or "utf-8", errors="ignore")
            else:
                out += p
        except:
            pass
    return out

def parse_subject(subject):
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

    for drone, aliases in ALIASES.items():
        for a in aliases:
            if a.lower() in s:
                return drone, event

    return None

def parse_date(msg):
    raw = msg.get("Date")

    if not raw:
        return None

    try:
        dt = parsedate_to_datetime(raw)
    except:
        return None

    if dt is None:
        return None

    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone()
    except:
        return None

def timer(start):
    if not start:
        return "--"
    try:
        sec = int((datetime.now(timezone.utc) - start).total_seconds())
        return f"{sec//60:02d}:{sec%60:02d}"
    except:
        return "--"

def color(s):
    if s == "IN_VOLO":
        return "#ff3b3b"
    elif s == "NO_GO":
        return "#f7c948"
    else:
        return "#39d98a"

# =========================
# FETCH MAIL (ULTRA SAFE)
# =========================
def fetch_data():
    model = {
        d: {"state": "A_TERRA", "last": "—", "start": None}
        for d in DRONI
    }

    try:
        if not EMAIL_USER or not EMAIL_PASS:
            st.error("Credenziali email mancanti (ENV)")
            return model

        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-200:]

        for num in ids:
            try:
                _, msg_data = mail.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                subj = decode_subject(msg.get("Subject", ""))
                parsed = parse_subject(subj)

                if not parsed:
                    continue

                drone, event = parsed
                dt = parse_date(msg)

                t = dt.strftime("%H:%M:%S") if dt else "--:--"

                if event == "TAKEOFF":
                    model[drone]["state"] = "IN_VOLO"
                    model[drone]["last"] = f"{t} TAKEOFF"
                    model[drone]["start"] = dt

                elif event == "LANDED":
                    model[drone]["state"] = "A_TERRA"
                    model[drone]["last"] = f"{t} LANDED"
                    model[drone]["start"] = None

                elif event == "NO_GO":
                    model[drone]["state"] = "NO_GO"
                    model[drone]["last"] = f"{t} NO GO"
                    model[drone]["start"] = None

            except:
                continue

        mail.logout()

    except Exception as e:
        st.error(f"Errore IMAP: {e}")

    return model

# =========================
# UI
# =========================
st.title("🚁 ReADI Control Center")

col1, col2, col3 = st.columns([1,6,1])

with col1:
    if st.button("🔄"):
        st.session_state["data"] = fetch_data()
        st.rerun()

with col3:
    st.image("aiview.png", width=70)

if "data" not in st.session_state:
    st.session_state["data"] = fetch_data()

data = st.session_state["data"]

# =========================
# GRID
# =========================
html = ""

for d in DRONI:
    info = data[d]

    html += f"""
    <div style="
        border:2px solid {color(info['state'])};
        border-radius:12px;
        padding:12px;
        background:#09111f;
        color:white;
    ">
        <h3 style="text-align:center">{d}</h3>

        <div style="
            background:{color(info['state'])};
            padding:10px;
            text-align:center;
            font-weight:bold;
            color:black;
        ">
            {info['state']}
        </div>

        <div style="font-size:12px; margin-top:8px;">
            Timer: {timer(info['start'])}
        </div>

        <div style="font-size:12px;">
            {info['last']}
        </div>
    </div>
    """

components.html(f"""
<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;">
{html}
</div>
""", height=700)

# =========================
# FOOTER
# =========================
st.markdown("""
<div style="text-align:center;color:#888;margin-top:20px;">
Developed by Roberto Innocenti - Powered by AiviewGroup
</div>
""", unsafe_allow_html=True)
