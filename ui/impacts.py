"""Onglet Analyse d'impacts : six facteurs combinables et comparaison à la référence."""
from datetime import date
from html import escape

import plotly.graph_objects as go
import streamlit as st

from plm import impact, scenarios
from plm.fmt import compact_eur, eur, kg, number, pct, signed_compact_eur, signed_eur, signed_kg
from plm.model import FAMILIES
from ui import theme
from ui.state import open_from_table

ELEMENTS_PRIMARY = "__elements__"
BEST_ALTERNATIVE = "__best__"
SCENARIO_COLOR = theme.SERIES[0]
REFERENCE_COLOR = theme.BASELINE
HIGHER_IS_BAD, HIGHER_IS_GOOD, NEUTRAL = -1, 1, 0
CHANGE_KINDS = {"geometry": "Géométrie / dimensions", "material": "Matériau", "process": "Procédé de fabrication"}


def reset_change_fields():
    for key in ('ia_s6_interfaces', 'ia_s6_material'):
        st.session_state.pop(key, None)


def node_id(model, part_id):
    return model.nodes_by_part[part_id][0].id


def element_options(model):
    """Assemblages et pièces, dans l'ordre de l'arborescence. Une pièce utilisée plusieurs fois n'apparaît qu'une fois."""
    options = {}
    seen = set()

    def visit(node, depth):
        if node.is_assembly:
            options[node.id] = f"{'· ' * (depth - 1)}{node.label} (assemblage)"
        elif node.part_id not in seen and node.product.get("physical", True):
            seen.add(node.part_id)
            options[node.id] = f"{'· ' * (depth - 1)}{model.node_label(node.part_id)}"
        for child in node.children:
            visit(child, depth + 1)

    for child in model.tree.children:
        visit(child, 1)
    return options


def material_options(model):
    used = [p for p in model.physical_parts if p.get("usage_kg") and p["material"]]
    families = {model.materials[p["material"]]["family"] for p in used}
    grades = sorted({p["material"] for p in used})
    return [family for family in FAMILIES if family in families] + grades


def defaults(model):
    return {
        "ia_elements": [],
        "ia_s1_on": False, "ia_s1_supplier": ELEMENTS_PRIMARY, "ia_s1_weeks": 12,
        "ia_s2_on": False, "ia_s2_material": "Cuivre", "ia_s2_pct": 15,
        "ia_s3_on": False, "ia_s3_from": ELEMENTS_PRIMARY, "ia_s3_to": BEST_ALTERNATIVE, "ia_s3_share": 100,
        "ia_s4_on": False, "ia_s4_target": "RELEASED", "ia_s4_gate": date.fromisoformat(model.program["release_gate_date"]),
        "ia_s5_on": False, "ia_s5_target": float(model.program["mass_target_kg"]), "ia_s5_options": [],
        "ia_s6_on": False, "ia_s6_part": model.physical_parts[0]["xml_id"], "ia_s6_mass_pct": 0, "ia_s6_weeks": 8,
        "ia_s6_kind": "geometry", "ia_s6_complexity_delta": 0,
    }


def reset_params(model):
    reset_change_fields()
    for key, value in defaults(model).items():
        st.session_state[key] = value


def read_params():
    state = st.session_state
    params = {"elements": state.ia_elements}
    if state.ia_s1_on:
        params["disruption"] = {"supplier": None if state.ia_s1_supplier == ELEMENTS_PRIMARY else state.ia_s1_supplier, "weeks": state.ia_s1_weeks}
    if state.ia_s2_on:
        params["price"] = {"material": state.ia_s2_material, "pct": state.ia_s2_pct}
    if state.ia_s3_on:
        params["change"] = {"from": None if state.ia_s3_from == ELEMENTS_PRIMARY else state.ia_s3_from, "to": None if state.ia_s3_to == BEST_ALTERNATIVE else state.ia_s3_to, "share": state.ia_s3_share}
    if state.ia_s4_on:
        params["release"] = {"target": state.ia_s4_target, "gate": state.ia_s4_gate.isoformat()}
    if state.ia_s5_on:
        params["mass"] = {"target_kg": state.ia_s5_target, "options": state.ia_s5_options}
    if state.ia_s6_on:
        params["versioning"] = {"part": state.ia_s6_part, "mass_pct": state.ia_s6_mass_pct, "weeks": state.ia_s6_weeks,
                               "kind": state.ia_s6_kind, "interfaces": state.ia_s6_interfaces,
                               "material": state.get('ia_s6_material'),
                               "complexity_delta": state.ia_s6_complexity_delta if state.ia_s6_kind == 'process' else 0}
    return params


