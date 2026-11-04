"""Onglet Risques et impacts : vue d'ensemble et 5 scénarios."""
from datetime import date
from html import escape

import plotly.graph_objects as go
import streamlit as st

from plm import scenarios
from plm.fmt import compact_eur, eur, kg, number, pct, signed_compact_eur, signed_eur, signed_kg
from plm.model import FAMILIES, FEASIBILITY_LABELS, FEASIBILITY_RANK
from ui import theme
from ui.state import open_from_table

TABS = ["Vue d'ensemble", "1. Rupture d'approvisionnement", "2. Prix des matières", "3. Fournisseurs", "4. Release", "5. Masse"]
CUSTOM = "Paramètres libres"


def scenarios_of(model, kind):
    return [s for s in model.scenarios.values() if s["kind"] == kind]


def part_node_ids(model, part_ids):
    return [model.nodes_by_part[part_id][0].id for part_id in part_ids]


def fictional_note(scenario):
    theme.note(f"<b>Scénario fictif.</b> {escape(scenario['narrative']).replace('$', '&#36;')}")


def recommendations(lines, title="Recommandations"):
    if lines:
        st.markdown(f"**{title}**")
        st.markdown("\n".join(f"- {escape(line)}" for line in lines))


# ------------------------------------------------------------------ Vue d'ensemble


def supplier_map(model):
    table = [r for r in scenarios.supplier_table(model)]
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
    theme.style_figure(fig, height=340, margin=dict(l=0, r=0, t=26, b=0))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#f0efec", showocean=False, showcountries=True, countrycolor="#ffffff", showframe=False, coastlinecolor="#c3c2b7", lataxis_range=[12, 66], lonaxis_range=[-14, 142], bgcolor="rgba(0,0,0,0)")
    return fig


def render_overview(model):
    kpis = scenarios.product_kpis(model)
    conc = scenarios.concentration(model)
    crit = scenarios.criticality(model)
    columns = st.columns(6)
    columns[0].metric("Composants critiques", kpis["critical_parts"], help="Score d'au moins 70, ou classe A ou B avec un seul fournisseur qualifié.")
    columns[1].metric("Pièces mono-source", conc["single_source_parts"], help=f"{compact_eur(conc['single_source_spend'])} d'achats annuels.")
    columns[2].metric("Achats annuels", compact_eur(kpis["annual_spend"]), help="À 48 000 e-drives par an.")
    columns[3].metric("3 premiers fournisseurs", pct(conc["top3_share"]))
    columns[4].metric("Achats hors UE", pct(conc["non_eu_share"]))
    columns[5].metric("Interdépendances", kpis["interfaces"], help="Interfaces fonctionnelles entre pièces, déduites des positions du XML ou supposées.")

    left, right = st.columns([6, 5], gap="medium")
    with left:
        top = crit[:12]
        fig = theme.hbar([r["name"] for r in top], [r["score"] for r in top], colors=[theme.LEVEL_COLORS[r["level"]] for r in top], texts=[str(r["score"]) for r in top],
                         hover=[f"<b>Score {r['score']}, {r['level']}</b><br>{r['name']}<br>{'<br>'.join(r['reasons'][:4])}" for r in top], title="Composants les plus critiques (score sur 100)", height=390)
        fig.update_xaxes(range=[0, 100])
        theme.show(fig, key="ov_crit")
        theme.legend({level: theme.LEVEL_COLORS[level] for level, _ in scenarios.LEVELS})
    with right:
        st.markdown("**Origine des achats** (taille selon les achats annuels, rouge pour une notation C)")
        theme.show(supplier_map(model), key="ov_map")
        countries = conc["by_country"]
        total = conc["total_spend"]
        st.caption(" · ".join(f"{name} {pct(value / total)}" for name, value in countries[:7]))

    st.markdown("**Tableau des risques par pièce** : cochez une ligne pour ouvrir sa fiche")
    rows = [{
        "Pièce": r["name"], "Criticité": r["level"], "Score": r["score"], "Raisons": " ; ".join(r["reasons"]), "Qualifiés / référencés": f"{r['sources_qualified']} / {r['sources_referenced']}",
        "Origine": r["origin"], "Interdépendances": r["interfaces"], "Qté": r["quantity"], "Masse (kg)": round(r["mass_kg"], 3), "Volume (L)": round(r["volume_l"], 3), "Encombrement (mm)": r["envelope_mm"].replace("x", " × "),
        "Coût (€)": round(r["line_cost"], 2), "Part du coût": r["cost_share"], "Classe": r["class"],
    } for r in crit]
    ids = part_node_ids(model, [r["part_id"] for r in crit])
    st.dataframe(rows, hide_index=True, width="stretch", height=420, key="ov_table", on_select=open_from_table("ov_table", ids), selection_mode="single-row",
                 column_config={
                     "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"), "Raisons": st.column_config.TextColumn(width="large"),
                     "Part du coût": st.column_config.NumberColumn(format="percent"), "Masse (kg)": st.column_config.NumberColumn(format="localized"),
                     "Volume (L)": st.column_config.NumberColumn(format="localized"), "Coût (€)": st.column_config.NumberColumn(format="localized"),
                 })
    st.caption("Le score cumule les sources qualifiées, le délai de remplacement, le délai de livraison, l'origine, la santé financière, la classe fonctionnelle, les interdépendances et le poids dans le coût. Une pièce de classe A ou B avec un seul fournisseur qualifié est toujours critique.")


# ------------------------------------------------------------------ Scénario 1


def apply_s1_preset(model):
    preset = st.session_state.s1_preset
    if preset != CUSTOM:
        scenario = model.scenarios[preset]
        st.session_state.s1_part = scenario["part"]
        st.session_state.s1_supplier = scenario["supplier"]
        st.session_state.s1_weeks = scenario["duration_weeks"]


