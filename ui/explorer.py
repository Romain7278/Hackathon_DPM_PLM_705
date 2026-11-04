"""Onglet Product Explorer : arborescence, fiche, relations, traçabilité et contrôle des données."""
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from plm import scenarios
from plm.fmt import eur, kg, number, pct
from plm.model import FAMILIES, normalize
from plm.quality import INFO, MISSING, PARENT_CHILD, SEVERITY_ICONS, SEVERITY_RANK, control_findings, counts, field_completeness, parent_child_links
from ui import theme
from ui.state import EXPLORER_TREE, close_detail, open_from_table, select_node, selected_id

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "plm_tree"
plm_tree = components.declare_component("plm_tree", path=str(COMPONENT_DIR))

TABS = [EXPLORER_TREE, "Nomenclature", "Contrôle des données", "Répartition et espace"]
MATURITIES = ["PRIVATE", "IN_WORK", "FROZEN", "RELEASED", "OBSOLETE"]
TREE_HEIGHT = 700


def tree_payload(model, node):
    # Les pastilles de l'arbre signalent seulement les contrôles du XML et la cohérence parent-enfant.
    own = counts(control_findings(model.findings_for_node(node)))
    subtree = counts(control_findings(model.subtree_findings(node)))
    product = node.product
    ei = node.wrapper["maturity"] if node.wrapper and node.wrapper["maturity"] != product["maturity"] else None
    # Un assemblage trouvé ouvre tout son contenu : on ne cherche donc que dans son nom, pas dans sa description.
    searchable = [node.label, product["name"], product["plm_id"], node.wrapper["name"] if node.wrapper else None]
    if not node.is_assembly:
        searchable += [product["description"], product.get("material"), product.get("material_family")]
    search = normalize(" ".join(filter(None, searchable))).replace(" ", "").replace("-", "")
    return {
        "id": node.id,
        "part_id": node.part_id,
        "label": node.label,
        "plm_name": product["name"],
        "qty": node.quantity,
        "pieces": node.abs_quantity,
        "rev": product["revision"],
        "maturity": product["maturity"],
        "ei_maturity": ei,
        "mass": round(node.total_mass, 3),
        "family": product.get("material_family"),
        "assembly": node.is_assembly,
        "err": own["Bloquant"],
        "warn": own["Attention"],
        "sub_err": subtree["Bloquant"],
        "sub_warn": subtree["Attention"],
        "search": search,
        "children": [tree_payload(model, child) for child in node.children],
    }


def render_kpis(model):
    kpis = scenarios.product_kpis(model)
    alerts = kpis["alerts"]
    box = kpis["bounding_box_mm"]
    columns = st.columns(7)
    columns[0].metric("Masse totale", kg(round(kpis["mass_kg"], 2)), help="Somme des pièces de la nomenclature, identique à la masse déclarée sur le produit.")
    columns[1].metric("Pièces / références", f"{kpis['pieces']} / {kpis['references']}")
    columns[2].metric("Coût nomenclature", eur(kpis["bom_cost"]), help="Coût par e-drive, moyenne des prix fournisseurs pondérée par les parts de volume.")
    columns[3].metric("Fournisseurs actifs", f"{kpis['suppliers_active']} ({kpis['countries']} pays)")
    columns[4].metric("Pièces mono-source", kpis["single_source_parts"], help="Pièces avec au plus un fournisseur qualifié.")
    columns[5].metric("Alertes bloquantes", alerts["Bloquant"], help=f"Données manquantes et cohérence parent-enfant. {alerts['Attention']} point d'attention et {alerts['Info']} informations en plus.")
    columns[6].metric("Encombrement (mm)", f"{box[0]}×{box[1]}×{box[2]}", help="Boîte englobante des positions des pièces : ordre de grandeur.")


# ------------------------------------------------------------------ Fiche


