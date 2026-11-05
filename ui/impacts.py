"""Onglet Analyse d'impacts : cinq facteurs combinables et comparaison à la référence."""
from datetime import date
from html import escape

import streamlit as st

from plm import impact, scenarios
from plm.fmt import compact_eur, eur, kg, number, pct, signed_eur, signed_kg
from plm.model import FAMILIES, MATURITY_RANK
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

    def supplier_label(value):
        return {ELEMENTS_PRIMARY: "Fournisseur principal des éléments", BEST_ALTERNATIVE: "Meilleure alternative"}.get(value) or suppliers[value]

    with st.container(border=True):
        st.markdown("##### Paramètres des facteurs d'impact")
        head = st.columns([10, 2], vertical_alignment="bottom")
        head[0].multiselect("Éléments à impacter", list(options), key="ia_elements", format_func=options.get, placeholder="Aucun élément : le facteur touche toutes les pièces concernées")
        head[1].button("Réinitialiser", key="reset_impacts", on_click=reset_params, args=(model,), width="stretch")

        state = st.session_state
        columns = [*st.columns(3, gap="small"), *st.columns(2, gap="small")]
        with columns[0], st.container(border=True, height="stretch"):
            st.toggle("Rupture fournisseur", key="ia_s1_on")
            off = not state.ia_s1_on
            st.selectbox("Fournisseur à l'arrêt", [ELEMENTS_PRIMARY, *active], key="ia_s1_supplier", format_func=supplier_label, disabled=off)
            st.slider("Durée (semaines)", 1, 30, key="ia_s1_weeks", disabled=off)
        with columns[1], st.container(border=True, height="stretch"):
            st.toggle("Coût d'un matériau", key="ia_s2_on")
            off = not state.ia_s2_on
            st.selectbox("Matériau", material_options(model), key="ia_s2_material", disabled=off, help="Une famille regroupe toutes ses nuances. Vous pouvez aussi choisir une seule nuance.")
            st.slider("Variation (%)", -40, 60, key="ia_s2_pct", disabled=off, help="Variation du coût matière selon les conditions du matériau.")
        with columns[2], st.container(border=True, height="stretch"):
            st.toggle("Changement de fournisseur", key="ia_s3_on")
            off = not state.ia_s3_on
            st.selectbox("Fournisseur remplacé", [ELEMENTS_PRIMARY, *active], key="ia_s3_from", format_func=supplier_label, disabled=off)
            st.selectbox("Nouveau fournisseur", [BEST_ALTERNATIVE, *suppliers], key="ia_s3_to", format_func=supplier_label, disabled=off, help="Il doit être référencé pour la pièce.")
            st.slider("Part de volume déplacée (%)", 10, 100, step=10, key="ia_s3_share", disabled=off)
        with columns[3], st.container(border=True, height="stretch"):
            st.toggle("Maturité", key="ia_s4_on")
            off = not state.ia_s4_on
            st.selectbox("Maturité visée", ["FROZEN", "RELEASED"], key="ia_s4_target", disabled=off)
            with st.popover("Comprendre les statuts", icon=":material/info:"):
                st.markdown("**PRIVATE** : brouillon privé.\n\n**IN_WORK** : conception en cours.\n\n**FROZEN** : conception figée, en attente de validation finale.\n\n**RELEASED** : version validée et publiée pour utilisation.\n\n**OBSOLETE** : version retirée de l'utilisation.")
            st.caption("La maturité visée est appliquée aux éléments sélectionnés. Sans sélection, la projection suit le calendrier de validation du programme.")

        with columns[4], st.container(border=True, height="stretch"):
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