# ------------------------------------------------------------------ Bloc du haut : paramètres


def render_settings(model):
    for key, value in defaults(model).items():
        st.session_state.setdefault(key, value)

    options = element_options(model)
    suppliers = {s: model.suppliers[s]["name"] for s in sorted(model.suppliers, key=lambda s: model.suppliers[s]["name"])}
    active = [s for s in suppliers if model.supplier_parts(s)]
    mass_options = {o["option_id"]: o for o in scenarios.mass_options(model, model.tree.id)}

    def supplier_label(value):
        return {ELEMENTS_PRIMARY: "Fournisseur principal des éléments", BEST_ALTERNATIVE: "Meilleure alternative"}.get(value) or suppliers[value]

    with st.container(border=True):
        st.markdown("##### Paramètres des facteurs d'impact")
        head = st.columns([10, 2], vertical_alignment="bottom")
        head[0].multiselect("Éléments à impacter", list(options), key="ia_elements", format_func=options.get, placeholder="Aucun élément : le facteur touche toutes les pièces concernées")
        head[1].button("Réinitialiser", key="reset_impacts", on_click=reset_params, args=(model,), width="stretch")

        state = st.session_state
        columns = [*st.columns(3, gap="small"), *st.columns(3, gap="small")]
        with columns[0], st.container(border=True, height="stretch"):
            st.toggle("Rupture fournisseur", key="ia_s1_on")
            off = not state.ia_s1_on
            st.selectbox("Fournisseur à l'arrêt", [ELEMENTS_PRIMARY, *active], key="ia_s1_supplier", format_func=supplier_label, disabled=off)
            st.slider("Durée (semaines)", 1, 30, key="ia_s1_weeks", disabled=off)
        with columns[1], st.container(border=True, height="stretch"):
            st.toggle("Prix d'un matériau", key="ia_s2_on")
            off = not state.ia_s2_on
            st.selectbox("Matériau", material_options(model), key="ia_s2_material", disabled=off, help="Une famille regroupe toutes ses nuances. Vous pouvez aussi choisir une seule nuance.")
            st.slider("Variation (%)", -40, 60, key="ia_s2_pct", disabled=off, help="Seule la part indexée du prix suit le marché.")
        with columns[2], st.container(border=True, height="stretch"):
            st.toggle("Changement de fournisseur", key="ia_s3_on")
            off = not state.ia_s3_on
            st.selectbox("Fournisseur remplacé", [ELEMENTS_PRIMARY, *active], key="ia_s3_from", format_func=supplier_label, disabled=off)
            st.selectbox("Nouveau fournisseur", [BEST_ALTERNATIVE, *suppliers], key="ia_s3_to", format_func=supplier_label, disabled=off, help="Il doit être référencé pour la pièce.")
            st.slider("Part de volume déplacée (%)", 10, 100, step=10, key="ia_s3_share", disabled=off)
        with columns[3], st.container(border=True, height="stretch"):
            st.toggle("Release", key="ia_s4_on")
            off = not state.ia_s4_on
            st.selectbox("Maturité visée", ["FROZEN", "RELEASED"], key="ia_s4_target", disabled=off)
            st.date_input("Jalon", key="ia_s4_gate", format="DD/MM/YYYY", disabled=off, help="Sans élément choisi : seules les pièces prévues à temps sont promues. Avec des éléments : ils sont promus quoi qu'il arrive.")
        with columns[4], st.container(border=True, height="stretch"):
            st.toggle("Allègement", key="ia_s5_on")
            off = not state.ia_s5_on
            st.slider("Masse cible (kg)", 85.0, 100.0, step=0.5, key="ia_s5_target", disabled=off)
            st.multiselect("Options imposées", list(mass_options), key="ia_s5_options", disabled=off, placeholder="Plan au meilleur coût",
                           format_func=lambda o: f"{mass_options[o]['part']} : {mass_options[o]['label']} ({signed_kg(mass_options[o]['delta_mass'])})")

        with columns[5], st.container(border=True, height="stretch"):
            st.toggle("Versioning · pièce modifiée", key="ia_s6_on")
            off = not state.ia_s6_on
            st.selectbox("Pièce modifiée", [p["xml_id"] for p in model.physical_parts], key="ia_s6_part", format_func=model.node_label, disabled=off, on_change=reset_change_fields)
            part = model.products[state.ia_s6_part]
            st.selectbox("Nature du changement", list(CHANGE_KINDS), key="ia_s6_kind", format_func=CHANGE_KINDS.get, disabled=off, on_change=reset_change_fields)
            if state.ia_s6_kind == 'material':
                materials = list(model.materials)
                st.selectbox("Nouveau matériau", materials, index=materials.index(part['material']) if part['material'] in materials else 0, key='ia_s6_material', disabled=off)
            if state.ia_s6_kind == 'process':
                st.slider("Variation de difficulté de fabrication", -2, 2, key='ia_s6_complexity_delta', disabled=off, help="Écart appliqué aux notes de procédé et de précision, chacune bornée de 1 à 5.")
            neighbors = list(dict.fromkeys(i['other'] for i in model.real_interfaces(part['xml_id'])))
            st.multiselect("Interfaces concernées", neighbors, default=[] if state.ia_s6_kind == 'process' else neighbors, key='ia_s6_interfaces', format_func=model.node_label, disabled=off)
            st.caption(f"Traçabilité : révision {part['revision']} → {impact.next_revision(part)}.")
            st.slider("Variation de masse (%)", -50, 50, key="ia_s6_mass_pct", disabled=off)
            st.slider("Revalidation (semaines)", 1, 52, key="ia_s6_weeks", disabled=off, help="Le délai effectif respecte aussi la durée de l’essai d’interface le plus long.")

        st.caption("Facteurs combinables. Si seul le fournisseur est choisi, toutes ses pièces sont concernées ; les éléments choisis limitent le périmètre.")