def reset_s1_supplier(model):
    st.session_state.s1_preset = CUSTOM
    primary = model.primary_link(model.products[st.session_state.s1_part])
    st.session_state.s1_supplier = primary["supplier"]


def mark_custom(key):
    st.session_state[key] = CUSTOM


def render_disruption(model):
    presets = scenarios_of(model, "SUPPLY_DISRUPTION")
    if "s1_preset" not in st.session_state:
        st.session_state.s1_preset = presets[0]["id"]
        apply_s1_preset(model)
    titles = {s["id"]: s["title"] for s in presets}
    st.selectbox("Scénario", [s["id"] for s in presets] + [CUSTOM], key="s1_preset", format_func=lambda v: titles.get(v, CUSTOM), on_change=apply_s1_preset, args=(model,))

    parts = [p for p in model.physical_parts if model.active_links(p)]
    columns = st.columns([4, 4, 3])
    part_id = columns[0].selectbox("Pièce touchée", [p["xml_id"] for p in parts], key="s1_part", format_func=model.node_label, on_change=reset_s1_supplier, args=(model,))
    part = model.products[part_id]
    links = model.active_links(part)
    if st.session_state.get("s1_supplier") not in [l["supplier"] for l in links]:
        st.session_state.s1_supplier = model.primary_link(part)["supplier"]
    supplier_id = columns[1].selectbox("Fournisseur à l'arrêt", [l["supplier"] for l in links], key="s1_supplier", format_func=lambda s: f"{model.suppliers[s]['name']} ({next(l['share_pct'] for l in links if l['supplier'] == s)} %)", on_change=mark_custom, args=("s1_preset",))
    weeks = columns[2].slider("Durée de l'arrêt (semaines)", 1, 30, key="s1_weeks", on_change=mark_custom, args=("s1_preset",))

    if st.session_state.s1_preset != CUSTOM:
        fictional_note(model.scenarios[st.session_state.s1_preset])

    result = scenarios.simulate_disruption(model, part_id, supplier_id, weeks)
    strategies = result["strategies"]
    wait, best = strategies["wait"], strategies[result["best"]]
    columns = st.columns(5)
    columns[0].metric("Couverture avant arrêt", f"{number(result['cover_days'])} jours ouvrés" if result["cover_days"] is not None else "Sans arrêt", help=f"Stock usine {result['plant_stock_days']} jours, transit {result['transit_days']} jours, stock de produits finis {model.program['finished_goods_days']} jours.")
    columns[1].metric("E-drives perdus sans action", number(wait["lost_units"]))
    columns[2].metric("Coût sans action", compact_eur(wait["total_cost"]))
    columns[3].metric("Meilleure stratégie", best["label"])
    columns[4].metric("Coût de cette stratégie", compact_eur(best["total_cost"]), delta=f"{compact_eur(best['total_cost'] - wait['total_cost'])} vs attente" if best["total_cost"] != wait["total_cost"] else None, delta_color="inverse")

    left, right = st.columns([7, 5], gap="medium")
    with left:
        fig = go.Figure()
        for index, name in enumerate(("wait", "reallocate", "emergency")):
            strategy = strategies[name]
            fig.add_scatter(x=[r["week"] for r in strategy["series"]], y=[r["delivered"] for r in strategy["series"]], name=strategy["label"], mode="lines", line=dict(color=theme.SERIES[index], width=2, dash="solid"), hovertemplate="%{y:,.0f}<extra>" + strategy["label"] + "</extra>")
        fig.add_vrect(x0=0.5, x1=weeks + 0.5, fillcolor="#d03b3b", opacity=0.07, line_width=0, annotation_text="Fournisseur à l'arrêt", annotation_position="top left", annotation_font_size=11)
        theme.style_figure(fig, height=330, title="E-drives livrés par semaine (cadence série : 1 000)")
        last_stop = max(s["last_stop_week"] or 0 for s in strategies.values())
        fig.update_xaxes(title_text="Semaine après le début de l'arrêt", dtick=2, range=[1, max(last_stop, weeks) + 5])
        fig.update_yaxes(range=[0, 1120])
        fig.update_layout(hovermode="x unified", legend=dict(y=-0.28, yanchor="top"))
        theme.show(fig, key="s1_chart")
    with right:
        recommendations(result["recommendations"])
        st.caption(" ".join(f"{s['label']} : {s['description']}" for s in strategies.values()))

    st.markdown("**Comparaison des stratégies**")
    st.dataframe([{
        "Stratégie": s["label"], "E-drives perdus": number(s["lost_units"]), "Jours d'arrêt": number(s["stop_days"]), "Marge perdue": compact_eur(s["margin_lost"]), "Pénalités OEM": compact_eur(s["penalty"]),
        "Surcoûts achats": compact_eur(s["extra_purchase"]), "Fret aérien": compact_eur(s["air_freight"]), "Outillage et PPAP": compact_eur(s["one_off"]), "Total": compact_eur(s["total_cost"]),
    } for s in strategies.values()], hide_index=True, width="stretch")

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("**Ce qui se bloque**")
        st.markdown("\n".join(f"- {escape(chain)}" for chain in result["blocked_chains"]))
        st.caption(f"{result['interfaces']} interface(s) fonctionnelle(s) sur cette pièce. Toute la ligne d'assemblage s'arrête quand une pièce manque.")
        if result["exposed_parts"]:
            st.markdown("**Autres pièces chez ce fournisseur** (si tout le site s'arrête)")
            st.dataframe([{"Pièce": e["part"], "Part du volume": e["share_pct"] / 100, "Couverture (j)": round(e["cover_days"], 1), "Mono-source": "Oui" if e["single_source"] else "Non"} for e in result["exposed_parts"]], hide_index=True, width="stretch", column_config={"Part du volume": st.column_config.NumberColumn(format="percent")})
    with right:
        st.markdown("**Alternatives référencées**")
        if result["alternatives"]:
            st.dataframe([{"Fournisseur": a["supplier"], "Pays": a["country"], "Statut": a["status"], "Capacité / besoin": a["coverage"], "Prix (€)": a["price"], "Délai normal (sem.)": a["delay_weeks"], "Délai d'urgence (sem.)": a["delay_emergency_weeks"], "Coût unique (€)": a["switching_cost"]} for a in result["alternatives"]], hide_index=True, width="stretch",
                         column_config={"Capacité / besoin": st.column_config.NumberColumn(format="percent"), "Prix (€)": st.column_config.NumberColumn(format="localized"), "Coût unique (€)": st.column_config.NumberColumn(format="localized")})
        else:
            st.warning("Aucune alternative référencée pour cette pièce.")
    theme.sources_expander(model, result["sources"])
    st.caption(f"Hypothèses : marge de {eur(result['margin_per_unit'])} par e-drive, pénalité OEM de {eur(model.program['line_stop_penalty_eur_day'])} par jour d'arrêt, fret aérien à {eur(model.program['air_freight_eur_kg'], 2)}/kg. Toutes simulées, à ajuster dans enrich_xml.py.")