def relation_graph(model, node):
    """Graphe de voisinage : chaîne des parents à gauche, contenu ou interfaces à droite."""

    def quoted(text):
        return '"' + str(text).replace('"', "'") + '"'

    lines = [
        "digraph {",
        'rankdir=LR; bgcolor="transparent"; nodesep=0.18; ranksep=0.42;',
        'node [shape=box, style="rounded,filled", fontname="Segoe UI", fontsize=11, color="#c3c2b7", fillcolor="#f2f1ed", fontcolor="#0b0b0b", margin="0.12,0.05", height=0.28];',
        'edge [color="#6c6b66", fontname="Segoe UI", fontsize=9, fontcolor="#52514e", arrowsize=0.6];',
    ]
    path = node.path()[-2:]
    for step in path:
        fill = 'fillcolor="#0d366b", fontcolor="#ffffff", color="#0d366b"' if step is node else ""
        lines.append(f"{quoted(step.id)} [label={quoted(step.label)} {fill}];")
    for parent, child in zip(path, path[1:]):
        lines.append(f"{quoted(parent.id)} -> {quoted(child.id)};")

    if node.is_assembly:
        for child in node.children[:18]:
            quantity = f" × {child.quantity}" if child.quantity > 1 else ""
            lines.append(f'{quoted(child.id)} [label={quoted(child.label + quantity)}];')
            lines.append(f"{quoted(node.id)} -> {quoted(child.id)};")
    else:
        for interface in model.interfaces(node.part_id):
            other = model.nodes_by_part[interface["other"]][0]
            label = model.interface_types[interface["type"]]["label"]
            lines.append(f'{quoted("i_" + other.part_id)} [label={quoted(model.node_label(other.part_id))}, fillcolor="#dbe8f9", color="#86b6ef"];')
            lines.append(f'{quoted(node.id)} -> {quoted("i_" + other.part_id)} [style=dashed, dir=none, label={quoted(label)}];')
        for other in model.nodes_by_part[node.part_id]:
            if other is not node:
                lines.append(f'{quoted("o_" + other.id)} [label={quoted(other.label + " (même pièce 3D)")}, fillcolor="#fff4d6", color="#fab219"];')
                lines.append(f'{quoted(node.id)} -> {quoted("o_" + other.id)} [style=dotted, dir=none];')
    lines.append("}")
    return "\n".join(lines)


