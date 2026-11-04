"""Onglet Risques et interdépendances : score de risque expliqué, relations entre pièces et origine des achats."""
from html import escape

import plotly.graph_objects as go
import streamlit as st

from plm import scenarios
from plm.fmt import compact_eur, number, pct
from ui import theme
from ui.state import open_from_table, open_part

TOP_PARTS = 12
CLASS_RULES = "Classe A : pièce vitale pour la fonction. Classe B : pièce importante. Classe C : pièce standard, facile à requalifier ailleurs. Ces classes sont une hypothèse du jeu de données simulé."


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
            marker=dict(color=theme.PALETTE[index], line=dict(color=theme.SURFACE, width=2)),
            hovertext=[f"<b>{number(c['points'], 1)} points sur {c['max']}</b><br>{escape(criterion['label'])}<br>{escape(c['detail'])}" for c in cells], hoverinfo="text",
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
    theme.table(["Critère", "Points", "Max", "Justification"], [(b["label"], number(b["points"], 1), b["max"], b["detail"]) for b in row["breakdown"]], numeric=(1, 2))
    st.caption(f"Niveau retenu : {row['level']}. {row['level_reason']}.")
    st.button("Ouvrir la fiche", key="risk_open_part", on_click=open_part, args=(model.nodes_by_part[part_id][0].id,))


def render_method():
    st.markdown("##### Comment le score est calculé")
    theme.note("<b>Score de risque = somme des points de 8 critères, de 0 à 100.</b> Plus il est élevé, plus la pièce peut arrêter la production. "
               "Le premier critère pèse le plus : une pièce sans source de secours part déjà de 25 à 35 points.")
    left, right = st.columns([7, 4], gap="medium")
    with left:
        theme.table(["Critère", "Max", "Barème"], [(c["label"], c["max"], c["scale"]) for c in scenarios.CRITERIA], numeric=(1,))
    with right:
        theme.table(["Niveau", "Score"], [(name, f"{threshold} ou plus" if threshold else "Moins de 25") for name, threshold in scenarios.LEVELS])
        st.markdown(
            "**Règles qui s'ajoutent au score**\n"
            "- Classe A ou B avec au plus un fournisseur qualifié : toujours **Critique**, quel que soit le score.\n"
            "- Classe C avec au plus un fournisseur qualifié : au moins **Élevé**.\n"
            "- Classe C : les points Sources et Remplacement sont divisés par 2 quand une seule source est qualifiée ou aucune alternative n'est en cours."
        )
        st.caption(CLASS_RULES)


def render_risk_table(model, rows):
    st.markdown("##### Tableau des risques par pièce")
    table = [{
        "Pièce": r["name"], "Criticité": r["level"], "Score": r["score"], "Raisons": " ; ".join(r["reasons"]), "Qualifiés / référencés": f"{r['sources_qualified']} / {r['sources_referenced']}",
        "Origine": r["origin"], "Interdépendances": r["interfaces"], "Qté": r["quantity"], "Masse (kg)": round(r["mass_kg"], 3), "Volume (L)": round(r["volume_l"], 3), "Encombrement (mm)": r["envelope_mm"].replace("x", " × "),
        "Coût (€)": round(r["line_cost"], 2), "Part du coût": r["cost_share"], "Classe": r["class"],
    } for r in rows]
    ids = part_node_ids(model, [r["part_id"] for r in rows])
    st.dataframe(table, hide_index=True, width="stretch", height=420, key="ov_table", on_select=open_from_table("ov_table", ids), selection_mode="single-row",
                 column_config={
                     "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "Raisons": st.column_config.TextColumn(width="large"),
                     "Part du coût": st.column_config.NumberColumn(format="percent"), "Masse (kg)": st.column_config.NumberColumn(format="localized"),
                     "Volume (L)": st.column_config.NumberColumn(format="localized"), "Coût (€)": st.column_config.NumberColumn(format="localized"),
                 })
    st.caption("Cochez une ligne pour ouvrir la fiche de la pièce.")


# ------------------------------------------------------------------ Interdépendances


def network_graph(model, rows):
    """Réseau des interfaces : un nœud par pièce, coloré selon sa criticité."""

    def quoted(value):
        return '"' + str(value).replace('"', "'") + '"'

    levels = {r["part_id"]: r["level"] for r in rows}
    ink = {"Critique": "#ffffff", "Élevé": "#0b0b0b", "Modéré": "#0b0b0b", "Faible": "#ffffff"}
    linked = {side for i in model.enrichment["interfaces"] if i["type"] != "study" for side in (i["first"], i["second"])}
    lines = [
        "graph {",
        'layout=neato; overlap=false; splines=true; sep="+10"; bgcolor="transparent"; size="9,6"; pad=0.2;',
        'node [shape=box, style="rounded,filled", fontname="Segoe UI", fontsize=10, color="#ffffff", margin="0.07,0.03", height=0.24];',
        'edge [color="#a9a89f", penwidth=1];',
    ]
    for part_id in sorted(linked):
        level = levels.get(part_id, "Faible")
        lines.append(f'{quoted(part_id)} [label={quoted(model.node_label(part_id))}, fillcolor="{theme.LEVEL_COLORS[level]}", fontcolor="{ink[level]}"];')
    for interface in model.enrichment["interfaces"]:
        if interface["type"] != "study":
            lines.append(f'{quoted(interface["first"])} -- {quoted(interface["second"])} [tooltip={quoted(model.interface_types[interface["type"]]["label"])}];')
    lines.append("}")
    return "\n".join(lines)


