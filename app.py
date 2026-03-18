import streamlit as st
from datetime import datetime
import imaplib
import email
from email.header import decode_header

# -------------------------
# CONFIG LOGIN
# -------------------------
USERNAME = "admin"
PASSWORD = "readi123"

# -------------------------
# CONFIG MAIL (METTI I TUOI)
# -------------------------
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "TUA_MAIL"
EMAIL_PASSWORD = "TUA_PASSWORD"

# -------------------------
# LOGIN
# -------------------------
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

# -------------------------
# DECODE SUBJECT
# -------------------------
def decode_subject(raw):
    parts = decode_header(raw)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="ignore")
        else:
            result += part
    return result

# -------------------------
# LEGGI EMAIL
# -------------------------
def get_latest_events():
    events = {}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-20:]  # ultime 20 mail

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = decode_subject(msg["Subject"]).upper()

            for drone in DRONI:
                if drone in subject:
                    if "TAKEOFF" in subject:
                        events[drone] = "IN VOLO"
                    elif "LANDED" in subject:
                        events[drone] = "A TERRA"
                    elif "NO GO" in subject:
                        events[drone] = "NO GO"

        mail.logout()

    except Exception as e:
        st.error(f"Errore IMAP: {e}")

    return events

# -------------------------
# DRONI
# -------------------------
DRONI = [
    "ALPHA","BRAVO","CHARLIE","DELTA","ECHO",
    "FOXTROT","GOLF","HOTEL","INDIA","A35 ADDA NORD"
]

# -------------------------
# COLORI
# -------------------------
def get_color(stato):
    return {
        "IN VOLO": "#ff3b3b",
        "NO GO": "#f7c948",
        "A TERRA": "#39d98a"
    }.get(stato, "#999")

# -------------------------
# REFRESH
# -------------------------
if "last_update" not in st.session_state:
    st.session_state["last_update"] = None

st.set_page_config(layout="wide")
st.title("🚁 ReADI Control Center")

if st.button("🔄 Aggiorna"):
    st.session_state["events"] = get_latest_events()
    st.session_state["last_update"] = datetime.now()

events = st.session_state.get("events", {})

# -------------------------
# BUILD HTML
# -------------------------
cards_html = ""

for drone in DRONI:
    stato = events.get(drone, "A TERRA")
    color = get_color(stato)
    now = datetime.now().strftime("%H:%M:%S")

    cards_html += f"""
    <div style="
        border:2px solid {color};
        border-radius:12px;
        padding:15px;
        background:#0f172a;
        color:white;
    ">
        <h3 style="text-align:center;">{drone}</h3>

        <div style="
            background:{color};
            padding:10px;
            border-radius:6px;
            font-weight:bold;
            color:black;
            text-align:center;
        ">
            {stato}
        </div>

        <div style="
            margin-top:10px;
            font-size:12px;
            text-align:center;
            color:#aaa;
        ">
            Last update: {now}
        </div>
    </div>
    """

full_html = f"""
<div style="
display:grid;
grid-template-columns: repeat(5, 1fr);
gap:20px;
">
{cards_html}
</div>
"""

st.html(full_html)