def render_cards(model, result, comparison_label="Scénario", show_shares=True):
    data = result["indicators"]
    mass_before, mass_after = data["mass"]
    cost_before, cost_after = data["cost"]
    margin_before, margin_after = data["margin_pct"]
    critical_before, critical_after = data["critical"]
    mono_before, mono_after = data["single_source"]
    count_scale = max(critical_before, critical_after, mono_before, mono_after, 1) * 1.2
    cost_scale = max(cost_before, cost_after) * 1.1
    mass_scale = max(mass_before, mass_after) * 1.1

    quality_groups = [scored_group("Qualité du produit", data["quality"]["product"], HIGHER_IS_GOOD)]
    if data["quality"]["touched"]:
        quality_groups.append(scored_group("Qualité des pièces touchées", data["quality"]["touched"], HIGHER_IS_GOOD))
    risk_groups = [scored_group("Score de risque du produit", data["risk"]["product"], HIGHER_IS_BAD)]
    if data["risk"]["touched"]:
        risk_groups.append(scored_group("Score de risque des pièces touchées", data["risk"]["touched"], HIGHER_IS_BAD))
    risk_groups.append(bar_group("Composants critiques", critical_before, critical_after, str(critical_before), str(critical_after),
                                 delta_badge(critical_after - critical_before, signed(critical_after - critical_before, 0), HIGHER_IS_BAD), count_scale))
    risk_groups.append(bar_group("Pièces mono-source", mono_before, mono_after, str(mono_before), str(mono_after),
                                 delta_badge(mono_after - mono_before, signed(mono_after - mono_before, 0), HIGHER_IS_BAD), count_scale))

    margin_points = (margin_after - margin_before) * 100
    cards = [
        card("Masse", [bar_group("Masse de l'e-drive", mass_before, mass_after, kg(round(mass_before, 2)), kg(round(mass_after, 2)),
                                 delta_badge(mass_after - mass_before, f"{signed_kg(round(mass_after - mass_before, 2))} ({signed((mass_after / mass_before - 1) * 100)} %)", HIGHER_IS_BAD), mass_scale)],
             foot=f"Cible OEM : {kg(model.program['mass_target_kg'])}."),
        card("Coût", [
            bar_group("Coût nomenclature par e-drive", cost_before, cost_after, eur(cost_before, 2), eur(cost_after, 2),
                      delta_badge(cost_after - cost_before, f"{signed_eur(cost_after - cost_before, 2)} ({signed((cost_after / cost_before - 1) * 100)} %)", HIGHER_IS_BAD), cost_scale),
            bar_group("Marge commerciale", margin_before, margin_after, pct(margin_before, 1), pct(margin_after, 1),
                      delta_badge(margin_points, f"{signed(margin_points)} pt", HIGHER_IS_GOOD, tolerance=0.05), max(margin_before, margin_after, 0.01) * 1.2),
        ]),
        card("Qualité", quality_groups),
        card("Risque", risk_groups),
        card("Part des fournisseurs dans le coût global", share_groups(data["suppliers"])),
        card("Part des matériaux dans le coût global", share_groups(data["materials"])),
    ]
    titles = ["Masse", "Coût", "Qualité", "Risque", "Part des fournisseurs", "Part des matériaux"]
    descriptions = [
        "Somme des masses unitaires × quantités de la nomenclature. Sert à mesurer l'effet sur la masse de l'ensemble et la cible du programme.",
        "Coût nomenclature : somme des coûts unitaires × quantités. Le coût d'une pièce est pondéré par les volumes de ses fournisseurs actifs. Marge : (montant de vente − coût nomenclature − assemblage et validation) / montant de vente. Sert à évaluer l'impact économique par produit.",
        "Score sur 100 : plus il est élevé, mieux c'est. Il combine les défauts fournisseurs (35 points), les livraisons à l'heure (15), la qualification (25), la maturité (15) et les données renseignées (10). La moyenne donne plus d'importance aux pièces de classe A, puis B, puis C.",
        "Risque sur 100 : plus il est élevé, plus la pièce est exposée. Les priorités choisies dans Risques et interdépendances (Élevé 30, Normal 20, Faible 10) sont normalisées sur 100. "
        + " · ".join(f"{c['label']} : {c['max']:.1f} points maximum" for c in scenarios.risk_criteria(model.risk_priorities))
        + ". Moyenne par classe A ×3, B ×2, C ×1. Une pièce A/B avec au plus une source qualifiée reste classée critique, quel que soit son score.",
        "Coût des achats attribué à chaque fournisseur / coût total de la nomenclature. Les volumes de chaque pièce déterminent la répartition. Sert à identifier une concentration des achats ; une hausse de part n'est pas automatiquement défavorable.",
        "Coût de matière consommée pour une famille (masse utilisée × coût au kg × quantités) / coût total de la nomenclature. Sert à repérer les familles qui concentrent les dépenses.",
    ]
    count, columns_per_row = (6, 3) if show_shares else (4, 2)
    for start in range(0, count, columns_per_row):
        for i, column in zip(range(start, start + columns_per_row), st.columns(columns_per_row)):
            with column, st.container(border=True):
                label, help_button = st.columns([5, 2], vertical_alignment="center")
                label.markdown(f"**{titles[i]}**")
                with help_button.popover("?", width="content"):
                    st.write(descriptions[i])
                st.html(cards[i].replace(f"<h5>{escape(titles[i])}</h5>", "").replace("<h5>Part des fournisseurs dans le coût global</h5>", "").replace("<h5>Part des matériaux dans le coût global</h5>", "").replace(">Scénario<", f">{escape(comparison_label)}<"))


