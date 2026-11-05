"""Onglet Risques et interdépendances : score de risque expliqué, relations entre pièces et origine des achats."""
from html import escape
from collections import Counter

import plotly.graph_objects as go
import streamlit as st

from plm import scenarios
from plm.fmt import number
from ui import theme
from ui.state import open_from_table, open_part

TOP_PARTS = 12
CLASS_RULES = "Classe A : pièce vitale pour la fonction. Classe B : pièce importante. Classe C : pièce standard, facile à requalifier ailleurs."
CRITERION_COLORS = [*theme.PALETTE, theme.NEUTRAL_BAR]


def part_node_ids(model, part_ids):
    return [model.nodes_by_part[part_id][0].id for part_id in part_ids]


# ------------------------------------------------------------------ Score de risque


def score_chart(rows):
    """Barres empilées : chaque segment montre les points d'un critère, le total est écrit au bout."""
    top = rows[:TOP_PARTS]
    names = [r["name"] for r in top]
    fig = go.Figure()
    for index, criterion in enumerate(scenarios.CRITERIA):
        cells = [next(b for b in r["breakdown"] if b["key"] == criterion["key"]) for r in top]
        fig.add_bar(
            y=names, x=[c["points"] for c in cells], name=criterion["label"], orientation="h", width=0.66,
            marker=dict(color=CRITERION_COLORS[index], line=dict(color=theme.SURFACE, width=2)),
            hovertext=[f"<b>{number(c['points'], 1)} points sur {number(c['max'], 2)}</b><br>{escape(criterion['label'])}<br>{escape(c['detail'])}" for c in cells], hoverinfo="text",
        )
    fig.add_scatter(y=names, x=[sum(b["points"] for b in r["breakdown"]) for r in top], text=[f"  {r['score']} · {r['level']}" for r in top], mode="text", textposition="middle right",
                    textfont=dict(color=theme.INK, size=12), showlegend=False, hoverinfo="skip", cliponaxis=False)
    fig.update_layout(barmode="stack")
    theme.style_figure(fig, height=112 + 27 * len(top), margin=dict(l=8, r=16, t=74, b=8))
    fig.update_layout(legend_traceorder="normal")
    fig.update_xaxes(range=[0, 100], showgrid=True, gridcolor=theme.GRID, title_text="Points, sur 100", dtick=20)
    fig.update_yaxes(showgrid=False, type="category", autorange="reversed", ticklabelstandoff=4)
    return fig


def render_part_detail(model, rows):
    by_id = {r["part_id"]: r for r in rows}
    part_id = st.selectbox("Pièce", list(by_id), key="risk_detail_part", format_func=lambda p: f"{by_id[p]['name']} ({by_id[p]['score']})")
    row = by_id[part_id]
    theme.badges([(f"Score {row['score']} sur 100", None), (row["level"], theme.LEVEL_COLORS[row["level"]]), (f"Classe {row['class']}", None), (f"{row['sources_qualified']} qualifié(s) sur {row['sources_referenced']}", None)])
    theme.table(["Critère", "Points", "Justification"], [(b["label"], number(b["points"], 1), b["detail"]) for b in row["breakdown"]], numeric=(1,))
    st.caption(f"Niveau retenu : {row['level']}. {row['level_reason']}.")
    st.button("Ouvrir la fiche", key="risk_open_part", on_click=open_part, args=(model.nodes_by_part[part_id][0].id,))


def render_method():
    st.markdown("##### Comment le score est calculé")
    st.caption("Choisissez la priorité de chaque critère : Élevé = 30, Normal = 20, Faible = 10. "
               "Ces poids sont ramenés à un total de 100 pour conserver un score sur 100. "
               "Les réglages s'appliquent à toutes les vues et aux outils de calcul.")
    for criterion in scenarios.CRITERIA:
        st.segmented_control(criterion['label'], list(scenarios.PRIORITY_WEIGHTS), default='Normal',
                             required=True, key=f"risk_priority_{criterion['key']}", width="stretch")