# ------------------------------------------------------------------ Bloc du bas : indicateurs en barres


def delta_badge(difference, text, direction, tolerance=0.005):
    if abs(difference) < tolerance:
        return '<span class="ia-delta same">= identique</span>'
    arrow = "▲" if difference > 0 else "▼"
    tone = "neutral" if direction == NEUTRAL else "good" if (difference > 0) == (direction > 0) else "bad"
    return f'<span class="ia-delta {tone}">{arrow} {escape(text)}</span>'


def bar_group(label, before, after, shown_before, shown_after, badge, scale):
    def row(name, value, shown, color):
        width = min(max(value, 0) / scale * 100, 100) if scale else 0
        return f'<div class="ia-row"><span>{name}</span><span class="ia-track"><i style="width:{width:.1f}%;background:{color}"></i></span><span class="ia-val">{escape(shown)}</span></div>'

    return f'<div class="ia-group"><div class="ia-head"><span>{escape(label)}</span>{badge}</div>{row("Référence", before, shown_before, REFERENCE_COLOR)}{row("Scénario", after, shown_after, SCENARIO_COLOR)}</div>'


def signed(value, digits=1):
    return ("+" if value > 0 else "") + number(value, digits)


def card(title, groups, foot=None):
    bottom = f'<div class="ia-foot">{escape(foot)}</div>' if foot else ""
    return f'<div class="ia-card"><h5>{escape(title)}</h5>{"".join(groups)}{bottom}</div>'


def scored_group(label, pair, direction):
    before, after = pair
    badge = delta_badge(after - before, f"{signed(after - before)} pts", direction, tolerance=0.05)
    return bar_group(label, before, after, f"{number(before, 1)} / 100", f"{number(after, 1)} / 100", badge, 100)