# ------------------------------------------------------------------ Résultats complémentaires par facteur


def render_disruption(model, detail):
    if not detail.get("parts"):
        return
    st.markdown(f"**Rupture fournisseur · {detail['weeks']} semaines**")
    columns = st.columns(3)
    columns[0].metric("Fournisseurs en retard", len({row['from'] for row in detail['rows']}), help="Nombre de fournisseurs distincts interrompus dans le périmètre simulé.")
    columns[1].metric("Pièces substituables", sum(row['to'] is not None for row in detail['rows']), help="Références disposant d'une alternative qualifiée et capable de reprendre le volume pendant la rupture.")
    columns[2].metric("Délai global", f"{number(max(row['delay_weeks'] for row in detail['rows']), 1)} semaines", help="Plus long délai parmi les pièces : mobilisation de l'alternative ou retard équivalent de production sans alternative. Les délais ne s'additionnent pas.")
    for row in detail["rows"]:
        with st.container(border=True):
            st.markdown(f"**{row['part']}** · fournisseur interrompu : {row['from']}")
            if row["to"]:
                st.success(f"Substitution simulée vers {row['to']}. Coût unitaire de la pièce : {eur(row['before'], 2)} → {eur(row['after'], 2)} ({signed_eur(row['after'] - row['before'], 2)}).")
                if row['delay_weeks']:
                    st.caption(f"Délai de mobilisation du fournisseur : {number(row['delay_weeks'], 1)} semaine(s). Les indicateurs représentent l'état après cette mobilisation, pendant la rupture.")
            else:
                st.warning(f"Aucun fournisseur alternatif qualifié, mobilisable pendant la rupture et avec une capacité suffisante. Pièce impactée : {row['part']}. Retard équivalent estimé : {number(row['delay_weeks'], 1)} semaine(s) de production.")
                st.caption("Estimation après consommation des stocks et des approvisionnements en transit, en tenant compte des sources restantes et de la reprise du fournisseur.")


def render_price(model, detail, indicators):
    if detail["parts"]:
        st.markdown(f"**Coût matière · {detail['material']} : {signed(detail['pct'], 0)} %** · {detail['parts']} pièce(s) concernée(s).")


