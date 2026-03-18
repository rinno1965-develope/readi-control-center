import streamlit as st

st.set_page_config(page_title="ReADI Control Center", layout="wide")

# Login semplice con credenziali prese dai secrets
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

# Dashboard base protetta
import streamlit as st

st.set_page_config(layout="wide")

st.title("🚁 ReADI Control Center")

# 👉 DATI DI TEST (poi li rendiamo live)
drones = {
    "ALPHA": {"state": "NO_GO"},
    "BRAVO": {"state": "A_TERRA"},
    "CHARLIE": {"state": "NO_GO"},
    "DELTA": {"state": "A_TERRA"},
    "ECHO": {"state": "A_TERRA"},
    "FOXTROT": {"state": "A_TERRA"},
    "GOLF": {"state": "A_TERRA"},
    "HOTEL": {"state": "NO_GO"},
    "INDIA": {"state": "NO_GO"},
    "A35 ADDA NORD": {"state": "IN_VOLO"},
}

# 🎨 colori
def get_color(state):
    if state == "IN_VOLO":
        return "#ff3b3b"
    elif state == "NO_GO":
        return "#f7c948"
    else:
        return "#39d98a"

def get_label(state):
    if state == "IN_VOLO":
        return "IN VOLO"
    elif state == "NO_GO":
        return "NO GO"
    else:
        return "A TERRA"

# 📦 layout a griglia
cols = st.columns(5)

i = 0
for drone, info in drones.items():
    col = cols[i % 5]
    with col:
        color = get_color(info["state"])
        label = get_label(info["state"])

        st.markdown(f"""
        <div style="
            border:2px solid {color};
            padding:10px;
            margin-bottom:10px;
            border-radius:10px;
            text-align:center;
            background-color:#111;
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
        </div>
        """, unsafe_allow_html=True)

    i += 1
