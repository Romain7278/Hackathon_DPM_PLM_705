"""Suivi des écarts entre l'export étudié et un second fichier XML."""
from io import BytesIO
from hashlib import sha256
from xml.etree import ElementTree as ET

import streamlit as st

from plm.version_diff import IncompatibleFormat, compare, compare_context, validate_format
from plm.model import load_model
from plm.impact import compare_models
from plm_parser import parse_plm
from ui.impacts import render_cards


@st.cache_data(show_spinner="Comparaison des exports…", max_entries=8)
def compare_files(reference_bytes, candidate_bytes):
    validate_format(reference_bytes, candidate_bytes)
    reference = parse_plm(BytesIO(reference_bytes))
    candidate = parse_plm(BytesIO(candidate_bytes))
    return compare(reference, candidate), compare_context(reference, candidate)


@st.cache_data(show_spinner="Calcul des indicateurs des deux fichiers…", max_entries=8)
def compare_indicators(reference_bytes, candidate_bytes, risk_priorities=()):
    rows, _ = compare_files(reference_bytes, candidate_bytes)
    reference = load_model(BytesIO(reference_bytes), risk_priorities=dict(risk_priorities))
    candidate = load_model(BytesIO(candidate_bytes), risk_priorities=dict(risk_priorities))
    return compare_models(reference, candidate, [row['id'] for row in rows if row['status'] == 'Modifié'])


def render(model, reference_path):
    st.markdown("### Suivi de versions")
    st.caption(f"Référence : {reference_path.name}. Le fichier chargé est comparé à cette référence sans la remplacer.")
    uploaded = st.file_uploader("Charger le XML à comparer", type=["xml"], key="version_xml")
    st.caption("Comparaison par identifiant PLM : révisions, masse, matériau, maturité, composition, positions, fournisseurs, coûts, historique et interfaces, selon les données présentes dans les exports.")
    if uploaded is None:
        st.info("Chargez un second export XPDMXML pour afficher les écarts par pièce.")
        return
    try:
        reference_bytes, candidate_bytes = reference_path.read_bytes(), uploaded.getvalue()
        rows, context = compare_files(reference_bytes, candidate_bytes)
    except IncompatibleFormat:
        st.error("Le format du fichier est incompatible.")
        return
    except (ET.ParseError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        st.error(f"Impossible de comparer ce fichier : {error}")
        return
    fingerprint = (sha256(reference_bytes).hexdigest(), sha256(candidate_bytes).hexdigest())
    if st.button("Comparer les indicateurs", icon=":material/compare_arrows:", key="compare_version_indicators"):
        st.session_state.version_indicators_for = fingerprint
    if st.session_state.get('version_indicators_for') == fingerprint:
        try:
            result = compare_indicators(reference_bytes, candidate_bytes, tuple(sorted(model.risk_priorities.items())))
        except (ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError, RecursionError) as error:
            st.error(f"Impossible de calculer les indicateurs de ce fichier : {error}")
        else:
            st.markdown("#### Évolution des indicateurs")
            st.caption("Référence : fichier étudié · Comparé : fichier chargé. Calcul sur la nomenclature complète de chaque export, avec les mêmes règles que l’analyse d’impacts.")
            render_cards(model, result, comparison_label="Comparé", show_shares=False)
    rows = [row for row in rows if row['status'] in ('Modifié', 'Inchangé')]
    counts = {status: sum(row["status"] == status for row in rows) for status in ("Modifié", "Inchangé")}
    for column, (status, count) in zip(st.columns(2), counts.items()):
        column.metric({"Modifié": "Modifiés", "Inchangé": "Inchangés"}[status], count)
    status = st.multiselect("État des éléments", list(counts), default=["Modifié"])
    query = st.text_input("Rechercher une pièce", placeholder="Nom ou identifiant PLM")
    filtered = [r for r in rows if r["status"] in status and query.casefold() in f"{r['name']} {r['id']}".casefold()]
    st.dataframe([{"Élément": r["name"], "ID PLM": r["id"], "Type": {"part": "Pièce", "wrapper": "Référence", "assembly": "Assemblage"}.get(r["kind"], r["kind"]), "État": r["status"], "Champs différents": len(r["changes"])} for r in filtered], hide_index=True, width="stretch")
    if filtered:
        options = {r["id"]: r for r in filtered}
        selected = st.selectbox("Détail des écarts par élément", list(options), format_func=lambda key: f"{options[key]['name']} · {key}")
        changes = options[selected]["changes"]
        if changes:
            st.dataframe(changes, hide_index=True, width="stretch")
        else:
            st.success("Toutes les données lues sont identiques pour cet élément.")
    elif rows and all(r["status"] == "Inchangé" for r in rows) and not context:
        st.success("Les éléments communs aux deux exports contiennent les mêmes données.")
    else:
        st.info("Aucun élément ne correspond aux filtres.")
    if context:
        with st.expander("Écarts des données générales et des référentiels"):
            st.dataframe(context, hide_index=True, width="stretch")
