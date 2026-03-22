import json
import re
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh


# =========================
# TIMEZONE FIX 🔥 (SOLO QUESTO CAMBIA)
# =========================
LOCAL_TZ = ZoneInfo("Europe/Rome")

def now_local():
    return datetime.now(LOCAL_TZ)


# =========================
# CONFIG
# =========================
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

aliases = cfg.get("aliases", {})
imap_cfg = cfg.get("imap", {})
poll_seconds = int(cfg.get("poll_seconds", 15))


# =========================
# REGEX
# =========================
TAKEOFF_RE = re.compile(r"take", re.IGNORECASE)
LANDED_RE = re.compile(r"land", re.IGNORECASE)
NOGO_RE = re.compile(r"no go", re.IGNORECASE)


# =========================
# UTILS
# =========================
def compute_timer(start_dt):
    if not start_dt:
        return "—"
    delta = now_local() - start_dt.astimezone(LOCAL_TZ)
    sec = int(delta.total_seconds())
    return f"{sec//60:02d}:{sec%60:02d}"


def color(state):
    return "#ff3b3b" if state == "IN_VOLO" else "#f7c948" if state == "NO_GO" else "#39d98a"


# =========================
# FETCH IMAP (IDENTICO AL TUO)
# =========================
def fetch_data():
    model = {d: {"state": "A_TERRA", "timer_start_dt": None} for d in aliases}

    try:
        mail = imaplib.IMAP4_SSL(imap_cfg["server"])
        mail.login(imap_cfg["email_user"], imap_cfg["email_pass"])
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-50:]

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = msg.get("Subject", "").lower()

            msg_dt = parsedate_to_datetime(msg.get("Date"))
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)

            for drone in aliases:
                if drone.lower() in subject:

                    if TAKEOFF_RE.search(subject):
                        model[drone]["state"] = "IN_VOLO"
                        model[drone]["timer_start_dt"] = msg_dt

                    elif LANDED_RE.search(subject):
                        model[drone]["state"] = "A_TERRA"
                        model[drone]["timer_start_dt"] = None

                    elif NOGO_RE.search(subject):
                        model[drone]["state"] = "NO_GO"

        mail.logout()

    except Exception as e:
        st.warning(f"IMAP error: {e}")

    return model


# =========================
# UI
# =========================
st.set_page_config(layout="wide")

st_autorefresh(interval=poll_seconds * 1000)

st.caption(f"🔄 Ultimo refresh: {now_local().strftime('%H:%M:%S')}")


# =========================
# DATA
# =========================
model = fetch_data()


# =========================
# CARDS
# =========================
cards = ""

for drone, info in model.items():
    state = info["state"]
    flash = "blink" if state == "IN_VOLO" else ""

    cards += f"""
    <div style="border:2px solid {color(state)}; padding:12px; border-radius:12px;">
        <b>{drone}</b>
        <div class="{flash}" style="background:{color(state)}; padding:10px; text-align:center;">
            {state.replace("_", " ")}
        </div>
        <div>Timer: {compute_timer(info.get("timer_start_dt"))}</div>
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
{cards}
</div>
"""

components.html(html, height=900)
