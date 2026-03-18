import json
import os
import re
import imaplib
import email
import email.message
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
CONFIG_FILE = "config.json"

def safe_load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_config_has_keys(cfg):
    if "imap" not in cfg:
        raise ValueError("Manca sezione imap")

    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

    if not cfg["imap"]["email_user"]:
        raise ValueError("Email IMAP mancante")


# =========================
# PARSER
# =========================
TAKEOFF_RE = re.compile(r"takeoff|take off", re.I)
LANDED_RE = re.compile(r"landed|landing", re.I)
NOGO_RE = re.compile(r"no go volo", re.I)
GO_RE = re.compile(r"go volo", re.I)


def decode_subject(s):
    if not s:
        return ""
    decoded = decode_header(s)
    out = ""
    for part, enc in decoded:
        if isinstance(part, bytes):
            out += part.decode(enc or "utf-8", errors="ignore")
        else:
            out += part
    return out


def get_text_body(msg):
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return (part.get_payload(decode=True) or b"").decode(errors="ignore")
        return (msg.get_payload(decode=True) or b"").decode(errors="ignore")
    except:
        return ""


def parse_subject(subject, aliases):
    s = (subject or "").lower()

    if "no go volo" in s:
        event = "NO_GO"
    elif "go volo" in s:
        event = "GO"
    elif TAKEOFF_RE.search(s):
        event = "TAKEOFF"
    elif LANDED_RE.search(s):
        event = "LANDED"
    else:
        return None

    for drone, alias_list in aliases.items():
        for a in alias_list:
            if a.lower() in s:
                return drone, event, ""

    return None


# =========================
# FETCH
# =========================
def fetch_control_center_data(cfg):
    aliases = cfg.get("aliases", {})
    model = {d: {"state": "A_TERRA", "last": "—"} for d in aliases}

    notams = []
    connected = False
    error = ""

    try:
        imap = cfg["imap"]
        mail = imaplib.IMAP4_SSL(imap["server"], int(imap["port"]))
        mail.login(imap["email_user"], imap["email_pass"])
        mail.select("INBOX")
        connected = True

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-200:]

        for i in ids:
            _, msg_data = mail.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subj = decode_subject(msg.get("Subject", ""))
            body = get_text_body(msg)

            if subj.upper().startswith("NOTAM"):
                notams.append({
                    "Data/Ora": "",
                    "PIC": msg.get("From", ""),
                    "Messaggio": body or subj
                })
                continue

            parsed = parse_subject(subj, aliases)
            if not parsed:
                continue

            drone, event, _ = parsed

            if event == "TAKEOFF":
                model[drone]["state"] = "IN_VOLO"
                model[drone]["last"] = "TAKEOFF"

            elif event == "LANDED":
                model[drone]["state"] = "A_TERRA"
                model[drone]["last"] = "LANDED"

            elif event == "NO_GO":
                model[drone]["state"] = "NO_GO"
                model[drone]["last"] = "NO GO"

            elif event == "GO":
                model[drone]["state"] = "A_TERRA"
                model[drone]["last"] = "GO"

        mail.logout()

    except Exception as e:
        error = str(e)

    return model, notams, connected, error


# =========================
# LOAD CONFIG
# =========================
cfg = safe_load_json(CONFIG_FILE)
ensure_config_has_keys(cfg)

aliases = cfg.get("aliases", {})
title = cfg.get("ui", {}).get("title", "ReADI Control Center")


# =========================
# UI
# =========================
st.set_page_config(layout="wide")

if st.button("🔄 Aggiorna"):
    st.session_state.clear()

if "data" not in st.session_state:
    st.session_state["data"] = fetch_control_center_data(cfg)

model, notams, connected, error = st.session_state["data"]

st.title(title)

if error:
    st.error(error)

# =========================
# CARDS
# =========================
cols = st.columns(5)

i = 0
for drone, info in model.items():
    col = cols[i % 5]
    color = "green"
    if info["state"] == "NO_GO":
        color = "orange"
    if info["state"] == "IN_VOLO":
        color = "red"

    col.markdown(f"""
    **{drone}**

    <div style="background:{color};padding:10px;text-align:center;">
    {info['state']}
    </div>

    <small>{info['last']}</small>
    """, unsafe_allow_html=True)

    i += 1


# =========================
# NOTAM
# =========================
st.markdown("## NOTAM")

if not notams:
    st.info("Nessun NOTAM")
else:
    st.dataframe(notams)
