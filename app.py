# =========================
# LOAD CONFIG
# =========================
try:
    cfg = safe_load_json(CONFIG_FILE)
    ensure_config_has_keys(cfg)
except Exception as e:
    st.error(f"Errore config: {e}")
    st.stop()

display_order = list(cfg.get("aliases", {}).keys())

# 🔥 FIX UI DA JSON
UI = cfg.get("ui", {})
title = UI.get("title", "ReADI Control Center")
logo_path = UI.get("logo_path", "")

poll_seconds = int(cfg.get("poll_seconds", 3))


# =========================
# HEADER + REFRESH
# =========================
st.set_page_config(page_title=title, layout="wide")

col_top_1, col_top_2, col_top_3 = st.columns([1, 6, 1])

# 🔄 BUTTON
with col_top_1:
    if st.button("🔄 Aggiorna stato", use_container_width=True):
        model, notams, connected, error_msg = fetch_control_center_data(cfg)
        st.session_state["cc_model"] = model
        st.session_state["cc_notams"] = notams
        st.session_state["cc_connected"] = connected
        st.session_state["cc_error"] = error_msg
        st.session_state["cc_last_refresh"] = datetime.now()
        st.rerun()

# 🧠 TITLE
with col_top_2:
    st.markdown(f"## {title}")

# 🖼️ LOGO (SAFE)
with col_top_3:
    if logo_path:
        try:
            st.image(logo_path, width=80)
        except Exception:
            pass

# 🔄 BUTTON
with col_top_1:
    if st.button("🔄 Aggiorna stato", use_container_width=True):
        model, notams, connected, error_msg = fetch_control_center_data(cfg)
        st.session_state["cc_model"] = model
        st.session_state["cc_notams"] = notams
        st.session_state["cc_connected"] = connected
        st.session_state["cc_error"] = error_msg
        st.session_state["cc_last_refresh"] = datetime.now()
        st.rerun()

# 🧠 TITLE
with col_top_2:
    st.markdown(f"## {title}")

# 🖼️ LOGO (SAFE)
with col_top_3:
    if logo_path:
        try:
            st.image(logo_path, width=80)
        except Exception:
            pass
