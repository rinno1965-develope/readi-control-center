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
# REGEX
# =========================
TAKEOFF_RE = re.compile(r"(take\s*off|takeoff)", re.IGNORECASE)
LANDED_RE = re.compile(r"(landed|landing)", re.IGNORECASE)
NOGO_RE = re.compile(r"(no\s*go\s*volo)", re.IGNORECASE)
GOVOLO_RE = re.compile(r"(go\s*volo)", re.IGNORECASE)


# =========================
# UTILS SAFE
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


# 🔥 FIX DEFINITIVO (mai più replace su None)
def parse_date(msg):
    raw = msg.get("Date")

    if not raw:
        return None

    try:
        # 🔥 NORMALIZZA STRINGA (FIX GMX)
        raw = str(raw).replace(" (UTC)", "").strip()

        # 🔥 PARSE MANUALE SAFE
        dt = parsedate_to_datetime(raw)

        if dt is None:
            return None

        # 🔥 PROTEZIONE TOTALE
        if dt.tzinfo is None:
            return None  # ← invece di replace, skip

        return dt.astimezone()

    except Exception:
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
# FETCH MAIL + NOTAM
# =========================
def fetch_data():
    model = {
        d: {"state": "A_TERRA", "last": "—", "start": None}
        for d in DRONI
    }

    notam_list = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-200:]

        for num in ids:
            try:
                _, msg_data = mail.fetch(num, "(RFC822)")

                if not msg_data or not msg_data[0]:
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # 🔥 SUBJECT SAFE
                raw_subj = msg.get("Subject", "")
                subj = decode_subject(raw_subj) if raw_subj else ""

                if not subj:
                    continue

                # 🔥 NOTAM
                if "notam" in subj.lower():
                    notam_list.append(subj)

                parsed = parse_subject(subj)
                if not parsed:
                    continue

                drone, event = parsed

                # 🔥 DATE SAFE (QUI ERA IL PROBLEMA)
                dt = None
                try:
                    dt = parse_date(msg)
                except:
                    dt = None

                t = dt.strftime("%H:%M:%S") if dt else "--:--"

                # 🔥 LOGICA EVENTI
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

            except Exception:
                # 🔥 QUI SALVIAMO LA VITA
                continue

        mail.logout()

    except Exception as e:
        st.error(f"Errore IMAP: {e}")

    return model, notam_list

# =========================
# UI
# =========================
col1, col2 = st.columns([1, 8])

with col1:
    st.image("aiview.png", width=60)

with col2:
    st.title("ReADI Control Center AiviewGroup-OPS")

if st.button("🔄 Aggiorna stato"):
    st.session_state["data"], st.session_state["notam"] = fetch_data()
    st.rerun()

if "data" not in st.session_state:
    st.session_state["data"], st.session_state["notam"] = fetch_data()

data = st.session_state["data"]
notam = st.session_state["notam"]


# =========================
# NOTAM
# =========================
if notam:
    st.warning("⚠️ NOTAM ATTIVI")
    for n in notam[:5]:
        st.write("•", n)


# =========================
# CARDS
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