# ------------------------------------------------------------------ Scénario 2


def apply_s2_preset(model):
    preset = st.session_state.s2_preset
    if preset != CUSTOM:
        scenario = model.scenarios[preset]
        st.session_state.s2_family = scenario["family"]
        st.session_state.s2_pct = scenario["pct"]


def render_price(model):
    presets = scenarios_of(model, "MATERIAL_PRICE")
    if "s2_preset" not in st.session_state:
        st.session_state.s2_preset = presets[0]["id"]
        apply_s2_preset(model)
    titles = {s["id"]: s["title"] for s in presets}
    columns = st.columns([5, 3, 3])
    columns[0].selectbox("Scénario", [s["id"] for s in presets] + [CUSTOM], key="s2_preset", format_func=lambda v: titles.get(v, CUSTOM), on_change=apply_s2_preset, args=(model,))
    family = columns[1].selectbox("Matière", FAMILIES, key="s2_family", on_change=mark_custom, args=("s2_preset",))
    variation = columns[2].slider("Variation de l'indice (%)", -40, 60, key="s2_pct", on_change=mark_custom, args=("s2_preset",))
    if st.session_state.s2_preset != CUSTOM:
        fictional_note(model.scenarios[st.session_state.s2_preset])

    result = scenarios.material_price_impact(model, family=family, pct=variation)
    columns = st.columns(5)
    columns[0].metric("Pièces touchées", result["parts"], help=f"{kg(round(result['mass_kg'], 2))} de cette matière dans l'e-drive.")
    columns[1].metric("Coût par e-drive", signed_eur(result["delta_unit"], 2), help=f"Nomenclature : {eur(result['bom_before'])} puis {eur(result['bom_after'])}.")
    columns[2].metric("Effet annuel", signed_compact_eur(result["delta_annual"]), help="À 48 000 e-drives par an, une fois toutes les clauses appliquées.")
    columns[3].metric("Sur les 12 premiers mois", signed_compact_eur(result["first_12_months"]), help="Tient compte de la date d'effet de chaque clause de prix.")
    columns[4].metric("Marge", pct(result["margin_pct_after"], 1), delta=f"{number((result['margin_pct_after'] - result['margin_pct_before']) * 100, 1)} pt", help=f"Avant : {pct(result['margin_pct_before'], 1)}.")

    left, right = st.columns(2, gap="medium")
    with left:
        rows = result["rows"]
        fig = theme.hbar([r["part"] for r in rows], [r["delta_unit"] for r in rows], colors=[theme.FAMILY_COLORS[family]] * len(rows), texts=[signed_eur(r["delta_unit"], 2) for r in rows],
                         hover=[f"<b>{signed_eur(r['delta_part'], 2)} par pièce</b><br>{r['part']}<br>{r['material']}<br>{r['clauses']}" for r in rows], title="Écart de coût par pièce (€ par e-drive)", height=max(150, 62 + 34 * len(rows)))
        theme.show(fig, key="s2_parts")
    with right:
        timeline = result["timeline"]
        fig = go.Figure(go.Bar(x=[f"M+{r['month']}" for r in timeline], y=[r["cost"] for r in timeline], marker=dict(color=theme.NEUTRAL_BAR), hovertemplate="%{y:,.0f} €<extra>%{x}</extra>", width=0.6))
        theme.style_figure(fig, height=250, legend_visible=False, title="Écart de coût mensuel, selon les clauses de prix (€)")
        fig.update_xaxes(type="category")
        theme.show(fig, key="s2_timeline")

    st.markdown("**Détail par pièce**")
    st.dataframe([{"Pièce": r["part"], "Matériau": r["material"], "Qté": r["quantity"], "Matière consommée (kg)": r["usage_kg"], "Prix avant (€/kg)": r["price_before"], "Prix après (€/kg)": round(r["price_after"], 2), "Écart par pièce (€)": round(r["delta_part"], 2), "En % du coût pièce": r["delta_pct_part"], "Par e-drive (€)": round(r["delta_unit"], 2), "Par an (€)": round(r["delta_annual"]), "Clause": r["clauses"], "Effet à partir de": f"M+{r['first_month']}"} for r in rows], hide_index=True, width="stretch",
                 column_config={"En % du coût pièce": st.column_config.NumberColumn(format="percent"), "Par an (€)": st.column_config.NumberColumn(format="localized"), "Écart par pièce (€)": st.column_config.NumberColumn(format="localized"), "Par e-drive (€)": st.column_config.NumberColumn(format="localized"), "Matière consommée (kg)": st.column_config.NumberColumn(format="localized")})

    left, right = st.columns(2, gap="medium")
    with left:
        sensitivity = scenarios.family_sensitivity(model)
        fig = theme.hbar([r["family"] for r in sensitivity], [r["delta_annual"] for r in sensitivity], colors=[theme.FAMILY_COLORS[r["family"]] for r in sensitivity], texts=[compact_eur(r["delta_annual"]) for r in sensitivity],
                         hover=[f"<b>{compact_eur(r['delta_annual'])} par an</b><br>{r['family']}<br>{kg(round(r['mass_kg'], 2))}, {r['parts']} pièce(s)" for r in sensitivity], title="Sensibilité : effet annuel d'une hausse de 10 % par matière", height=250)
        theme.show(fig, key="s2_sens")
    with right:
        lines = [f"{pct(result['share_within_3_months'])} de l'effet arrive sous 3 mois : le reste attend la fin des contrats à prix fixe."]
        if family == "Cuivre":
            lines.append("Le cuivre pèse 7 % de la masse mais autant que l'aluminium dans le coût matière : c'est la première exposition au kilo.")
            lines.append("Parade structurelle à long terme : épingles en aluminium (voir le scénario 5), mais faisabilité faible sur ce moteur.")
        elif family == "Aluminium":
            lines.append("Quatre des six pièces viennent surtout de Garda : y négocier une couverture matière commune aurait le plus d'effet.")
        elif family == "Acier électrique":
            lines.append("Une seule pièce concernée : la double source Slovlam (scénario 3) peut aussi servir de levier de négociation.")
        if variation > 0:
            lines.append(f"Pour garder la marge, il faudrait répercuter {eur(result['delta_unit'], 2)} sur le prix de vente, soit {pct(result['delta_unit'] / model.program['selling_price_eur'], 1)}.")
        recommendations(lines, "Lecture")
    theme.sources_expander(model, result["sources"])
    st.caption("Calcul à cadence série (48 000 e-drives par an). Seule la part indexée du prix matière varie : la conversion (usinage, fonderie, bobinage) ne bouge pas. Prix de référence : cuivre LME 14 415 \\$/t au 23/10/2026, aluminium LME environ 3 100 \\$/t début octobre 2026, 1 € = 1,14 \\$. Autres matières : hypothèses de travail.")