def render_relations(model, node):
    st.graphviz_chart(relation_graph(model, node), width="content")
    theme.legend({"Composant sélectionné": "#0d366b", "Hiérarchie (parents et contenu)": "#f2f1ed", "Interface fonctionnelle (pointillés)": "#dbe8f9"})

    if node.is_assembly:
        rows = [{"Composant": c.label, "Qté": c.quantity, "Masse (kg)": round(c.total_mass, 3), "Part de la masse": c.total_mass / node.total_mass, "Coût (€)": round(model.node_cost(c), 2), "Rév.": c.product["revision"], "Maturité": c.product["maturity"]} for c in node.children]
        ids = [c.id for c in node.children]
        key = f"children_{node.id}"
        st.markdown("**Contenu direct**")
        st.dataframe(rows, hide_index=True, width="stretch", key=key, on_select=select_child(key, ids), selection_mode="single-row",
                     column_config={"Part de la masse": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"), "Masse (kg)": st.column_config.NumberColumn(format="localized"), "Coût (€)": st.column_config.NumberColumn(format="localized")})
        return

    occurrences = model.nodes_by_part[node.part_id]
    st.markdown(f"**Où cette pièce est utilisée** : {len(occurrences)} emplacement(s), {model.quantity(node.part_id)} pièce(s)")
    for occurrence in occurrences:
        st.markdown("- " + " › ".join(step.label for step in occurrence.path()) + f" (× {occurrence.abs_quantity})")

    interfaces = model.interfaces(node.part_id)
    real = model.real_interfaces(node.part_id)
    st.markdown(f"**Interdépendances** : {len(real)} interface(s) fonctionnelle(s)")
    if interfaces:
        rows = [{"Avec": model.node_label(i["other"]), "Type": model.interface_types[i["type"]]["label"], "Description": i["note"]} for i in interfaces]
        st.dataframe(rows, hide_index=True, width="stretch")


def select_child(key, ids):
    def callback():
        rows = st.session_state[key].selection.rows
        if rows:
            select_node(ids[rows[0]])

    return callback


def render_suppliers(model, node):
    part = node.product

    def columns(link):
        supplier = model.suppliers[link["supplier"]]
        return {"Fournisseur": supplier["name"], "Origine": f"{supplier['city']}, {supplier['country_name']}", "Part": link["share_pct"] / 100, "Prix (€)": link.get("unit_price_eur"), "Notation": supplier["financial_rating"]}

    config = {"Part": st.column_config.NumberColumn(format="percent"), "Prix (€)": st.column_config.NumberColumn(format="localized")}
    if node.is_assembly:
        part_ids = sorted({leaf.part_id for leaf in node.leaves() if leaf.product.get("physical", True)})
        rows = [{"Pièce": model.node_label(part_id), **columns(link)} for part_id in part_ids for link in model.products[part_id]["sourcing"]]
        st.dataframe(rows, hide_index=True, width="stretch", column_config=config)
        return
    if not part.get("physical", True):
        st.info("Géométrie d'étude : pas de fournisseur attendu.")
        return
    if not part["sourcing"]:
        st.error("Aucun fournisseur désigné pour cette pièce.")
        return
    qualified = len(model.qualified_links(part))
    if qualified <= 1:
        st.warning(f"Pièce critique côté achats : {qualified} fournisseur qualifié sur {len(part['sourcing'])} référencé(s).")
    if part.get("sourcing_note"):
        st.caption(part["sourcing_note"])
    st.dataframe([columns(link) for link in sorted(part["sourcing"], key=lambda l: -l["share_pct"])], hide_index=True, width="stretch", column_config=config)
    st.caption(f"Stock de sécurité : {part.get('safety_stock_days', 0)} jours ouvrés.")


def render_traceability(model, node):
    part = node.product
    rows = [
        ("ID PLM", f"<code>{escape(part['plm_id'])}</code>"),
        ("ID XML", f"<code>{escape(part['xml_id'])}</code>"),
        ("Nom PLM", escape(part["name"])),
    ]
    if node.wrapper:
        rows.append(("Engineering Item", f"{escape(node.wrapper['name'])} · <code>{escape(node.wrapper['plm_id'])}</code> · {escape(node.wrapper['maturity'])}"))
    rows += [
        ("Révision", f"{escape(part['revision'])} (indice {part['revision_index']})"),
        ("Famille de révision", f"<code>{escape(part['revision_family'])}</code>"),
        ("Maturité", f"{escape(part['maturity'])} depuis le {escape(str(part.get('maturity_date', 'non renseigné')))}"),
        ("Cycle de vie", f"<code>{escape(part['lifecycle'])}</code>"),
        ("Créé le", escape(part["created"][:10])),
        ("Modifié le", escape(part["modified"][:10])),
        ("Propriétaire", escape(part["owner"])),
        ("Projet", escape(part["project"])),
    ]
    if part.get("sourcing"):
        rows.append(("Fournisseur(s)", ", ".join(escape(model.suppliers[l["supplier"]]["name"]) for l in model.active_links(part))))
    theme.key_values(rows)

    if not part["revisions"]:
        st.info("Historique de révision non renseigné.")
        return
    st.markdown("**Suivi de versions**")
    rows = []
    previous = None
    for revision in part["revisions"]:
        mass = revision.get("mass_kg")
        rows.append({
            "Rév.": revision["name"], "Date": revision["date"], "ECO": revision["eco"], "Motif": revision["reason"],
            "Masse (kg)": mass, "Écart (kg)": round(mass - previous, 3) if previous is not None and mass is not None else None,
            "Matériau": revision.get("material", part["material"] or ""),
        })
        previous = mass
    st.dataframe(rows, hide_index=True, width="stretch", column_config={"Masse (kg)": st.column_config.NumberColumn(format="localized"), "Écart (kg)": st.column_config.NumberColumn(format="localized")})


def composition_chart(model, node, metric):
    values = {}
    for leaf in node.leaves():
        family = leaf.product.get("material_family")
        amount = leaf.total_mass if metric == "mass" else model.unit_cost(leaf.product)[0] * leaf.abs_quantity
        values[family] = values.get(family, 0) + amount
    total = sum(values.values())
    fig = go.Figure()
    for family in FAMILIES:
        if family in values:
            share = values[family] / total
            amount = kg(round(values[family], 2)) if metric == "mass" else eur(values[family])
            fig.add_bar(y=[""], x=[values[family]], name=family, orientation="h", marker=dict(color=theme.FAMILY_COLORS[family], line=dict(color=theme.SURFACE, width=2)),
                        hovertext=f"{family} : {amount}, {pct(share)}", hoverinfo="text", width=0.7)
    fig.update_layout(barmode="stack")
    theme.style_figure(fig, height=90, margin=dict(l=4, r=4, t=26, b=4))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, showgrid=False)
    return fig


def render_cost(model, node):
    part = node.product
    if node.is_assembly:
        theme.show(composition_chart(model, node, "mass"), key=f"compo_mass_{node.id}")
        rows = []
        leaves = {}
        for leaf in node.leaves():
            leaves.setdefault(leaf.part_id, 0)
            leaves[leaf.part_id] += leaf.abs_quantity
        groups = {}
        for part_id, quantity in leaves.items():
            product = model.products[part_id]
            group = groups.setdefault(product.get("material_family"), {"mass": 0.0, "cost": 0.0, "refs": 0})
            group["mass"] += product["mass_kg"] * quantity
            group["cost"] += model.unit_cost(product)[0] * quantity
            group["refs"] += 1
        total_mass = sum(g["mass"] for g in groups.values())
        total_cost = sum(g["cost"] for g in groups.values())
        for family in FAMILIES:
            if family in groups:
                group = groups[family]
                rows.append({"Famille": family, "Références": group["refs"], "Masse (kg)": round(group["mass"], 2), "Part de la masse": group["mass"] / total_mass, "Coût (€)": round(group["cost"], 2), "Part du coût": group["cost"] / total_cost if total_cost else 0})
        st.dataframe(rows, hide_index=True, width="stretch", column_config={
            "Part de la masse": st.column_config.NumberColumn(format="percent"), "Part du coût": st.column_config.NumberColumn(format="percent"),
            "Masse (kg)": st.column_config.NumberColumn(format="localized"), "Coût (€)": st.column_config.NumberColumn(format="localized")})
        return

    material = model.material_of(part)
    unit_cost, kind = model.unit_cost(part)
    rows = [("Matériau", escape(part["material"] or "Non renseigné"))]
    if material:
        rows.append(("Famille, densité", f"{escape(material['family'])}, {number(material['density_kg_dm3'], 2)} kg/dm³"))
        rows.append(("Prix matière", f"{eur(material['price_eur_kg'], 2)}/kg · {escape(material['index'])}"))
    if part.get("usage_kg"):
        rows.append(("Matière consommée", f"{kg(part['usage_kg'])} par pièce"))
    rows.append(("Coût unitaire", f"{eur(unit_cost, 2)} ({escape(kind.lower())})"))
    if material and part.get("usage_kg"):
        rows.append(("CO2 matière", f"{number(part['usage_kg'] * material['co2_kg_per_kg'] * model.quantity(node.part_id), 1)} kg CO2e par e-drive"))
    volume = model.volume_litres(part)
    if volume:
        rows.append(("Volume matière", f"{number(volume * model.quantity(node.part_id), 2)} L (masse et densité)"))
    theme.key_values(rows)


def render_alerts_block(model, node):
    findings = sorted(model.findings_for_node(node), key=lambda f: SEVERITY_RANK[f["severity"]])
    if node.is_assembly:
        below = [f for f in model.subtree_findings(node) if f not in findings and f["severity"] != INFO]
        if below:
            total = counts(below)
            st.caption(f"Dans le contenu de cet assemblage : {total['Bloquant']} alerte(s) bloquante(s), {total['Attention']} point(s) d'attention.")
    for finding in findings:
        icon = SEVERITY_ICONS[finding["severity"]]
        theme.html(f'<div class="plm-alert"><span>{icon}</span><div><b>{escape(finding["severity"])}</b> · {escape(finding["domain"])} : {escape(finding["message"])}</div></div>')


def render_detail(model, node):
    part = node.product
    path = node.path()
    crumbs, close = st.columns([5, 2], vertical_alignment="center")
    with crumbs, st.container(horizontal=True, vertical_alignment="center", gap="small"):
        for step in path[:-1]:
            st.button(step.label, key=f"crumb_{step.id}", type="tertiary", on_click=select_node, args=(step.id,))
            st.markdown("›")
        st.markdown(f"**{escape(node.label)}**")
    close.button("Fermer la fiche", icon=":material/close:", key="close_detail", on_click=close_detail, width="stretch")

    quantity = f" × {node.quantity}" if node.quantity > 1 else ""
    title = node.label if node.is_assembly or len(model.nodes_by_part[node.part_id]) > 1 else model.node_label(node.part_id)
    st.markdown(f"#### {escape(title)}{quantity}")
    if part["description"]:
        st.caption(part["description"])
    tags = [(part["maturity"], theme.MATURITY_COLORS[part["maturity"]]), (f"Révision {part['revision']}", None), ("Assemblage" if node.is_assembly else "Pièce", None)]
    if part.get("material_family"):
        tags.append((part["material_family"], theme.FAMILY_COLORS[part["material_family"]]))
    if part.get("criticality") and not node.is_assembly:
        tags.append((f"Classe {part['criticality']}", None))
    if not node.is_assembly and part.get("physical", True):
        complexity = model.complexity(part)
        tags.append((f"Complexité {complexity['level'].lower()}, {complexity['score']} sur 100", None))
    if not node.is_assembly and part.get("physical", True) and model.is_single_source(part):
        tags.append(("Mono-source", theme.LEVEL_COLORS["Critique"]))
    theme.badges(tags)

    leaves = node.leaves()
    columns = st.columns(4)
    if node.is_assembly:
        columns[0].metric("Masse", kg(round(node.total_mass, 3)), help="Masse déclarée du composant.")
        columns[1].metric("Part du produit", pct(node.total_mass / model.tree.total_mass, 1))
        columns[2].metric("Pièces / références", f"{sum(l.abs_quantity for l in leaves)} / {len({l.part_id for l in leaves})}")
        columns[3].metric("Coût", eur(model.node_cost(node)))
    else:
        unit_cost = model.unit_cost(part)[0]
        several = node.abs_quantity > 1
        columns[0].metric(f"Masse (× {node.abs_quantity})" if several else "Masse", kg(round(node.total_mass, 3)), help=f"{kg(part['mass_kg'])} par pièce.")
        columns[1].metric("Part du parent", pct(node.total_mass / node.parent.total_mass, 1) if node.parent else "100 %", help=f"Part de la masse de {node.parent.label}." if node.parent else None)
        columns[2].metric(f"Coût (× {node.abs_quantity})" if several else "Coût", eur(unit_cost * node.abs_quantity, 2), help=f"{eur(unit_cost, 2)} par pièce.")
        columns[3].metric("Interdépendances", len(model.real_interfaces(node.part_id)))

    render_alerts_block(model, node)

    tabs = st.tabs(["Relations", "Fournisseurs", "Traçabilité", "Matière et coût"])
    with tabs[0]:
        render_relations(model, node)
    with tabs[1]:
        render_suppliers(model, node)
    with tabs[2]:
        render_traceability(model, node)
    with tabs[3]:
        render_cost(model, node)


def sync_tree_selection():
    """Lit le clic de l'arbre avant la mise en page : la fiche s'ouvre dès ce passage."""
    value = st.session_state.get("plm_tree")
    if value and value["n"] != st.session_state.get("tree_last_click"):
        st.session_state.tree_last_click = value["n"]
        st.session_state.selected_id = value["id"]


def render_tree_tab(model):
    sync_tree_selection()
    current = selected_id()
    node = model.nodes.get(current) if current else None
    st.caption("Cliquez sur un composant pour ouvrir sa fiche. Le bouton Liste / Arbre change l'affichage.")
    columns = st.columns([5, 7], gap="medium") if node else st.columns([1])
    with columns[0]:
        plm_tree(tree=_payload(model), selected=current, height=TREE_HEIGHT, maturities=MATURITIES, families=FAMILIES, key="plm_tree", default=None)
    if node:
        with columns[1]:
            render_detail(model, node)


def _payload(model):
    if not hasattr(model, "tree_payload"):
        model.tree_payload = tree_payload(model, model.tree)
    return model.tree_payload


# ------------------------------------------------------------------ Nomenclature


def render_bom_tab(model):
    critical = {row["part_id"]: row for row in scenarios.criticality(model)}
    rows = []
    node_ids = []
    total_mass = model.tree.total_mass
    total_cost = model.bom_cost()
    for part in model.parts:
        part_id = part["xml_id"]
        node = model.nodes_by_part[part_id][0]
        quantity = model.quantity(part_id)
        crit = critical.get(part_id)
        alerts = counts(model.findings_for_node(node))
        rows.append({
            "Référence": model.node_label(part_id),
            "Sous-ensemble": node.top_level().label,
            "Qté": quantity,
            "Masse unit. (kg)": part["mass_kg"],
            "Masse totale (kg)": round(part["mass_kg"] * quantity, 3),
            "Part masse": part["mass_kg"] * quantity / total_mass,
            "Coût total (€)": round(model.line_cost(part), 2),
            "Part coût": model.line_cost(part) / total_cost,
            "Matériau": part["material"],
            "Famille": part.get("material_family"),
            "Rév.": part["revision"],
            "Maturité": part["maturity"],
            "Fournisseurs": len(part["sourcing"]),
            "Interfaces": len(model.real_interfaces(part_id)),
            "Criticité": crit["level"] if crit else "Hors périmètre",
            "Alertes": alerts["Bloquant"] + alerts["Attention"],
        })
        node_ids.append(node.id)

    columns = st.columns(3)
    groups = columns[0].multiselect("Sous-ensemble", sorted({r["Sous-ensemble"] for r in rows}), key="bom_groups", placeholder="Tous")
    families = columns[1].multiselect("Famille de matériau", FAMILIES, key="bom_families", placeholder="Toutes")
    maturities = columns[2].multiselect("Maturité", MATURITIES, key="bom_maturities", placeholder="Toutes")
    kept = [i for i, r in enumerate(rows) if (not groups or r["Sous-ensemble"] in groups) and (not families or r["Famille"] in families) and (not maturities or r["Maturité"] in maturities)]
    shown = [rows[i] for i in kept]
    ids = [node_ids[i] for i in kept]
    shown_mass = sum(r["Masse totale (kg)"] for r in shown)
    shown_cost = sum(r["Coût total (€)"] for r in shown)
    st.caption(f"{sum(r['Qté'] for r in shown)} pièces · {len(shown)} références · {kg(round(shown_mass, 3))} ({pct(shown_mass / total_mass, 1)}) · {eur(shown_cost)} ({pct(shown_cost / total_cost, 1)}). Cochez une ligne pour ouvrir sa fiche.")
    st.dataframe(shown, hide_index=True, width="stretch", height=620, key="bom_table", on_select=open_from_table("bom_table", ids), selection_mode="single-row",
                 column_config={
                     "Part masse": st.column_config.NumberColumn(format="percent"), "Part coût": st.column_config.NumberColumn(format="percent"),
                     "Masse unit. (kg)": st.column_config.NumberColumn(format="localized"), "Masse totale (kg)": st.column_config.NumberColumn(format="localized"),
                     "Coût total (€)": st.column_config.NumberColumn(format="localized"),
                 })


# ------------------------------------------------------------------ Contrôle des données


def node_for_product(model, product_id):
    if product_id in model.nodes:
        return model.nodes[product_id]
    return model.nodes_by_part[product_id][0]


def render_missing_section(model, found):
    st.markdown(f"##### {MISSING}")
    left, right = st.columns([7, 5], gap="medium")
    rows = [{"Gravité": f"{SEVERITY_ICONS[f['severity']]} {f['severity']}", "Élément": f["element"] or node_for_product(model, f["product_id"]).label, "Champ": f["field"], "Constat": f["message"]} for f in found]
    ids = [None if f["element"] else node_for_product(model, f["product_id"]).id for f in found]
    with left:
        st.dataframe(rows, hide_index=True, width="stretch", key="dq_missing", on_select=open_from_table("dq_missing", ids), selection_mode="single-row",
                     column_config={"Constat": st.column_config.TextColumn(width="large")})
        st.caption("Cochez une ligne pour ouvrir la fiche de la pièce. Un champ vide sur tout un type d'objet donne une seule ligne.")
    completeness = field_completeness(model)
    gaps = [{"Objet": r["object"], "Champ": r["field"], "Remplis": f"{r['filled']} / {r['total']}", "Taux": r["rate"]} for r in completeness if r["filled"] < r["total"]]
    with right:
        st.dataframe(gaps, hide_index=True, width="stretch", column_config={"Taux": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
        complete = sum(r["filled"] == r["total"] for r in completeness)
        with st.expander(f"Tous les champs contrôlés ({len(completeness)}, dont {complete} complets)"):
            st.dataframe([{"Objet": r["object"], "Champ": r["field"], "Remplis": f"{r['filled']} / {r['total']}", "Taux": r["rate"]} for r in completeness], hide_index=True, width="stretch",
                         column_config={"Taux": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
        st.caption("Un assemblage sans matériau est normal : ce cas n'est pas signalé.")


def render_parent_child_section(model):
    links = parent_child_links(model)
    issues = links["issues"]
    st.markdown(f"##### {PARENT_CHILD}")
    theme.note("<b>Règle :</b> un parent FROZEN ou RELEASED ne peut pas être plus avancé que ses enfants directs, et un enfant OBSOLETE ne devrait plus être utilisé par un parent actif. "
               "Échelle de maturité : PRIVATE, IN_WORK, FROZEN, RELEASED.")
    rows = [{"Parent": r["parent"], "Maturité du parent": r["parent_maturity"], "Enfant": r["child"], "Maturité de l'enfant": r["child_maturity"], "Écart (niveaux)": r["gap"], "Constat": f"🔴 {r['problem']}"} for r in issues]
    ids = [node_for_product(model, r["child_id"]).id for r in issues]
    st.dataframe(rows, hide_index=True, width="stretch", key="dq_links", on_select=open_from_table("dq_links", ids), selection_mode="single-row",
                 column_config={"Constat": st.column_config.TextColumn(width="medium")})
    st.caption(f"{links['checked']} liens parent-enfant du XML vérifiés, {len(issues)} incohérents. Cochez une ligne pour ouvrir la fiche de l'enfant.")


def render_quality_tab(model):
    found = control_findings(model.findings)
    total = counts(found)
    links = parent_child_links(model)
    columns = st.columns(4)
    columns[0].metric("🔴 Bloquant", total["Bloquant"], help="À corriger avant toute release.")
    columns[1].metric("🟠 Attention", total["Attention"], help="Donnée à vérifier.")
    columns[2].metric("🔵 Info", total["Info"], help="Amélioration de la qualité des données.")
    columns[3].metric("Liens parent-enfant cohérents", f"{links['checked'] - len(links['issues'])} / {links['checked']}")
    render_missing_section(model, [f for f in found if f["domain"] == MISSING])
    render_parent_child_section(model)
    st.caption("Les autres constats (approvisionnement, nommage, structure, cycle de vie) restent affichés sur la fiche de chaque pièce.")


# ------------------------------------------------------------------ Répartition et espace


def treemap(model, metric):
    ids, labels, parents, values, colors, hovers = [], [], [], [], [], []

    def visit(node, parent_id):
        amount = node.total_mass if metric == "mass" else model.node_cost(node)
        label = node.label + (f" × {node.quantity}" if node.quantity > 1 else "")
        ids.append(node.id)
        labels.append(label)
        parents.append(parent_id)
        values.append(0 if node.is_assembly else amount)
        family = node.product.get("material_family")
        colors.append(theme.FAMILY_COLORS.get(family, "#f0efec"))
        hovers.append(f"<b>{kg(round(amount, 3)) if metric == 'mass' else eur(amount, 2)}</b><br>{node.label}<br>{node.product.get('material') or 'Assemblage'}")
        for child in node.children:
            visit(child, node.id)

    visit(model.tree, "")
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="remainder",
        marker=dict(colors=colors, line=dict(color=theme.SURFACE, width=2)),
        hovertext=hovers, hoverinfo="text", textinfo="label", tiling=dict(pad=2),
        pathbar=dict(visible=True, thickness=22), root=dict(color="#f0efec"), maxdepth=-1,
    ))
    theme.style_figure(fig, height=560, legend_visible=False, margin=dict(l=2, r=2, t=4, b=2))
    return fig


def spatial_view(model):
    fig = go.Figure()
    grouped = {}
    for part in model.parts:
        family = part.get("material_family")
        for position in model.positions.get(part["xml_id"], []):
            grouped.setdefault(family, []).append((position, part))
    for family in FAMILIES:
        points = grouped.get(family, [])
        if not points:
            continue
        fig.add_trace(go.Scatter3d(
            x=[p[0][0] for p in points], y=[p[0][1] for p in points], z=[p[0][2] for p in points], mode="markers", name=family,
            marker=dict(size=[4 + 16 * (p[1]["mass_kg"] / 21.5) ** 0.5 for p in points], color=theme.FAMILY_COLORS[family], line=dict(width=0), opacity=0.92),
            hovertext=[f"<b>{model.node_label(p[1]['xml_id'])}</b><br>{kg(p[1]['mass_kg'])}<br>x={number(p[0][0])} y={number(p[0][1])} z={number(p[0][2])} mm" for p in points],
            hoverinfo="text",
        ))
    axes = (("ID_30", "ID_3", "Axe moteur"), ("ID_38", "ID_40", "Axe intermédiaire"), ("ID_34", "ID_36", "Axe de sortie"))
    for first, second, label in axes:
        a, b = model.positions[first][0], model.positions[second][0]
        fig.add_trace(go.Scatter3d(x=[a[0], b[0]], y=[a[1], b[1]], z=[a[2], b[2]], mode="lines+text", line=dict(color=theme.INK2, width=4), name=label, text=["", label], textposition="top center", textfont=dict(size=11, color=theme.INK), hoverinfo="name", showlegend=False))
    theme.style_figure(fig, height=560, margin=dict(l=0, r=0, t=30, b=0))
    scene_axis = dict(backgroundcolor="rgba(0,0,0,0)", gridcolor=theme.GRID, zerolinecolor=theme.BASELINE, color=theme.INK2)
    fig.update_layout(scene=dict(aspectmode="data", xaxis=dict(title="X (mm)", **scene_axis), yaxis=dict(title="Y (mm)", **scene_axis), zaxis=dict(title="Z (mm)", **scene_axis), camera=dict(eye=dict(x=1.5, y=-1.2, z=0.8))))
    return fig


def render_spread_tab(model):
    left, right = st.columns(2, gap="medium")
    with left:
        st.session_state.setdefault("map_metric", "Masse")
        metric_label = st.segmented_control("Répartition par", ["Masse", "Coût"], key="map_metric", required=True)
        metric = "mass" if metric_label == "Masse" else "cost"
        theme.legend({family: theme.FAMILY_COLORS[family] for family in FAMILIES})
        theme.show(treemap(model, metric), key=f"treemap_{metric}")
        st.caption("Cliquez sur un sous-ensemble pour zoomer. Les valeurs détaillées sont dans l'onglet Nomenclature.")
    with right:
        box = model.bounding_box()
        total_volume = sum((model.volume_litres(p) or 0) * model.quantity(p["xml_id"]) for p in model.parts)
        st.markdown(f"**Vue spatiale** : positions des {sum(len(model.positions.get(p['xml_id'], [])) for p in model.parts)} instances, avec les 3 axes du réducteur")
        theme.show(spatial_view(model), key="spatial")
        st.caption(f"Boîte englobante {box[0]} × {box[1]} × {box[2]} mm, volume matière {number(total_volume, 1)} L. Chaque point est la position d'une pièce.")


def render(model):
    render_kpis(model)
    tabs = st.tabs(TABS, key="explorer_tab", on_change="rerun")
    with tabs[0]:
        if tabs[0].open:
            render_tree_tab(model)
    with tabs[1]:
        if tabs[1].open:
            render_bom_tab(model)
    with tabs[2]:
        if tabs[2].open:
            render_quality_tab(model)
    with tabs[3]:
        if tabs[3].open:
            render_spread_tab(model)
