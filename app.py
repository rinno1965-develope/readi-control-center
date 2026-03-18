import streamlit as st

st.set_page_config(page_title="ReADI Control Center", layout="wide")

# Login semplice con credenziali prese dai secrets
def login():
    st.title("🔐 Accesso ReADI Control Center")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if st.button("Login"):
        if (
            user == st.secrets["auth"]["username"]
            and pwd == st.secrets["auth"]["password"]
        ):
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
st.title("🚁 ReADI Control Center")
st.subheader("Accesso protetto attivo")

col1, col2, col3 = st.columns(3)
col1.metric("Droni", "0")
col2.metric("Stato", "ONLINE")
col3.metric("Aggiornamento", "LIVE")

st.divider()

st.dataframe([
    {"Drone": "ALPHA", "Stato": "A TERRA", "Batteria": "—"},
    {"Drone": "BRAVO", "Stato": "A TERRA", "Batteria": "—"},
])