# ------------------------------------------------------------------ Scénario 3


def render_mapping(model):
    conc = scenarios.concentration(model)
    table = scenarios.supplier_table(model)
    columns = st.columns(5)
    columns[0].metric("Fournisseurs actifs", f"{conc['suppliers_active']} sur {conc['suppliers_referenced']}")
    columns[1].metric("Pays", conc["countries"])
    columns[2].metric("Pièces mono-source", conc["single_source_parts"], help=f"{pct(conc['single_source_spend'] / conc['total_spend'])} des achats.")
    columns[3].metric("3 premiers fournisseurs", pct(conc["top3_share"]))
    columns[4].metric("Concentration HHI", number(conc["hhi"]), help="Indice de Herfindahl sur les achats : au-dessus de 1 000, marché modérément concentré.")

    left, right = st.columns(2, gap="medium")
    with left:
        active = [r for r in table if r["active_parts"]][:12]
        fig = theme.hbar([r["supplier"] for r in active], [r["spend_annual"] for r in active], colors=[theme.LEVEL_COLORS["Critique"] if r["rating"] == "C" else theme.SERIES[0] for r in active], texts=[compact_eur(r["spend_annual"]) for r in active],
                         hover=[f"<b>{compact_eur(r['spend_annual'])} par an, {pct(r['spend_share'])}</b><br>{r['supplier']}, {r['country']}<br>{r['active_parts']} pièce(s), dont {r['sole_source_parts']} mono-source<br>Notation {r['rating']}, {r['ppm']} ppm" for r in active], title="Achats annuels par fournisseur (rouge pour une notation C)", height=390)
        theme.show(fig, key="s3_spend")
    with right:
        st.markdown("**Origine des fournisseurs**")
        theme.show(supplier_map(model), key="s3_map")
        total = conc["total_spend"]
        st.caption(" · ".join(f"{name} {pct(value / total)}" for name, value in conc["by_region"]))

    st.markdown("**Cartographie pièces et fournisseurs** : cochez une ligne pour ouvrir sa fiche")
    mapping = scenarios.part_supplier_mapping(model)
    ids = part_node_ids(model, [r["part_id"] for r in mapping])
    st.dataframe([{"Pièce": r["part"], "Sous-ensemble": r["subassembly"], "Qualifiés": r["qualified"], "Référencés": r["referenced"], "Mono-source": "⚠ Oui" if r["single_source"] else "Non", "Classe": r["class"], "Achats annuels (€)": round(r["annual_spend"]), "Fournisseurs": r["suppliers"]} for r in mapping], hide_index=True, width="stretch", height=430,
                 key="s3_mapping", on_select=open_from_table("s3_mapping", ids), selection_mode="single-row",
                 column_config={"Fournisseurs": st.column_config.TextColumn(width="large"), "Achats annuels (€)": st.column_config.NumberColumn(format="localized")})
    with st.expander("Tous les fournisseurs"):
        st.dataframe([{"Fournisseur": r["supplier"], "Pays": r["country"], "Ville": r["city"], "Région": r["region"], "Spécialité": r["speciality"], "Pièces actives": r["active_parts"], "Pièces candidates": r["candidate_parts"], "Achats annuels (€)": round(r["spend_annual"]), "Part": r["spend_share"], "Mono-source sur": r["sole_source_names"], "Notation": r["rating"], "PPM": r["ppm"], "Livraison à l'heure": r["otd"] / 100} for r in table], hide_index=True, width="stretch",
                     column_config={"Part": st.column_config.NumberColumn(format="percent"), "Livraison à l'heure": st.column_config.NumberColumn(format="percent"), "Achats annuels (€)": st.column_config.NumberColumn(format="localized")})