def share_groups(items):
    """Parts dans le coût : même échelle pour toute la carte, et un écart neutre car une part n'est ni bonne ni mauvaise."""
    scale = max((max(i["before"], i["after"]) for i in items), default=0) * 1.15 or 1
    groups = []
    for item in items:
        difference = (item["after"] - item["before"]) * 100
        badge = delta_badge(difference, f"{signed(difference)} pt", NEUTRAL, tolerance=0.05)
        groups.append(bar_group(item["label"], item["before"], item["after"], pct(item["before"], 1), pct(item["after"], 1), badge, scale))
    return groups


def render_cards(model, result):
    data = result["indicators"]
    mass_before, mass_after = data["mass"]
    cost_before, cost_after = data["cost"]
    margin_before, margin_after = data["margin_pct"]
    annual = data["annual_cost"][1] - data["annual_cost"][0]
    critical_before, critical_after = data["critical"]
    mono_before, mono_after = data["single_source"]
    count_scale = max(critical_before, critical_after, mono_before, mono_after, 1) * 1.2
    cost_scale = max(cost_before, cost_after) * 1.1
    mass_scale = max(mass_before, mass_after) * 1.1

    quality_groups = [scored_group("Score qualité du produit", data["quality"]["product"], HIGHER_IS_GOOD)]
    if data["quality"]["touched"]:
        quality_groups.append(scored_group("Score qualité des pièces touchées", data["quality"]["touched"], HIGHER_IS_GOOD))
    risk_groups = [scored_group("Score de risque du produit", data["risk"]["product"], HIGHER_IS_BAD)]
    if data["risk"]["touched"]:
        risk_groups.append(scored_group("Score de risque des pièces touchées", data["risk"]["touched"], HIGHER_IS_BAD))
    risk_groups.append(bar_group("Composants critiques", critical_before, critical_after, str(critical_before), str(critical_after),
                                 delta_badge(critical_after - critical_before, signed(critical_after - critical_before, 0), HIGHER_IS_BAD), count_scale))
    risk_groups.append(bar_group("Pièces mono-source", mono_before, mono_after, str(mono_before), str(mono_after),
                                 delta_badge(mono_after - mono_before, signed(mono_after - mono_before, 0), HIGHER_IS_BAD), count_scale))

    margin_points = (margin_after - margin_before) * 100
    cards = [
        card("Poids", [bar_group("Masse de l'e-drive", mass_before, mass_after, kg(round(mass_before, 2)), kg(round(mass_after, 2)),
                                 delta_badge(mass_after - mass_before, f"{signed_kg(round(mass_after - mass_before, 2))} ({signed((mass_after / mass_before - 1) * 100)} %)", HIGHER_IS_BAD), mass_scale)],
             foot=f"Cible OEM : {kg(model.program['mass_target_kg'])}."),
        card("Prix", [
            bar_group("Coût nomenclature par e-drive", cost_before, cost_after, eur(cost_before, 2), eur(cost_after, 2),
                      delta_badge(cost_after - cost_before, f"{signed_eur(cost_after - cost_before, 2)} ({signed((cost_after / cost_before - 1) * 100)} %)", HIGHER_IS_BAD), cost_scale),
            bar_group("Marge sur le prix de vente", margin_before, margin_after, pct(margin_before, 1), pct(margin_after, 1),
                      delta_badge(margin_points, f"{signed(margin_points)} pt", HIGHER_IS_GOOD, tolerance=0.05), max(margin_before, margin_after, 0.01) * 1.2),
        ], foot=f"Effet annuel à {number(model.program['annual_volume'])} e-drives : {signed_compact_eur(annual)}." if abs(cost_after - cost_before) >= 0.005 else None),
        card("Qualité", quality_groups),
        card("Risque", risk_groups),
        card("Poids du fournisseur dans le coût global", share_groups(data["suppliers"])),
        card("Poids du matériau dans le coût global", share_groups(data["materials"])),
    ]
    st.html(f'<div class="ia-grid">{"".join(cards)}</div>')


# ------------------------------------------------------------------ Résultats complémentaires par facteur


