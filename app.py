"""USMLE ECO-SYSTEM V2 — App orchestrator.

UI modules live in ui/ and each handles one tab.
This file ties them together and handles top-level layout.
"""

import streamlit as st

from ui.sidebar import render_sidebar
from ui.dashboard import render_dashboard
from ui.study import render_study
from ui.targeted import render_targeted
from ui.analytics import render_analytics
from ui.history import render_history

# Startup (init_db, session state, backup) runs automatically
# when ui.state is imported by dashboard & study modules.

# ==============================================================================
# SIDEBAR
# ==============================================================================
api_key, dificuldade = render_sidebar()

# ==============================================================================
# MAIN UI
# ==============================================================================
st.title("USMLE ECO-SYSTEM V2")

tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Dashboard",
    "🎯 Targeted Practice",
    "📊 Analytics",
    "📜 History",
])

# -- Tab 1: Dashboard / Study Mode --
with tab1:
    if st.session_state.get("modo_estudo") is None:
        render_dashboard(api_key, dificuldade)
    else:
        render_study(api_key, dificuldade)

# -- Tab 2: Targeted Practice --
with tab2:
    render_targeted(api_key, dificuldade)

# -- Tab 3: Analytics --
with tab3:
    render_analytics()

# -- Tab 4: History --
with tab4:
    render_history()