def render_exit(model):
    scenario = model.scenarios["S3-GARDA"]
    table = [r for r in scenarios.supplier_table(model) if r["active_parts"]]
    if "s3_exit_supplier" not in st.session_state:
        st.session_state.s3_exit_supplier = scenario["supplier"]
    supplier_id = st.selectbox("Fournisseur défaillant", [r["supplier_id"] for r in table], key="s3_exit_supplier", format_func=lambda s: f"{model.suppliers[s]['name']} (notation {model.suppliers[s]['financial_rating']})")
    if supplier_id == scenario["supplier"]:
        fictional_note(scenario)
    result = scenarios.supplier_exit(model, supplier_id)
    columns = st.columns(5)
    columns[0].metric("Pièces touchées", result["parts"], help=f"{compact_eur(result['spend_annual'])} d'achats annuels.")
    columns[1].metric("Sans alternative", result["no_alternative"])
    columns[2].metric("Coût unique", compact_eur(result["one_off"]), help="Outillages et qualification des fournisseurs de remplacement.")
    columns[3].metric("Effet annuel", signed_compact_eur(result["delta_annual"]))
    columns[4].metric("Délai max", f"{result['max_delay_weeks']} semaines", help=f"{number(result['weeks_to_sop'])} semaines restent avant le démarrage série.")

    rows = result["rows"]
    fig = theme.hbar([r["part"] for r in rows], [r["delay_weeks"] for r in rows], colors=[theme.LEVEL_COLORS["Critique"] if r["no_alternative"] or not r["before_sop"] else theme.SERIES[0] for r in rows], texts=[f"{r['delay_weeks']} sem." for r in rows],
                     hover=[f"<b>{r['delay_weeks']} semaines</b><br>{r['part']}<br>{r['alternative']}<br>{r['status']}" for r in rows], title="Délai pour retrouver une source (semaines)", height=max(170, 80 + 34 * len(rows)))
    fig.add_vline(x=result["weeks_to_sop"], line_color=theme.INK2, line_width=1, annotation_text=f"Démarrage série ({number(result['weeks_to_sop'])} sem.)", annotation_position="top", annotation_font_size=11)
    theme.show(fig, key="s3_exit_chart")
    st.dataframe([{"Pièce": r["part"], "Part perdue": r["share_lost_pct"] / 100, "Alternative": r["alternative"], "Statut": r["status"], "Capacité / besoin": r["capacity_coverage"], "Délai (sem.)": r["delay_weeks"], "Avant démarrage série": "Oui" if r["before_sop"] else "⚠ Non", "Effet annuel (€)": round(r["delta_annual"]), "Coût unique (€)": r["one_off"]} for r in rows], hide_index=True, width="stretch",
                 column_config={"Part perdue": st.column_config.NumberColumn(format="percent"), "Capacité / besoin": st.column_config.NumberColumn(format="percent"), "Effet annuel (€)": st.column_config.NumberColumn(format="localized"), "Coût unique (€)": st.column_config.NumberColumn(format="localized")})
    lines = []
    if result["no_alternative"]:
        lines.append(f"{result['no_alternative']} pièce(s) sans alternative : lancer un sourcing dès maintenant, sinon le démarrage série n'est pas tenu.")
    partial = [r["part"] for r in rows if not r["no_alternative"] and r["capacity_coverage"] < 1]
    if partial:
        lines.append(f"Capacité insuffisante pour couvrir tout le volume : {', '.join(partial)}.")
    if model.suppliers[supplier_id]["financial_rating"] == "C":
        lines.append("Notation C : demander un plan de continuité et sécuriser la propriété des outillages.")
    recommendations(lines)
    theme.sources_expander(model, result["sources"])


def apply_s3_preset(model):
    preset = st.session_state.s3_switch_preset
    if preset != CUSTOM:
        scenario = model.scenarios[preset]
        st.session_state.s3_switch_part = scenario["part"]
        st.session_state.s3_switch_to = scenario["to_supplier"]
        st.session_state.s3_switch_share = scenario["share_pct"]