def render_disruption(model, detail):
    if not detail.get("parts"):
        return
    strategies = detail["strategies"]
    wait, best = strategies["wait"], strategies[detail["best"]]
    st.markdown(f"**Rupture de {detail['weeks']} semaines** : {detail['parts']} pièce(s) à l'arrêt, le fournisseur est retiré des indicateurs ci-dessus le temps de l'arrêt")
    columns = st.columns(5)
    columns[0].metric("E-drives perdus sans action", number(wait["lost_units"]))
    columns[1].metric("Arrêt de ligne sans action", f"{number(wait['stop_days'])} jours", help="Toute la ligne s'arrête dès qu'une pièce manque.")
    columns[2].metric("Coût sans action", compact_eur(wait["total_cost"]), help="Marge perdue, pénalité d'arrêt de ligne et surcoûts.")
    columns[3].metric("Meilleure stratégie", best["label"])
    columns[4].metric("Coût de cette stratégie", compact_eur(best["total_cost"]))
    with st.expander("Courbe de livraison par stratégie"):
        fig = go.Figure()
        weeks = list(range(1, len(wait["delivered"]) + 1))
        fig.add_scatter(x=weeks, y=[model.program["weekly_demand"]] * len(weeks), name="Demande", mode="lines", line=dict(color=theme.BASELINE, width=2, dash="dot"), hovertemplate="%{y:,.0f}<extra>Demande</extra>")
        for index, name in enumerate(("wait", "reallocate", "emergency")):
            strategy = strategies[name]
            fig.add_scatter(x=weeks, y=strategy["delivered"], name=strategy["label"], mode="lines", line=dict(color=theme.SERIES[index], width=2), hovertemplate="%{y:,.0f}<extra>" + strategy["label"] + "</extra>")
        theme.style_figure(fig, height=300, margin=dict(l=8, r=16, t=30, b=8))
        fig.update_xaxes(title_text="Semaine")
        fig.update_yaxes(title_text="E-drives livrés par semaine", rangemode="tozero")
        theme.show(fig, key="impact_delivery")


def render_price(model, detail, indicators):
    if not detail["parts"]:
        return
    delta = indicators["cost"][1] - indicators["cost"][0]
    st.markdown(f"**Prix de {detail['material']} : {signed(detail['pct'], 0)} %** sur {detail['parts']} pièce(s), soit {signed_eur(delta, 2)} par e-drive à plein régime. Seule la part indexée du prix suit le marché.")


def render_change(model, detail):
    if not detail["parts"]:
        return
    st.markdown("**Changement de fournisseur** : indicateurs calculés une fois le nouveau fournisseur qualifié")
    columns = st.columns(4)
    columns[0].metric("Pièces concernées", detail["parts"])
    columns[1].metric("Sans alternative", len(detail["no_alternative"]))
    columns[2].metric("Coût unique", compact_eur(detail["one_off"]), help="Coût de bascule et essais de revalidation si le fournisseur n'est pas encore en qualification.")
    columns[3].metric("Délai maximal", f"{detail['max_delay']} semaines", help=f"{number(model.weeks_to_sop)} semaines avant le démarrage série.")
    if detail["no_alternative"]:
        st.warning(f"Aucune solution de remplacement référencée pour : {', '.join(detail['no_alternative'])}. Ces pièces restent chez le fournisseur actuel dans les indicateurs.")
    if detail["max_delay"] > model.weeks_to_sop:
        st.warning(f"Le délai de {detail['max_delay']} semaines dépasse les {number(model.weeks_to_sop)} semaines restant avant le démarrage série.")


def render_release(detail):
    before, after = detail["before"], detail["after"]
    theme.verdict(f"{'GO' if after['go'] else 'NO-GO'} pour {detail['target']} au {date.fromisoformat(detail['gate']).strftime('%d/%m/%Y')} : {after['ready']} pièces prêtes sur {after['total']}", after["go"])
    columns = st.columns(4)
    columns[0].metric("Pièces prêtes, référence", f"{before['ready']} / {before['total']}")
    columns[1].metric("Pièces prêtes, scénario", f"{after['ready']} / {after['total']}", delta=after["ready"] - before["ready"] or None)
    columns[2].metric("Date au plus tôt", date.fromisoformat(after["earliest_date"]).strftime("%d/%m/%Y"), help="Date à laquelle toutes les pièces restantes peuvent être prêtes, selon les plans de release et de PPAP.")
    columns[3].metric("Assemblages à corriger", len(after["corrections"]), help="Assemblages plus avancés que leurs sous-composants.")
    remaining = [f"{r['part']} ({r['status'].lower()})" for r in after["rows"] if r["in_scope"] and not r["ready"]]
    if remaining:
        st.caption("Restent à traiter : " + ", ".join(remaining) + ".")
    if after["corrections"]:
        st.caption("Assemblages à corriger : " + ", ".join(after["corrections"]) + ".")
    if after["excluded"]:
        st.caption("Hors périmètre, géométries d'étude à retirer de la nomenclature : " + ", ".join(after["excluded"]) + ".")