def render_criticality_info():
    st.markdown("##### Comprendre la criticité")
    st.caption("Selon le score : Faible < 25 · Modéré 25–44 · Élevé 45–69 · Critique ≥ 70.")
    st.markdown(
        "**Règles automatiques, indépendamment des pondérations :**\n\n"
        "- Une pièce de **classe A ou B (rôle vital/important dans l’assemblage)** avec **un seul fournisseur** est automatiquement classée **Critique**, même si son score est inférieur à 70.\n"
        "- Une pièce de **classe C (rôle standard dans l’assemblage)** avec **un seul fournisseur** est automatiquement classée **Élevé au minimum**. Elle reste **Critique** si son score atteint 70.\n\n"
        "Ces règles s’appliquent également lorsqu’aucun fournisseur n’est disponible."
    )
    with st.expander("Voir les barèmes"):
        theme.table(["Critère", "Définition"], [(c["label"], scenarios.CRITERION_DEFINITIONS[c['key']]) for c in scenarios.CRITERIA])
        st.caption(CLASS_RULES + " La complexité combine procédé (40 %), précision (30 %) et opérations (30 %). "
                   "Dans un scénario, le changement technique augmente le critère Importance fonctionnelle, dans la limite de sa pondération.")


def render_risk_table(model, rows):
    st.markdown("##### Tableau des risques par pièce")
    table = [{
        "Pièce": r["name"], "Criticité": r["level"], "Score": r["score"], "Raisons": " ; ".join(r["reasons"]), "Qualifiés / référencés": f"{r['sources_qualified']} / {r['sources_referenced']}",
        "Origine": r["origin"], "Complexité": r["complexity"], "Interdépendances": r["interfaces"], "Qté": r["quantity"], "Masse (kg)": round(r["mass_kg"], 3),
        "Coût (€)": round(r["line_cost"], 2), "Part du coût": r["cost_share"], "Classe": r["class"],
    } for r in rows]
    ids = part_node_ids(model, [r["part_id"] for r in rows])
    st.dataframe(table, hide_index=True, width="stretch", height=420, key="ov_table", on_select=open_from_table("ov_table", ids), selection_mode="single-row",
                 column_config={
                     "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "Complexité": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "Raisons": st.column_config.TextColumn(width="large"),
                     "Part du coût": st.column_config.NumberColumn(format="percent"), "Masse (kg)": st.column_config.NumberColumn(format="localized"),
                     "Coût (€)": st.column_config.NumberColumn(format="localized"),
                 })
    st.caption("Cochez une ligne pour ouvrir la fiche de la pièce.")


# ------------------------------------------------------------------ Interdépendances


def complexity_chart(rows):
    """Une colonne par pièce, de la plus complexe à la plus simple."""
    ranked = sorted(rows, key=lambda r: -r["complexity"])
    names = [r["name"] for r in ranked]
    fig = go.Figure(go.Bar(
        x=names, y=[r["complexity"] for r in ranked], width=0.66,
        marker=dict(color=[theme.COMPLEXITY_COLORS[r["complexity_level"]] for r in ranked], line=dict(width=0)),
        hovertext=[f"<b>{r['complexity']} sur 100, {r['complexity_level'].lower()}</b><br>{escape(r['name'])}<br>{escape(r['process'])}<br>Procédé {r['process_rating']}/5, précision {r['precision_rating']}/5, {r['operations']} opérations" for r in ranked],
        hoverinfo="text",
    ))
    theme.style_figure(fig, height=430, legend_visible=False, title="Complexité des pièces (score sur 100)")
    fig.update_xaxes(type="category", tickmode="array", tickvals=names, ticktext=names, tickangle=-55, tickfont=dict(size=10))
    fig.update_yaxes(range=[0, 100], dtick=25)
    return fig