def render_switch(model):
    presets = scenarios_of(model, "SUPPLIER_SWITCH")
    if "s3_switch_preset" not in st.session_state:
        st.session_state.s3_switch_preset = presets[0]["id"]
        apply_s3_preset(model)
    titles = {s["id"]: s["title"] for s in presets}
    st.selectbox("Scénario", [s["id"] for s in presets] + [CUSTOM], key="s3_switch_preset", format_func=lambda v: titles.get(v, CUSTOM), on_change=apply_s3_preset, args=(model,))

    parts = [p for p in model.physical_parts if len(p["sourcing"]) > 1]
    columns = st.columns([4, 4, 3])
    part_id = columns[0].selectbox("Pièce", [p["xml_id"] for p in parts], key="s3_switch_part", format_func=model.node_label, on_change=mark_custom, args=("s3_switch_preset",))
    part = model.products[part_id]
    primary = model.primary_link(part)
    options = [l["supplier"] for l in part["sourcing"] if l is not primary]
    if st.session_state.get("s3_switch_to") not in options:
        st.session_state.s3_switch_to = options[0]
    to_supplier = columns[1].selectbox(f"Nouveau fournisseur (actuel : {model.suppliers[primary['supplier']]['name']})", options, key="s3_switch_to", format_func=lambda s: model.suppliers[s]["name"], on_change=mark_custom, args=("s3_switch_preset",))
    share = columns[2].slider("Part de volume confiée (%)", 10, 100, step=10, key="s3_switch_share", on_change=mark_custom, args=("s3_switch_preset",))
    if st.session_state.s3_switch_preset != CUSTOM:
        fictional_note(model.scenarios[st.session_state.s3_switch_preset])

    result = scenarios.supplier_switch(model, part_id, to_supplier, share)
    columns = st.columns(5)
    columns[0].metric("Effet annuel", signed_compact_eur(result["annual_delta"]), help=f"Achats {signed_compact_eur(result['purchase_delta_annual'])}, stock supplémentaire {compact_eur(result['carrying_cost_annual'])} par an.")
    columns[1].metric("Coût unique", compact_eur(result["one_off"]), help=f"Outillage et qualification {compact_eur(result['switching_cost'])}, essais {compact_eur(result['tests_cost'])}.")
    columns[2].metric("Retour sur investissement", f"{number(result['payback_months'])} mois" if result["payback_months"] is not None else "Sans gain")
    columns[3].metric("Délai avant série", f"{result['delay_weeks']} semaines", help=f"{number(result['weeks_to_sop'])} semaines restent avant le démarrage série.")
    columns[4].metric("Sources qualifiées", f"{result['qualified_before']} puis {result['qualified_after']}")

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("**Comparaison**")
        before, after = result["from"], result["to"]
        rows = [
            ("Fournisseur", before["supplier"], after["supplier"]),
            ("Pays", before["country"], after["country"]),
            ("Prix par pièce", eur(before["price"], 2), eur(after["price"], 2)),
            ("Délai de livraison", f"{before['lead_time']} jours", f"{after['lead_time']} jours"),
            ("Transit", f"{before['transit']} jours", f"{after['transit']} jours"),
            ("Capacité par semaine", number(before["capacity"]), number(after["capacity"])),
            ("Qualité", f"{before['ppm']} ppm", f"{after['ppm']} ppm"),
            ("Livraison à l'heure", f"{number(before['otd'], 1)} %", f"{number(after['otd'], 1)} %"),
            ("Notation financière", before["rating"], after["rating"]),
            ("Statut", before["status"], after["status"]),
        ]
        st.dataframe([{"Critère": r[0], "Actuel": r[1], "Proposé": r[2]} for r in rows], hide_index=True, width="stretch")
        recommendations(result["remarks"], "Lecture")
    with right:
        st.markdown("**Interfaces à revalider**")
        if result["impacted_interfaces"]:
            st.dataframe([{"Avec": i["part"], "Type": i["type"], "Description": i["note"]} for i in result["impacted_interfaces"]], hide_index=True, width="stretch")
        st.markdown("**Assemblages à réviser**")
        st.markdown("\n".join(f"- {escape(chain)}" for chain in result["impacted_assemblies"]))
        if result["tests"]:
            st.caption("Essais concernés : " + " ; ".join(t["test"] for t in result["tests"]) + ".")
    theme.sources_expander(model, result["sources"])


def render_suppliers(model):
    tabs = st.tabs(["Cartographie", "Défaillance d'un fournisseur", "Changement de fournisseur"], key="s3_view", on_change="rerun")
    with tabs[0]:
        if tabs[0].open:
            render_mapping(model)
    with tabs[1]:
        if tabs[1].open:
            render_exit(model)
    with tabs[2]:
        if tabs[2].open:
            render_switch(model)


# ------------------------------------------------------------------ Scénario 4


def render_release(model):
    scenario = model.scenarios["S4-RELEASE"]
    columns = st.columns([3, 3, 6])
    target = columns[0].selectbox("Maturité visée", ["RELEASED", "FROZEN"], key="s4_target")
    if "s4_gate" not in st.session_state:
        st.session_state.s4_gate = date.fromisoformat(model.program["release_gate_date"])
    gate = columns[1].date_input("Jalon", key="s4_gate", format="DD/MM/YYYY")
    with columns[2]:
        fictional_note(scenario)
    result = scenarios.release_readiness(model, target, gate.isoformat())

    if result["go"]:
        theme.verdict(f"GO : toutes les pièces sont au niveau {target}.", True)
    else:
        late = f", {result['late_days']} jours après le jalon" if result["late_days"] > 0 else ""
        theme.verdict(f"NO-GO : {result['total'] - result['ready']} pièces sur {result['total']} ne sont pas prêtes. Date au plus tôt : {result['earliest_date']}{late}.", False)

    columns = st.columns(5)
    columns[0].metric("Pièces prêtes", f"{result['ready']} / {result['total']}", help="Hors géométries d'étude.")
    columns[1].metric("En part de masse", pct(result["ready_mass_pct"]))
    columns[2].metric("En part de coût", pct(result["ready_cost_pct"]))
    columns[3].metric("Bloquantes ou en retard", len(result["blockers"]))
    columns[4].metric("Maturités trop hautes", len(result["corrections"]), help="Assemblages plus avancés que leurs sous-composants.")

    left, right = st.columns([5, 7], gap="medium")
    statuses = ["Prêt", "À promouvoir", "En retard", "Bloquant", "À exclure"]
    with left:
        groups = {}
        for row in result["rows"]:
            groups.setdefault(row["subassembly"], {s: 0 for s in statuses})[row["status"]] += 1
        fig = go.Figure()
        for status in statuses:
            fig.add_bar(y=list(groups), x=[groups[g][status] for g in groups], name=status, orientation="h", marker=dict(color=theme.STATUS_COLORS[status], line=dict(color=theme.SURFACE, width=2)), hovertemplate="%{x} pièce(s)<extra>" + status + "</extra>", width=0.55)
        fig.update_layout(barmode="stack")
        theme.style_figure(fig, height=240, title="État des pièces par sous-ensemble")
        fig.update_layout(legend=dict(y=-0.2, yanchor="top"))
        fig.update_yaxes(showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor=theme.GRID, dtick=2)
        theme.show(fig, key="s4_groups")
    with right:
        pending = sorted([r for r in result["rows"] if r["date"] and not r["ready"]], key=lambda r: r["date"])
        fig = go.Figure()
        for status in ("À promouvoir", "En retard", "Bloquant"):
            items = [r for r in pending if r["status"] == status]
            if items:
                fig.add_scatter(x=[r["date"] for r in items], y=[r["part"] for r in items], mode="markers", name=status, marker=dict(size=11, color=theme.STATUS_COLORS[status], line=dict(color=theme.SURFACE, width=2)), hovertext=[f"<b>{r['date']}</b><br>{r['part']}<br>{r['issues'][0] if r['issues'] else ''}" for r in items], hoverinfo="text")
        theme.style_figure(fig, height=60 + 21 * max(len(pending), 8), title="Date de promotion prévue, face au jalon")
        fig.update_layout(legend=dict(y=-0.12, yanchor="top"))
        fig.update_yaxes(categoryorder="array", categoryarray=[r["part"] for r in pending][::-1], type="category")
        fig.update_xaxes(showgrid=True, gridcolor=theme.GRID, type="date", tickformat="%d/%m/%y")
        fig.add_shape(type="line", x0=gate.isoformat(), x1=gate.isoformat(), y0=0, y1=1, yref="paper", line=dict(color=theme.INK, width=1.5))
        fig.add_annotation(x=gate.isoformat(), y=1, yref="paper", text="Jalon", showarrow=False, yanchor="bottom", font=dict(size=11, color=theme.INK))
        theme.show(fig, key="s4_dates")

    st.markdown("**Pièce par pièce** : cochez une ligne pour ouvrir sa fiche")
    rows = result["rows"]
    ids = part_node_ids(model, [r["part_id"] for r in rows])
    icons = {"Prêt": "✅", "À promouvoir": "🟡", "En retard": "🟠", "Bloquant": "🔴", "À exclure": "⚪"}
    st.dataframe([{"État": f"{icons[r['status']]} {r['status']}", "Pièce": r["part"], "Sous-ensemble": r["subassembly"], "Maturité": r["maturity"], "Rév.": r["revision"], "Date prévue": r["date"] or "", "Maturité OK": "Oui" if r["maturity_ok"] else "Non", "PPAP OK": "Oui" if r["ppap_ok"] else "Non", "Données OK": "Oui" if r["data_ok"] else "Non", "Responsable": r["owner"], "Points à lever": " ; ".join(r["issues"])} for r in rows], hide_index=True, width="stretch", height=430,
                 key="s4_table", on_select=open_from_table("s4_table", ids), selection_mode="single-row", column_config={"Points à lever": st.column_config.TextColumn(width="large")})

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("**Ordre de promotion** (des pièces vers le produit)")
        for step in result["promotion_steps"]:
            st.markdown(f"- **{escape(step['step'])}** : {escape(', '.join(step['items']))}")
        if result["excluded"]:
            st.markdown(f"- **À retirer de la nomenclature** : {escape(', '.join(result['excluded']))}")
    with right:
        st.markdown("**Cohérence des assemblages**")
        st.dataframe([{"Assemblage": a["assembly"], "Maturité": a["maturity"], "Pièces prêtes": f"{a['ready']} / {a['total']}", "Sous-composant le moins mûr": a["lowest_child"], "Cohérence": "⚠ Trop haut" if a["ahead_of_children"] else "OK"} for a in result["assemblies"]], hide_index=True, width="stretch")
    theme.sources_expander(model, result["sources"])
    st.caption("Maturités, dates et PPAP simulés. L'export d'origine indique IN_WORK sur les 79 produits.")