def render_interdependencies(model, rows):
    st.markdown("##### Interdépendances")
    st.caption("Une interface relie deux pièces : si l'une change, l'autre doit être revérifiée. Les interfaces sont déduites des positions du XML ou supposées, la colonne Justification le précise.")
    ranked = sorted(rows, key=lambda r: -r["interfaces"])[:TOP_PARTS]
    left, right = st.columns([4, 7], gap="medium")
    with left:
        fig = theme.hbar([r["name"] for r in ranked], [r["interfaces"] for r in ranked], texts=[str(r["interfaces"]) for r in ranked], title="Pièces les plus liées (nombre d'interfaces)",
                         hover=[f"<b>{r['interfaces']} interfaces</b><br>{r['name']}" for r in ranked], height=430)
        theme.show(fig, key="ov_links")
    with right:
        st.markdown("**Réseau des interfaces, coloré selon la criticité**")
        st.graphviz_chart(network_graph(model, rows), width="stretch")
        theme.legend({level: theme.LEVEL_COLORS[level] for level, _ in scenarios.LEVELS})
    interfaces = [i for i in model.enrichment["interfaces"] if i["type"] != "study"]
    with st.expander(f"Liste des {len(interfaces)} interfaces"):
        st.dataframe([{
            "Pièce A": model.node_label(i["first"]), "Pièce B": model.node_label(i["second"]), "Type": model.interface_types[i["type"]]["label"], "Description": i["note"], "Justification": i["evidence"],
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
        marker=dict(size=[max(8, (r["spend_annual"] / 1e6) ** 0.5 * 12) for r in active], color=[theme.LEVEL_COLORS["Critique"] if r["rating"] == "C" else theme.SERIES[0] for r in active], line=dict(color=theme.SURFACE, width=2), opacity=0.9),
        hovertext=[f"<b>{compact_eur(r['spend_annual'])} par an</b><br>{r['supplier']}<br>{r['city']}, {r['country']}<br>{r['active_parts']} pièce(s), notation {r['rating']}" for r in active], hoverinfo="text",
    ))
    fig.add_trace(go.Scattergeo(
        lat=[r["lat"] for r in candidates], lon=[r["lon"] for r in candidates], name="Candidat non actif", mode="markers",
        marker=dict(size=9, color="#c3c2b7", line=dict(color=theme.SURFACE, width=2)),
        hovertext=[f"<b>Candidat</b><br>{r['supplier']}<br>{r['city']}, {r['country']}" for r in candidates], hoverinfo="text",
    ))
    theme.style_figure(fig, height=380, margin=dict(l=0, r=0, t=26, b=0))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#f0efec", showocean=False, showcountries=True, countrycolor="#ffffff", showframe=False, coastlinecolor="#c3c2b7", lataxis_range=[12, 66], lonaxis_range=[-14, 142], bgcolor="rgba(0,0,0,0)")
    return fig


def render_origin(model):
    conc = scenarios.concentration(model)
    st.markdown("##### Origine des fournisseurs")
    st.caption("Taille selon les achats annuels, rouge pour une notation financière C. Fournisseurs fictifs.")
    theme.show(supplier_map(model), key="ov_map")
    st.caption(" · ".join(f"{name} {pct(value / conc['total_spend'])}" for name, value in conc["by_country"][:7]))


def render(model):
    rows = scenarios.criticality(model)
    kpis = scenarios.product_kpis(model)
    columns = st.columns(3)
    columns[0].metric("Composants critiques", kpis["critical_parts"], help="Score d'au moins 70, ou classe A ou B avec au plus un fournisseur qualifié.")
    columns[1].metric("Pièces mono-source", kpis["single_source_parts"], help="Pièces avec un seul fournisseur qualifié, ou aucun.")
    columns[2].metric("Interdépendances", kpis["interfaces"], help="Interfaces fonctionnelles entre pièces, déduites des positions du XML ou supposées.")

    left, right = st.columns([7, 5], gap="medium")
    with left:
        st.markdown(f"##### Les {TOP_PARTS} composants les plus critiques, détail du score")
        theme.show(score_chart(rows), key="ov_crit")
    with right:
        st.markdown("##### Détail du score d'une pièce")
        render_part_detail(model, rows)

    render_method()
    render_risk_table(model, rows)
    render_interdependencies(model, rows)
    render_origin(model)