def render_interdependencies(model, rows):
    st.markdown("##### Interdépendances et complexité des pièces")
    st.caption("Une interface relie deux pièces : si l'une change, l'autre doit être revérifiée. La complexité mesure la difficulté de fabrication de la pièce. Les deux entrent dans le score de risque.")
    ranked = sorted(rows, key=lambda r: -r["interfaces"])[:TOP_PARTS]
    left, right = st.columns([4, 7], gap="medium")
    with left:
        fig = theme.hbar([r["name"] for r in ranked], [r["interfaces"] for r in ranked], texts=[str(r["interfaces"]) for r in ranked], title="Pièces les plus liées (nombre d'interfaces)",
                         hover=[f"<b>{r['interfaces']} interfaces</b><br>{r['name']}" for r in ranked], height=430)
        theme.show(fig, key="ov_links")
    with right:
        theme.show(complexity_chart(rows), key="ov_complexity")
        theme.legend(theme.COMPLEXITY_COLORS)
    interfaces = [i for i in model.enrichment["interfaces"] if i["type"] != "study"]
    with st.expander(f"Liste des {len(interfaces)} interfaces"):
        st.dataframe([{
            "Pièce A": model.node_label(i["first"]), "Pièce B": model.node_label(i["second"]), "Type": model.interface_types[i["type"]]["label"], "Description": i["note"],
            "Essai à refaire": model.interface_types[i["type"]]["test"],
        } for i in interfaces], hide_index=True, width="stretch")


# ------------------------------------------------------------------ Origine des achats


def supplier_map(model):
    table = scenarios.supplier_table(model)
    active = [r for r in table if r["active_parts"]]
    candidates = [r for r in table if not r["active_parts"]]
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=[r["lat"] for r in active], lon=[r["lon"] for r in active], name="Fournisseur actif", mode="markers",
        marker=dict(size=12, color=[theme.LEVEL_COLORS["Critique"] if r["rating"] == "C" else theme.SERIES[0] for r in active], line=dict(color=theme.SURFACE, width=2), opacity=0.9),
        hovertext=[f"<b>{r['supplier']}</b><br>{r['city']}, {r['country']}<br>{r['active_parts']} pièce(s), notation {r['rating']}" for r in active], hoverinfo="text",
    ))
    fig.add_trace(go.Scattergeo(
        lat=[r["lat"] for r in candidates], lon=[r["lon"] for r in candidates], name="Candidat non actif", mode="markers",
        marker=dict(size=9, color="#c3c2b7", line=dict(color=theme.SURFACE, width=2)),
        hovertext=[f"<b>Candidat</b><br>{r['supplier']}<br>{r['city']}, {r['country']}" for r in candidates], hoverinfo="text",
    ))
    theme.style_figure(fig, height=380, margin=dict(l=0, r=0, t=26, b=0))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#293548", showocean=False, showcountries=True, countrycolor="#64748b", showframe=False, coastlinecolor="#64748b", lataxis_range=[12, 66], lonaxis_range=[-14, 142], bgcolor="rgba(0,0,0,0)")
    return fig


def render_origin(model):
    countries = Counter(r["country"] for r in scenarios.supplier_table(model) if r["active_parts"])
    st.markdown("##### Origine des fournisseurs")
    st.caption("Fournisseurs actifs en couleur ; rouge pour une notation financière C. Candidats en gris.")
    theme.show(supplier_map(model), key="ov_map")
    st.caption(" · ".join(f"{name} : {count} fournisseur(s) actif(s)" for name, count in countries.most_common()))


def render(model):
    rows = scenarios.criticality(model)
    kpis = scenarios.product_kpis(model)
    columns = st.columns(3)
    columns[0].metric("Composants critiques", kpis["critical_parts"], help="Score d'au moins 70, ou classe A ou B avec au plus un fournisseur qualifié.")
    columns[1].metric("Pièces mono-source", kpis["single_source_parts"], help="Pièces avec un seul fournisseur qualifié, ou aucun.")
    columns[2].metric("Interdépendances", kpis["interfaces"], help="Interfaces fonctionnelles entre pièces.")

    left, right = st.columns([7, 5], gap="medium")
    with left:
        st.markdown(f"##### Les {TOP_PARTS} composants les plus critiques, détail du score")
        theme.show(score_chart(rows), key="ov_crit")
        render_criticality_info()
    with right:
        render_method()

    detail, origin = st.columns(2, gap="medium")
    with detail:
        st.markdown("##### Détail du score d'une pièce")
        render_part_detail(model, rows)
    with origin:
        render_origin(model)
    render_risk_table(model, rows)
    render_interdependencies(model, rows)
