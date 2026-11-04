"""Dashboard PLM Intelligence. Lancement : streamlit run app.py"""
import streamlit as st

from plm.model import DATA_XML, load_model
from ui import chat, explorer, risks, theme
from ui.state import MAIN_EXPLORER, MAIN_RISKS, keep_widget_state

st.set_page_config(page_title="PLM Intelligence", page_icon="⚙️", layout="wide", initial_sidebar_state="expanded")
theme.inject_css()
keep_widget_state()


@st.cache_resource(show_spinner="Lecture de l'export PLM…")
def get_model(_modified):
    return load_model()


model = get_model(DATA_XML.stat().st_mtime)

with st.sidebar:
    chat.render(model)

theme.html(
    '<div class="plm-header"><h1>PLM Intelligence · E-drive avant 410 kW</h1>'
    "<span>Structure, masses et matériaux : export XML de l'OEM. Coûts, fournisseurs, maturités et historiques : données simulées, fournisseurs et événements fictifs.</span></div>"
)

tabs = st.tabs([MAIN_EXPLORER, MAIN_RISKS], key="main_tab", on_change="rerun")
with tabs[0]:
    if tabs[0].open:
        explorer.render(model)
with tabs[1]:
    if tabs[1].open:
        risks.render(model)