# ------------------------------------------------------------------ Scénario 5


def render_mass(model):
    scenario = model.scenarios["S5-95KG"]
    perimeters = {"ID_0": "E-drive complet", "ID_1": "Moteur (EMOTOR FRONT)", "ID_17": "Réducteur", "ID_51": "Carters et visserie"}
    columns = st.columns([3, 3, 3, 3])
    perimeter = columns[0].selectbox("Périmètre", list(perimeters), key="s5_perimeter", format_func=perimeters.get)
    perimeter_mass = model.nodes[perimeter].total_mass
    default_target = max(0.0, perimeter_mass - model.program["mass_target_kg"]) if perimeter == "ID_0" else round(0.05 * perimeter_mass, 1)
    st.session_state.setdefault(f"s5_target_{perimeter}", round(default_target, 1))
    target = columns[1].number_input("Gain visé (kg)", 0.0, 20.0, step=0.1, key=f"s5_target_{perimeter}")
    feasibility_labels = {"HIGH": "Élevée seulement", "MEDIUM": "Moyenne ou élevée", "LOW": "Toutes"}
    feasibility = columns[2].selectbox("Faisabilité minimale", ["MEDIUM", "HIGH", "LOW"], key="s5_feasibility", format_func=feasibility_labels.get)
    st.session_state.setdefault("s5_weeks", int(model.weeks_to_sop))
    weeks = columns[3].slider("Délai maximal (semaines)", 0, 80, key="s5_weeks", help="Par défaut, le temps restant avant le démarrage série.")
    if perimeter == "ID_0":
        fictional_note(scenario)
    elif perimeter == "ID_1":
        theme.note("<b>Moteur seul.</b> Le carter moteur (« motor », 7 kg) est rangé dans les carters par l'export. Le rotor n'apparaît pas dans la nomenclature, sa masse n'est donc pas couverte.")

    plan = scenarios.mass_plan(model, perimeter, target, feasibility, weeks)
    options = plan["options"]
    default_ids = {o["option_id"] for o in plan["chosen"]}
    results_box = st.container()

    pareto = scenarios.mass_pareto(model, perimeter)
    left, right = st.columns([6, 7], gap="medium")
    with left:
        top = pareto["rows"][:12]
        fig = theme.hbar([r["part"] for r in top], [r["mass_kg"] for r in top], colors=[theme.FAMILY_COLORS.get(r["family"], theme.NEUTRAL_BAR) for r in top], texts=[f"{kg(round(r['mass_kg'], 2))} · {pct(r['share'])}" for r in top],
                         hover=[f"<b>{kg(round(r['mass_kg'], 3))}, {pct(r['share'], 1)}</b><br>{r['part']}<br>{r['material']}<br>Densité {number(r['density'], 2)} kg/dm³, volume {number(r['volume_l'], 2)} L<br>Cumul : {pct(r['cumulated_share'])}" for r in top], title=f"Pièces les plus lourdes ({kg(round(pareto['total_mass'], 2))} au total)", height=390)
        fig.update_xaxes(range=[0, top[0]["mass_kg"] * 1.3])
        theme.show(fig, key="s5_pareto")
        theme.legend({family: theme.FAMILY_COLORS[family] for family in FAMILIES if family in {r["family"] for r in top}})
    with right:
        kept = [o for o in options if o["kind"] != "DATA" and FEASIBILITY_RANK[o["feasibility"]] >= FEASIBILITY_RANK[feasibility] and o["weeks"] <= weeks][:14]
        fig = theme.hbar([f"{o['part']} : {o['label']}" for o in kept], [o["eur_per_kg"] for o in kept], colors=[theme.SERIES[0] if o["option_id"] in default_ids else "#c3c2b7" for o in kept], texts=[f"{number(o['eur_per_kg'], 1)} €/kg" for o in kept],
                         hover=[f"<b>{number(o['eur_per_kg'], 2)} € par kg gagné</b><br>{o['part']} : {o['label']}<br>{signed_kg(o['delta_mass'])}, {signed_eur(o['delta_cost'], 2)}<br>Faisabilité : {o['feasibility_label']}" for o in kept], title="Coût du kg gagné, par option (bleu : retenue dans le plan)", height=390)
        fig.add_vline(x=model.program["lightweight_value_eur_kg"], line_color=theme.INK2, line_width=1, annotation_text=f"Valeur OEM : {number(model.program['lightweight_value_eur_kg'])} €/kg", annotation_position="top", annotation_font_size=11)
        theme.show(fig, key="s5_merit")

    st.markdown("**Composez votre plan** : le plan proposé est coché, modifiez-le librement")
    frame_rows = [{
        "Retenir": o["option_id"] in default_ids, "Pièce": o["part"], "Option": o["label"], "Matériau après": o["material_after"] or "", "Masse (kg)": round(o["delta_mass"], 2), "Coût (€/e-drive)": round(o["delta_cost"], 2), "€ par kg gagné": round(o["eur_per_kg"], 2),
        "CO2 (kg)": round(o["delta_co2"], 1), "Coût unique (€)": o["one_off"], "Délai (sem.)": o["weeks"], "Faisabilité": FEASIBILITY_LABELS[o["feasibility"]], "Interfaces": o["interfaces"], "Encombrement": o["space"], "Risque": o["risk"],
    } for o in options]
    edited = st.data_editor(frame_rows, hide_index=True, width="stretch", height=430, key=f"s5_editor_{perimeter}_{target}_{feasibility}_{weeks}",
                            disabled=[k for k in frame_rows[0] if k != "Retenir"] if frame_rows else True,
                            column_config={"Retenir": st.column_config.CheckboxColumn(width="small"), "Coût unique (€)": st.column_config.NumberColumn(format="localized"), "Encombrement": st.column_config.TextColumn(width="medium"), "Risque": st.column_config.TextColumn(width="large")})
    chosen = [option for option, row in zip(options, edited) if row["Retenir"]]
    conflicts = {}
    for option in chosen:
        conflicts.setdefault(option["part"], []).append(option["label"])
    duplicates = [part for part, labels in conflicts.items() if len(labels) > 1]
    if duplicates:
        st.warning(f"Plusieurs options retenues sur la même pièce, gains non cumulables : {', '.join(duplicates)}.")

    summary = scenarios.summarize_plan(model, chosen, perimeter_mass)
    columns = results_box.columns(6)
    columns[0].metric("Masse après plan", kg(round(summary["mass_after"], 2)), delta=f"{signed_kg(-summary['saved_kg'])}", delta_color="inverse")
    columns[1].metric("Coût par e-drive", signed_eur(summary["delta_cost_unit"], 2), help=f"{signed_compact_eur(summary['delta_cost_annual'])} par an.")
    columns[2].metric("Coût du kg gagné", f"{number(summary['avg_eur_per_kg'], 2)} €", help=f"Valeur OEM supposée : {number(model.program['lightweight_value_eur_kg'])} €/kg.")
    columns[3].metric("Coût unique", compact_eur(summary["one_off"]))
    columns[4].metric("Délai max", f"{summary['max_weeks']} semaines", help=f"{number(model.weeks_to_sop)} semaines avant le démarrage série.")
    columns[5].metric("CO2 matière", f"{number(summary['delta_co2'], 1)} kg", help="Par e-drive, à consommation matière équivalente.")

    lines = []
    if perimeter == "ID_0":
        gap = summary["mass_after"] - model.program["mass_target_kg"]
        lines.append(f"Cible OEM de {kg(model.program['mass_target_kg'])} {'atteinte' if gap <= 0 else 'manquée de ' + kg(round(gap, 2))} avec ce plan.")
    if not plan["reached"]:
        lines.append("Avec ces contraintes, le plan proposé n'atteint pas le gain visé : élargir la faisabilité ou le délai.")
    lines.append("Le magnésium gagne beaucoup de masse, mais alourdit nettement le CO2 matière et son offre est très concentrée en Chine. Les optimisations de dessin sont d'abord moins risquées.")
    lines.append("Les géométries d'étude (dent et bobine seules) sont une correction de données : à faire confirmer par l'OEM avant de l'annoncer comme un gain.")
    recommendations(lines, "Lecture")
    theme.sources_expander(model, plan["sources"])
    st.caption("Options, gains et coûts simulés, à valider par le bureau d'études. Ordres de grandeur du magnésium issus de publications (gain de 25 à 36 % sur des carters d'e-drive). Le plan proposé est une heuristique : options triées par coût du kg gagné, une option par pièce.")


def render(model):
    tabs = st.tabs(TABS, key="risk_tab", on_change="rerun")
    renderers = (render_overview, render_disruption, render_price, render_suppliers, render_release, render_mass)
    for tab, renderer in zip(tabs, renderers):
        with tab:
            if tab.open:
                renderer(model)
