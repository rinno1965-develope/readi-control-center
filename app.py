import streamlit as st
import json
import os

st.set_page_config(layout="wide")

st.title("🚁 ReADI Control Center")

STATE_FILE = "state.json"

drones = []

if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        data = json.load(f)
        drones = data.get("drones", [])

col1, col2, col3 = st.columns(3)

col1.metric("Droni", len(drones))
col2.metric("Stato", "ONLINE")
col3.metric("Aggiornamento", "LIVE")

st.divider()

st.dataframe(drones)