def render_mass(model, detail):
    automatic = "plan au meilleur coût, options à faisabilité moyenne ou élevée" if detail["automatic"] else "options imposées"
    st.markdown(f"**Allègement** : {automatic}, masse cible {kg(detail['target_kg'])}")
    columns = st.columns(5)
    columns[0].metric("Masse gagnée", kg(round(detail["saved_kg"], 2)))
    columns[1].metric("Surcoût par e-drive", signed_eur(detail["delta_cost_unit"], 2))
    columns[2].metric("Coût unique", compact_eur(detail["one_off"]), help="Outillage et requalification.")
    columns[3].metric("Délai maximal", f"{detail['max_weeks']} semaines", help=f"{number(model.weeks_to_sop)} semaines avant le démarrage série.")
    columns[4].metric("CO2 matière", f"{signed(detail['delta_co2'])} kg CO2e", help="Écart par e-drive.")
    if detail["chosen"]:
        st.dataframe([{"Pièce": o["part"], "Option": o["label"], "Gain (kg)": round(-o["delta_mass"], 3), "Surcoût (€)": round(o["delta_cost"], 2), "Faisabilité": o["feasibility_label"], "Délai (semaines)": o["weeks"], "Risque": o["risk"]} for o in detail["chosen"]], hide_index=True, width="stretch",
                     column_config={"Gain (kg)": st.column_config.NumberColumn(format="localized"), "Surcoût (€)": st.column_config.NumberColumn(format="localized")})
    else:
        st.info("Aucune option d'allègement applicable avec ces paramètres.")


def render_touched(model, rows):
    st.markdown(f"**Pièces touchées ({len(rows)})** : cochez une ligne pour ouvrir la fiche")
    table = [{
        "Pièce": r["part"], "Facteurs": r["factors"],
        "Rév. réf.": r["revision_before"], "Rév. scén.": r["revision_after"],
        "Masse réf. (kg)": round(r["mass_before"], 3), "Masse scén. (kg)": round(r["mass_after"], 3),
        "Coût réf. (€)": round(r["cost_before"], 2), "Coût scén. (€)": round(r["cost_after"], 2),
        "Qualité réf.": round(r["quality_before"]), "Qualité scén.": round(r["quality_after"]),
        "Risque réf.": r["risk_before"], "Risque scén.": r["risk_after"],
        "Fournisseurs réf.": r["suppliers_before"], "Fournisseurs scén.": r["suppliers_after"],
        "Qualifiés réf.": r["qualified_before"], "Qualifiés scén.": r["qualified_after"],
        "Matériau scén.": r["material_after"], "Maturité réf.": r["maturity_before"], "Maturité scén.": r["maturity_after"], "ID PLM": r["plm_id"],
    } for r in rows]
    ids = [node_id(model, r["part_id"]) for r in rows]
    st.dataframe(table, hide_index=True, width="stretch", key="impact_table", on_select=open_from_table("impact_table", ids), selection_mode="single-row",
                 column_config={name: st.column_config.NumberColumn(format="localized") for name in ("Masse réf. (kg)", "Masse scén. (kg)", "Coût réf. (€)", "Coût scén. (€)")})


