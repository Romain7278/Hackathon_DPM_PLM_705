"""Dashboard PLM Intelligence. Lancement : python -m streamlit run app.py"""
import streamlit as st
from pathlib import Path
from xml.etree import ElementTree as ET

from plm import quality, scenarios
from plm.model import DATA_XML, load_model
from ui import chat, explorer, impacts, risks, theme, versions
from ui.state import MAIN_EXPLORER, MAIN_IMPACTS, MAIN_RISKS, MAIN_VERSIONS, keep_widget_state, reset_for_xml

st.set_page_config(page_title="PLM Intelligence", page_icon="⚙️", layout="wide")
theme.inject_css()
keep_widget_state()


@st.cache_resource(show_spinner="Lecture de l'export PLM…", max_entries=16)
def get_model(xml_path, modified, rules_modified, risk_priorities):
    return load_model(xml_path, risk_priorities=dict(risk_priorities))


xml_files = {path.name: path for path in sorted(DATA_XML.parent.iterdir()) if path.is_file() and path.suffix.lower() == ".xml"}
if not xml_files:
    st.info("Ajoutez un fichier XML dans le dossier data pour commencer.")
    st.stop()
if st.session_state.get("selected_xml") not in xml_files:
    reset_for_xml()
    st.session_state.selected_xml = DATA_XML.name if DATA_XML.name in xml_files else next(iter(xml_files))
title, file_choice = st.columns([8, 3], vertical_alignment="center")
with title:
    theme.html('<div class="plm-header"><h1>PLM Intelligence · E-drive avant 410 kW</h1></div>')
with file_choice:
    with st.popover("Choisir un fichier XML", icon=":material/folder_open:", width="stretch"):
        st.selectbox("Fichier à étudier", list(xml_files), key="selected_xml", on_change=reset_for_xml)
selected_xml = xml_files[st.session_state.selected_xml]
st.caption(f"Fichier étudié : {selected_xml.name}")
try:
    priorities = tuple((c['key'], st.session_state.get(f"risk_priority_{c['key']}", 'Normal')) for c in scenarios.CRITERIA)
    model = get_model(str(selected_xml), selected_xml.stat().st_mtime_ns, Path(quality.__file__).stat().st_mtime_ns, priorities)
except (ET.ParseError, ValueError, KeyError, TypeError) as error:
    st.error(f"Impossible d’étudier ce fichier : {error}")
    st.stop()

chat.render(model)

tabs = st.tabs([MAIN_EXPLORER, MAIN_RISKS, MAIN_IMPACTS, MAIN_VERSIONS], key="main_tab", on_change="rerun")
with tabs[0]:
    if tabs[0].open:
        explorer.render(model)
with tabs[1]:
    if tabs[1].open:
        risks.render(model)
with tabs[2]:
    if tabs[2].open:
        impacts.render(model)
with tabs[3]:
    if tabs[3].open:
        versions.render(model, selected_xml)