def render_change(model, detail):
    if not detail["parts"]:
        return
    st.markdown("**Changement de fournisseur** : indicateurs calculés une fois le nouveau fournisseur qualifié")
    columns = st.columns(3)
    columns[0].metric("Pièces concernées", detail["parts"])
    columns[1].metric("Sans alternative", len(detail["no_alternative"]))
    columns[2].metric("Coût unique", compact_eur(detail["one_off"]), help="Coût de bascule et essais de revalidation si le fournisseur n'est pas encore en qualification.")
    if detail["no_alternative"]:
        st.warning(f"Aucune solution de remplacement référencée pour : {', '.join(detail['no_alternative'])}. Ces pièces restent chez le fournisseur actuel dans les indicateurs.")

def render_release(detail):
    after = detail["after"]
    maturities = detail["maturities"]
    current = sorted({row['Maturité actuelle'] for row in maturities}, key=MATURITY_RANK.get)
    st.markdown("#### Situation actuelle")
    if current:
        with st.container(key="maturity_situation"):
            for status, column in zip(current, st.columns(len(current))):
                column.metric(status, sum(row['Maturité actuelle'] == status for row in maturities))
        nonconforming = [{"Pièce": row['Pièce'], "Maturité actuelle": row['Maturité actuelle']}
                         for row in maturities if MATURITY_RANK[row['Maturité actuelle']] < MATURITY_RANK[detail['target']]]
        if nonconforming:
            st.markdown("**Pièces dont la maturité n’est pas conforme**")
            st.dataframe(nonconforming, hide_index=True, width="stretch")
        else:
            st.success("Toutes les pièces du périmètre ont une maturité conforme.")
    else:
        st.info("Aucune pièce dans le périmètre.")
    st.metric("Assemblages à corriger", len(after["corrections"]), help="Assemblages plus avancés que leurs sous-composants.")
    remaining = [f"{r['part']} ({r['status'].lower()})" for r in after["rows"] if r["in_scope"] and not r["ready"]]
    if remaining:
        st.caption("Restent à traiter : " + ", ".join(remaining) + ".")
    if after["corrections"]:
        st.caption("Assemblages à corriger : " + ", ".join(after["corrections"]) + ".")
    if after["excluded"]:
        st.caption("Hors périmètre : " + ", ".join(after["excluded"]) + ".")


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
    columns = st.columns(2)
    columns[0].metric("Revalidation", f"{detail['weeks']} semaines")
    columns[1].metric("Interfaces à revérifier", detail['interfaces'])
    st.caption("État simulé après modification : nouvelle révision en IN_WORK, qualification des fournisseurs remise en cours. Les interfaces sélectionnées entraînent une revérification des pièces liées.")
    st.markdown("**Impact sur les critères de risque de la pièce**")
    st.dataframe([{"Critère": r['criterion'], "Points avant": round(r['before'], 2), "Points après": round(r['after'], 2), "Écart": round(r['after'] - r['before'], 2), "Explication": r['detail']} for r in detail['criteria']], hide_index=True, width="stretch")
    with st.expander("Impact sur les critères de qualité"):
        st.dataframe([{"Critère": r['criterion'], "Points avant": round(r['before'], 2), "Points après": round(r['after'], 2), "Écart": round(r['after'] - r['before'], 2)} for r in detail['quality_criteria']], hide_index=True, width="stretch")
    if detail['neighbors']:
        st.markdown("**Pièces liées à revérifier**")
        st.dataframe([{"Pièce": r['part'], "Interface": r['type']} for r in detail['neighbors']], hide_index=True, width="stretch")
    st.caption("Chaînes d’assemblage concernées : " + " · ".join(detail['assemblies']))


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
    if details.get("versioning"):
        render_versioning(details["versioning"])
    if result["touched"]:
        render_touched(model, result["touched"])
    if result["sources"]:
        theme.sources_expander(model, result["sources"])


def render(model):
    render_settings(model)
    params = read_params()
    result = impact.analyze(model, params)
    with st.container(border=True):
        render_results(model, result, len(params) > 1)
