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
# SESSION
# -------------------------
if "logged" not in st.session_state:
    st.session_state["logged"] = False

if not st.session_state["logged"]:
    login()
    st.stop()

# -------------------------
# UI
# -------------------------
st.set_page_config(layout="wide")
st.title("🚁 ReADI Control Center")

# -------------------------
# DATI DEMO
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
# BUILD HTML
# -------------------------
cards_html = ""

for drone in droni:
    stato = random.choice(stati)
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

# -------------------------
# GRID
# -------------------------
full_html = f"""
<div style="
display:grid;
grid-template-columns: repeat(5, 1fr);
gap:20px;
">
{cards_html}
</div>
"""

# 🚀 QUESTO È IL FIX VERO
st.html(full_html)
