import streamlit as st
from datetime import datetime
import imaplib
import email
from email.header import decode_header

# -------------------------
# LOGIN
# -------------------------
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

# -------------------------
# CONFIG GMX (METTI LE TUE)
# -------------------------
IMAP_SERVER = "imap.gmx.com"
EMAIL_ACCOUNT = "readi.controlcenter@gmx.com"
EMAIL_PASSWORD = "Aibotix7805!"

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
# PARSER SUBJECT (ROBUSTO)
# -------------------------
def clean_subject(subject):
    s = subject.upper()

    # pulizia spam / reply
    for junk in ["RE:", "FWD:", "[SPAM]", "[EXTERNAL]"]:
        s = s.replace(junk, "")

    return s.strip()

# -------------------------
# LETTURA EMAIL
# -------------------------
def get_latest_events():
    events = {}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")

        if status != "OK":
            st.error("Errore ricerca email")
            return events

        ids = data[0].split()[-20:]

        st.write("📡 EMAIL TROVATE:", len(ids))

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject_raw = decode_subject(msg["Subject"])
            subject = clean_subject(subject_raw)

            st.write("✉️ SUBJECT:", subject)  # DEBUG

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
        st.error(f"❌ ERRORE IMAP: {e}")

    return events

# -------------------------
# UI
# -------------------------
st.set_page_config(layout="wide")
st.title("🚁 ReADI Control Center")

if st.button("🔄 Aggiorna stato"):
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
