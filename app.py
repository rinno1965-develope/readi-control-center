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
# MOBILE DETECT (ROBUSTO)
# =========================
def detect_mobile():
    try:
        ua = st.context.headers.get("user-agent", "").lower()
        return any(k in ua for k in ["iphone", "android", "mobile"])
    except:
        return False

is_mobile = detect_mobile()

# fallback manuale
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
# TOGGLE MODE
# =========================
if not is_mobile:
    if st.sidebar.button("📱 Mobile Mode"):
        st.session_state["force_mobile"] = True
        st.rerun()
else:
    if st.sidebar.button("💻 Desktop Mode"):
        st.session_state["force_mobile"] = False
        st.rerun()

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
    model = {d: {"state": "A_TERRA", "timer": None} for d in display_order}

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
                    model[drone]["timer"] = now_local()
    except:
        pass

    return model

# =========================
# REFRESH
# =========================
st_autorefresh(interval=poll_seconds * 1000, key="refresh")

model = fetch_data()

# =========================
# MOBILE VIEW
# =========================
if is_mobile:
    for drone in display_order:
        st.markdown(f"## {drone}")
        st.markdown(f"**{model[drone]['state']}**")
        st.markdown("---")
    st.stop()

# =========================
# DESKTOP VIEW
# =========================
st.title(title)

cols = st.columns(5)
for i, drone in enumerate(display_order):
    with cols[i % 5]:
        st.markdown(f"### {drone}")
        st.markdown(f"**{model[drone]['state']}**")
