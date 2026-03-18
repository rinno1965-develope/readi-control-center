import streamlit as st
import random
import time

st.set_page_config(layout="wide")

# ---------------- LOGIN ----------------
USERNAME = "admin"
PASSWORD = "readi123"

if "logged" not in st.session_state:
    st.session_state.logged = False

def login():
    st.title("🔐 ReADI Control Center Login")

    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        if user == USERNAME and pwd == PASSWORD:
            st.session_state.logged = True
            st.rerun()
        else:
            st.error("Credenziali errate")

if not st.session_state.logged:
    login()
    st.stop()

# ---------------- DASHBOARD ----------------

st.title("🚁 ReADI Control Center")

drones = [
    "ALPHA","BRAVO","CHARLIE","DELTA","ECHO",
    "FOXTROT","GOLF","HOTEL","INDIA","A35 ADDA NORD"
]

# Stati possibili
states = ["A_TERRA", "IN_VOLO", "NO_GO"]

# Mantieni stato in sessione
if "drone_states" not in st.session_state:
    st.session_state.drone_states = {
        d: {
            "state": random.choice(states),
            "last": time.strftime("%H:%M:%S")
        } for d in drones
    }

# Simula cambi ogni refresh
for d in drones:
    if random.random() < 0.2:  # 20% cambia stato
        st.session_state.drone_states[d]["state"] = random.choice(states)
        st.session_state.drone_states[d]["last"] = time.strftime("%H:%M:%S")

def get_color(state):
    if state == "IN_VOLO":
        return "#ff3b3b"
    elif state == "NO_GO":
        return "#f7c948"
    else:
        return "#39d98a"

def get_label(state):
    return state.replace("_", " ")

# Layout
cols = st.columns(5)

i = 0
for drone in drones:
    col = cols[i % 5]
    with col:
        info = st.session_state.drone_states[drone]
        color = get_color(info["state"])
        label = get_label(info["state"])

        st.markdown(f"""
        <div style="
            border:2px solid {color};
            padding:12px;
            margin-bottom:12px;
            border-radius:12px;
            text-align:center;
            background-color:#0b0f14;
            color:white;
        ">
            <h4>{drone}</h4>

            <div style="
                background:{color};
                padding:10px;
                border-radius:6px;
                font-weight:bold;
                color:black;
            ">
                {label}
            </div>

            <div style="margin-top:8px; font-size:12px; color:#aaa;">
                Last update: {info["last"]}
            </div>
        </div>
        """, unsafe_allow_html=True)

    i += 1

# Auto refresh
time.sleep(2)
st.rerun()