def render_versioning(detail):
    st.markdown(f"**Impact de la modification · {detail['part']} · {CHANGE_KINDS[detail['kind']]}**")
    columns = st.columns(4)
    columns[0].metric("Revalidation", f"{detail['weeks']} semaines")
    columns[1].metric("Fin de revalidation prévue", date.fromisoformat(detail['planned_release']).strftime('%d/%m/%Y'))
    columns[2].metric("Interfaces à revérifier", detail['interfaces'])
    columns[3].metric("Coût unique des essais", compact_eur(detail['one_off']))
    st.caption("État simulé après modification : pièce en IN_WORK, qualification des fournisseurs remise en cours. "
               "La variation de prix suit la matière consommée ; la conversion est conservée. "
               "Le délai couvre aussi l’essai le plus long. Le coût unique est présenté séparément du coût par e-drive.")
    st.markdown("**Impact sur les critères de risque de la pièce**")
    st.dataframe([{"Critère": r['criterion'], "Points avant": round(r['before'], 2), "Points après": round(r['after'], 2), "Écart": round(r['after'] - r['before'], 2), "Explication": r['detail']} for r in detail['criteria']], hide_index=True, width="stretch")
    with st.expander("Impact sur les critères de qualité"):
        st.dataframe([{"Critère": r['criterion'], "Points avant": round(r['before'], 2), "Points après": round(r['after'], 2), "Écart": round(r['after'] - r['before'], 2)} for r in detail['quality_criteria']], hide_index=True, width="stretch")
    if detail['neighbors']:
        st.markdown("**Pièces liées à revérifier**")
        st.dataframe([{"Pièce": r['part'], "Interface": r['type'], "Contrôle": r['test']} for r in detail['neighbors']], hide_index=True, width="stretch")
    if detail['tests']:
        st.dataframe([{"Essai": test['test'], "Coût (€)": test['cost_eur']} for test in detail['tests']], hide_index=True, width="stretch")
    st.caption("Chaînes d’assemblage concernées : " + " · ".join(detail['assemblies']))


def render_method():
    with st.expander("Comment les scores sont calculés"):
        st.markdown("**Score qualité d'une pièce, sur 100**")
        theme.table(["Critère", "Max", "Calcul"], [(c["label"], c["max"], c["rule"]) for c in impact.QUALITY_CRITERIA], numeric=(1,))
        st.markdown(
            "Une option d'allègement retire 5 points si sa faisabilité est moyenne, 15 si elle est faible.\n\n"
            "**Score de risque d'une pièce, sur 100** : barème détaillé dans l'onglet Risques et interdépendances. "
            "Une option d'allègement augmente le critère Criticité intrinsèque, dans sa limite de 16,67 points.\n\n"
            "**Score du produit** : moyenne pondérée par la classe de la pièce (A compte 3 fois, B 2 fois, C 1 fois). "
            "Le score des pièces touchées fait la même moyenne sur les seules pièces modifiées.\n\n"
            "**Hypothèses** : la rupture montre l'état pendant l'arrêt, le changement de fournisseur l'état une fois qualifié, "
            "le prix l'effet à plein régime sans délai contractuel."
        )


def render_results(model, result, active):
    st.markdown("##### Impact par rapport à la référence")
    if not active:
        theme.note("Activez au moins un facteur dans le bloc du dessus. Pour l'instant, le scénario est identique à la référence.")
    elif not result["touched"]:
        st.warning("Aucune pièce n'est concernée par ces paramètres : vérifiez que les éléments choisis utilisent ce fournisseur ou ce matériau.")
    else:
        st.caption(f"{len(result['touched'])} pièce(s) touchée(s). Barres à échelle réelle depuis zéro, écart affiché en face de chaque indicateur.")
    for message in result["notes"]:
        st.warning(message)
    render_cards(model, result)

    details = result["details"]
    if details.get("disruption"):
        render_disruption(model, details["disruption"])
    if details.get("price"):
        render_price(model, details["price"], result["indicators"])
    if details.get("change"):
        render_change(model, details["change"])
    if details.get("release"):
        render_release(details["release"])
    if details.get("mass"):
        render_mass(model, details["mass"])
    if details.get("versioning"):
        render_versioning(details["versioning"])
    if result["touched"]:
        render_touched(model, result["touched"])
    render_method()
    if result["sources"]:
        theme.sources_expander(model, result["sources"])


def render(model):
    render_settings(model)
    params = read_params()
    result = impact.analyze(model, params)
    with st.container(border=True):
        render_results(model, result, len(params) > 1)
