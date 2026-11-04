"""État de navigation partagé : pièce sélectionnée, onglet actif, paramètres conservés entre onglets."""
import streamlit as st

MAIN_EXPLORER = "Product Explorer"
MAIN_RISKS = "Risques et impacts"
EXPLORER_TREE = "Arborescence et fiche"

# Streamlit oublie l'état d'un widget qui n'est plus affiché : on le fige pour retrouver ses réglages en changeant d'onglet.
# Liste explicite : les tableaux avec sélection et les éditeurs de données refusent qu'on réécrive leur état.
PERSISTENT_KEYS = (
    "explorer_tab", "risk_tab", "s3_view", "bom_groups", "bom_families", "bom_maturities", "dq_severity", "dq_domain", "map_metric",
    "s1_preset", "s1_part", "s1_supplier", "s1_weeks", "s2_preset", "s2_family", "s2_pct", "s3_exit_supplier",
    "s3_switch_preset", "s3_switch_part", "s3_switch_to", "s3_switch_share", "s4_target", "s4_gate", "s5_perimeter", "s5_feasibility", "s5_weeks",
)


def keep_widget_state():
    for key in list(st.session_state.keys()):
        if key in PERSISTENT_KEYS or str(key).startswith("s5_target_"):
            st.session_state[key] = st.session_state[key]


def selected_id(model):
    if "selected_id" not in st.session_state:
        st.session_state.selected_id = model.tree.id
    return st.session_state.selected_id


def select_node(node_id):
    st.session_state.selected_id = node_id


def open_part(node_id):
    """Ouvre la fiche d'une pièce depuis n'importe quel écran."""
    st.session_state.selected_id = node_id
    st.session_state.main_tab = MAIN_EXPLORER
    st.session_state.explorer_tab = EXPLORER_TREE


def open_from_table(table_key, node_ids):
    """Rappel pour st.dataframe : la ligne cliquée ouvre la fiche correspondante."""

    def callback():
        rows = st.session_state[table_key].selection.rows
        if rows:
            open_part(node_ids[rows[0]])

    return callback
