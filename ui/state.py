"""État de navigation partagé : pièce ouverte, onglet actif, paramètres conservés entre onglets."""
import streamlit as st

MAIN_EXPLORER = ":material/account_tree: Product Explorer"
MAIN_RISKS = ":material/warning: Risques et interdépendances"
MAIN_IMPACTS = ":material/analytics: Analyse d'impacts"
MAIN_VERSIONS = ":material/history: Suivi de versions"
EXPLORER_TREE = "Arborescence et fiche"

# Streamlit oublie l'état d'un widget qui n'est plus affiché : on le fige pour retrouver ses réglages en changeant d'onglet.
# Liste explicite : les tableaux avec sélection et les éditeurs de données refusent qu'on réécrive leur état.
PERSISTENT_KEYS = ("explorer_tab", "bom_groups", "bom_families", "bom_maturities", "map_metric", "risk_detail_part")


def reset_for_xml():
    """Évite de conserver les pièces, filtres et simulations d'un autre fichier."""
    for key in list(st.session_state):
        if key in PERSISTENT_KEYS or str(key).startswith("ia_") or key in ("selected_id", "chat_messages", "pending_question"):
            del st.session_state[key]


def keep_widget_state():
    for key in list(st.session_state.keys()):
        if key in PERSISTENT_KEYS or str(key).startswith(("ia_", "risk_priority_")):
            st.session_state[key] = st.session_state[key]


def selected_id():
    """Identifiant de la pièce dont la fiche est ouverte, ou None."""
    return st.session_state.get("selected_id")


def select_node(node_id):
    st.session_state.selected_id = node_id


def close_detail():
    st.session_state.selected_id = None


def open_part(node_id):
    """Ouvre la fiche d'une pièce depuis n'importe quel écran."""
    st.session_state.selected_id = node_id
    st.session_state.main_tab = MAIN_EXPLORER
    st.session_state.explorer_tab = EXPLORER_TREE


def open_from_table(table_key, node_ids):
    """Rappel pour st.dataframe : la ligne cochée ouvre la fiche correspondante, s'il y en a une."""

    def callback():
        rows = st.session_state[table_key].selection.rows
        if rows and node_ids[rows[0]]:
            open_part(node_ids[rows[0]])

    return callback
