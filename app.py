import streamlit as st
from datetime import datetime
import random

# -------------------------
# CONFIG LOGIN
# -------------------------
USERNAME = "admin"
PASSWORD = "readi123"

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

# -------------------------
# INIT SESSION
# -------------------------
if "logged" not in st.session_state:
    st.session_state["logged"] = False

if not st.session_state["logged"]:
    login()
    st.stop()

# -------------------------
# UI HEADER
# -------------------------
st.set_page_config(layout="wide")

st.title("🚁 ReADI Control Center")

# -------------------------
# DATI DEMO (poi li colleghiamo ai tuoi veri)
# -------------------------
droni = [
    "ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO",
    "FOXTROT", "GOLF", "HOTEL", "INDIA", "A35 ADDA NORD"
]

stati = ["A TERRA", "IN VOLO", "NO GO"]

def get_color(stato):
    if stato == "IN VOLO":
        return "#ff3b3b"
    elif stato == "NO GO":
        return "#f7c948"
    else:
        return "#39d98a"

# -------------------------
# GRID
# -------------------------
cols = st.columns(5)

for i, drone in enumerate(droni):
    stato = random.choice(stati)
    color = get_color(stato)
    now = datetime.now().strftime("%H:%M:%S")

    card_html = f"""
    <div style="
        border:2px solid {color};
        border-radius:12px;
        padding:15px;
        margin-bottom:15px;
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

    cols[i % 5].markdown(card_html, unsafe_allow_html=True)
