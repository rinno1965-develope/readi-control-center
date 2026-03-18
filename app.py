import streamlit as st
import json
import os
import imaplib
import email
from email.header import decode_header

st.set_page_config(layout="wide")

st.title("🚁 ReADI Control Center")

STATE_FILE = "state.json"

def decode_subject(raw):
    if not raw:
        return ""
    parts = decode_header(raw)
    out = ""
    for p, enc in parts:
        if isinstance(p, bytes):
            out += p.decode(enc or "utf-8", errors="ignore")
        else:
            out += p
    return out

def read_mail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmx.com")
        mail.login("readi.controlcenter@gmx.com", "Aibotix7805!")
        mail.select("inbox")

        _, messages = mail.search(None, "ALL")
        ids = messages[0].split()[-10:]

drones_dict = {}

for i in ids:
    _, msg_data = mail.fetch(i, "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])
    subject = decode_subject(msg["Subject"])

    if "ALPHA" in subject:
        drones_dict["ALPHA"] = {
            "Drone": "ALPHA",
            "Stato": "Online",
            "Batteria": "78%"
        }

    if "BRAVO" in subject:
        drones_dict["BRAVO"] = {
            "Drone": "BRAVO",
            "Stato": "Standby",
            "Batteria": "55%"
        }

drones = list(drones_dict.values())

        return drones

    except:
        return []

drones = read_mail()

col1, col2, col3 = st.columns(3)

col1.metric("Droni", len(drones))
col2.metric("Stato", "ONLINE")
col3.metric("Aggiornamento", "LIVE")

st.divider()

st.dataframe(drones if drones else [{"Status": "No data yet"}])
