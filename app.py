"""Dashboard PLM Intelligence. Lancement : python -m streamlit run app.py"""
import streamlit as st

from plm.model import DATA_XML, load_model
from ui import chat, explorer, impacts, risks, theme
from ui.state import MAIN_EXPLORER, MAIN_IMPACTS, MAIN_RISKS, keep_widget_state

st.set_page_config(page_title="PLM Intelligence", page_icon="⚙️", layout="wide")
theme.inject_css()
keep_widget_state()


@st.cache_resource(show_spinner="Lecture de l'export PLM…")
def get_model(_modified):
    return load_model()


model = get_model(DATA_XML.stat().st_mtime)

chat.render(model)

theme.html('<div class="plm-header"><h1>PLM Intelligence · E-drive avant 410 kW</h1></div>')

tabs = st.tabs([MAIN_EXPLORER, MAIN_RISKS, MAIN_IMPACTS], key="main_tab", on_change="rerun")
with tabs[0]:
    if tabs[0].open:
        explorer.render(model)
with tabs[1]:
    if tabs[1].open:
        risks.render(model)
with tabs[2]:
    if tabs[2].open:
        impacts.render(model)
