"""Outils d'interrogation des données, partagés par le chatbot Claude et le mode local.

Chaque outil renvoie un dictionnaire compact avec une clé "sources" : les éléments PLM réellement lus.
C'est cette liste, et non le texte du modèle, qui alimente l'affichage des sources dans le chat.
"""
from plm import scenarios
from plm.model import MATURITY_RANK, QUALIFICATION_LABELS, normalize


class ToolError(Exception):
    """Demande impossible à résoudre (pièce inconnue, nom ambigu) : le message est renvoyé tel quel."""


def resolve_node(model, text):
    nodes = model.find_part(text)
    if not nodes:
        raise ToolError(f"Aucune pièce trouvée pour « {text} ».")
    if len(nodes) > 1 and len({n.part_id for n in nodes}) > 1:
        options = ", ".join(f"{n.id} ({n.label}, rév. {n.product['revision']}, {n.unit_mass} kg)" for n in nodes)
        raise ToolError(f"Plusieurs pièces correspondent à « {text} » : {options}. Préciser l'ID ou un terme comme couronne, pignon d'entrée, roue du 1er étage, pignon du 2e étage.")
    return nodes[0]


def resolve_supplier(model, text):
    supplier = model.find_supplier(text)
    if supplier is None:
        known = ", ".join(s["name"] for s in model.suppliers.values())
        raise ToolError(f"Fournisseur « {text} » inconnu. Fournisseurs référencés : {known}.")
    return supplier


def rounded(value, digits=2):
    return round(value, digits) if isinstance(value, float) else value


def search_parts(model, query, family=None, maturity=None, limit=12):
    terms = normalize(query)
    matches = []
    for node in model.nodes.values():
        if node.is_assembly and (family or maturity):
            continue
        part = node.product
        text = normalize(" ".join(filter(None, [node.label, part["name"], part["description"], part["material"], part.get("material_family"), part["plm_id"], node.id])))
        if terms and terms not in text:
            continue
        if family and part.get("material_family") != family:
            continue
        if maturity and part["maturity"] != maturity:
            continue
        matches.append(node)
    if not matches and terms:
        matches = model.find_part(query)
    rows = [{"id": n.id, "part_id": n.part_id, "name": n.label, "plm_name": n.product["name"], "plm_id": n.product["plm_id"], "quantity": n.abs_quantity,
             "mass_kg": rounded(n.total_mass, 3), "material": n.product["material"], "revision": n.product["revision"], "maturity": n.product["maturity"]} for n in matches[:limit]]
    return {"count": len(matches), "results": rows, "sources": [model.source_ref(n.part_id, "nom, masse, matériau, maturité") for n in matches[:limit]]}


def part_details(model, part):
    node = resolve_node(model, part)
    product = node.product
    part_id = node.part_id
    result = {
        "name": node.label,
        "plm_name": product["name"],
        "plm_id": product["plm_id"],
        "xml_id": part_id,
        "kind": "assemblage" if node.is_assembly else "pièce",
        "description": product["description"],
        "path": " › ".join(step.label for step in node.path()),
        "revision": product["revision"],
        "maturity": product["maturity"],
        "maturity_date": product.get("maturity_date"),
        "lifecycle": product["lifecycle"],
        "owner": product["owner"],
        "created": product["created"][:10],
        "modified": product["modified"][:10],
        "mass_unit_kg": product["mass_kg"],
        "quantity": node.abs_quantity,
        "mass_total_kg": rounded(node.total_mass, 3),
        "cost_total_eur": rounded(model.node_cost(node)),
        "alerts": [{"severity": f["severity"], "message": f["message"]} for f in model.findings_for_node(node)],
        "history": [{k: r.get(k) for k in ("name", "date", "eco", "reason", "mass_kg")} for r in product["revisions"]],
    }
    if node.is_assembly:
        result["children"] = [{"name": c.label, "quantity": c.quantity, "mass_kg": rounded(c.total_mass, 3), "maturity": c.product["maturity"]} for c in node.children]
    else:
        unit_cost, cost_kind = model.unit_cost(product)
        result.update({
            "material": product["material"],
            "unit_cost_eur": rounded(unit_cost),
            "cost_kind": cost_kind,
            **({"complexity": model.complexity(product)} if product.get("physical", True) else {}),
            "volume_l": rounded(model.volume_litres(product) or 0, 3),
            "positions_mm": model.positions.get(part_id, [])[:4],
            "suppliers": [{"id": l["supplier"], "name": model.suppliers[l["supplier"]]["name"], "country": model.suppliers[l["supplier"]]["country_name"], "share_pct": l["share_pct"],
                           "price_eur": l.get("unit_price_eur"), "lead_time_days": l["lead_time_days"], "status": QUALIFICATION_LABELS[l["qualification"]]} for l in product["sourcing"]],
            "interfaces": [{"with": model.node_label(i["other"]), "type": model.interface_types[i["type"]]["label"], "note": i["note"]} for i in model.interfaces(part_id)],
        })
    sources = [model.source_ref(product, "identité, structure, masse, maturité, historique")]
    sources += [model.supplier_ref(l["supplier"], "prix, délai, PPAP") for l in product["sourcing"]]
    return {**result, "sources": sources}


def product_structure(model, assembly=None):
    node = resolve_node(model, assembly) if assembly else model.tree
    if not node.is_assembly:
        node = node.parent
    leaves = node.leaves()
    return {
        "assembly": node.label,
        "plm_id": node.product["plm_id"],
        "mass_kg": rounded(node.total_mass, 3),
        "pieces": sum(leaf.abs_quantity for leaf in leaves),
        "references": len({leaf.part_id for leaf in leaves}),
        "cost_eur": rounded(model.node_cost(node)),
        "children": [{"name": c.label, "plm_id": c.product["plm_id"], "kind": "assemblage" if c.is_assembly else "pièce", "quantity": c.quantity,
                      "mass_kg": rounded(c.total_mass, 3), "maturity": c.product["maturity"]} for c in node.children],
        "sources": [model.source_ref(node.product, "structure, masse")] + [model.source_ref(c.product, "structure, masse") for c in node.children],
    }


def data_alerts(model, severity=None, domain=None, part=None, limit=25):
    from plm.quality import counts

    findings = model.findings
    if part:
        findings = model.subtree_findings(resolve_node(model, part))
    if severity:
        findings = [f for f in findings if normalize(f["severity"]) == normalize(severity)]
    if domain:
        findings = [f for f in findings if normalize(domain) in normalize(f["domain"])]
    return {
        "totals": counts(findings),
        "shown": len(findings[:limit]),
        "alerts": [{k: f[k] for k in ("severity", "domain", "name", "message")} for f in findings[:limit]],
        "sources": [model.source_ref(f["product_id"], f"contrôle {f['rule']}") for f in findings[:limit]],
    }


def critical_parts(model, top=10):
    rows = scenarios.criticality(model)
    selected = rows[:top]
    fields = ("name", "plm_id", "score", "level", "level_reason", "reasons", "breakdown", "complexity", "complexity_level", "sources_qualified", "sources_referenced", "origin", "interfaces", "mass_kg", "line_cost", "cost_share", "quantity")
    return {
        "levels": {level: sum(r["level"] == level for r in rows) for level, _ in scenarios.LEVELS},
        "rule": "Score sur 100 : sources, délai de remplacement, délai, origine, santé financière, classe fonctionnelle, interdépendances, poids dans le coût. Une pièce de classe A ou B avec un seul fournisseur qualifié est critique.",
        "parts": [{k: rounded(r[k]) for k in fields} for r in selected],
        "sources": [model.source_ref(r["part_id"], "sourcing, interfaces, masse, coût") for r in selected],
    }


def supply_disruption(model, part, supplier=None, weeks=8):
    node = resolve_node(model, part)
    if node.is_assembly:
        raise ToolError(f"{node.label} est un assemblage : préciser une pièce.")
    supplier_id = resolve_supplier(model, supplier)["id"] if supplier else None
    result = scenarios.simulate_disruption(model, node.part_id, supplier_id, int(weeks))
    if "error" in result:
        raise ToolError(result["error"])
    keys = ("lost_units", "stop_days", "first_stop_week", "last_stop_week", "margin_lost", "penalty", "extra_purchase", "air_freight", "one_off", "total_cost", "candidates_used")
    return {
        "part": result["part"],
        "supplier": result["supplier"],
        "share_lost_pct": result["share_lost_pct"],
        "duration_weeks": result["duration_weeks"],
        "hypothesis": "Cadence série de 1 000 e-drives par semaine.",
        "plant_stock_days": result["plant_stock_days"],
        "transit_days": result["transit_days"],
        "cover_days_before_line_stop": rounded(result["cover_days"]) if result["cover_days"] is not None else None,
        "blocked_chains": result["blocked_chains"],
        "interfaces": result["interfaces"],
        "strategies": {name: {"label": s["label"], **{k: rounded(s[k], 0) for k in keys}} for name, s in result["strategies"].items()},
        "best_strategy": result["best"],
        "alternatives": [{k: rounded(a[k]) for k in ("supplier", "country", "status", "share_pct", "capacity", "price", "delay_weeks", "delay_emergency_weeks", "switching_cost")} for a in result["alternatives"]],
        "other_parts_at_same_supplier": [{k: rounded(e[k]) for k in ("part", "share_pct", "cover_days", "single_source")} for e in result["exposed_parts"]],
        "recommendations": result["recommendations"],
        "sources": result["sources"],
    }


def material_price(model, material, pct):
    family = model.find_family(material)
    exact = next((m["plm_name"] for m in model.materials.values() if normalize(material) == normalize(m["plm_name"])), None)
    if not family and not exact:
        families = sorted({m["family"] for m in model.materials.values() if m["in_bom"]})
        raise ToolError(f"Matériau « {material} » inconnu. Familles disponibles : {', '.join(families)}.")
    result = scenarios.material_price_impact(model, family=None if exact else family, material=exact, pct=float(pct))
    keys = ("family", "material", "pct", "parts", "mass_kg", "delta_unit", "delta_annual", "bom_before", "bom_after", "margin_pct_before", "margin_pct_after", "first_12_months", "share_within_3_months")
    return {
        **{k: rounded(result[k], 3) for k in keys},
        "hypothesis": "Seule la part indexée du prix matière varie, pas la conversion. Volume de 48 000 e-drives par an.",
        "rows": [{k: rounded(r[k]) for k in ("part", "plm_id", "material", "quantity", "usage_kg", "price_before", "price_after", "delta_part", "delta_unit", "delta_annual", "first_month", "clauses")} for r in result["rows"]],
        "sources": result["sources"],
    }


def supplier_mapping(model, supplier=None):
    if supplier:
        target = resolve_supplier(model, supplier)
        table = next(r for r in scenarios.supplier_table(model) if r["supplier_id"] == target["id"])
        parts = [{"part": model.node_label(p["xml_id"]), "plm_id": p["plm_id"], "share_pct": l["share_pct"], "status": QUALIFICATION_LABELS[l["qualification"]], "price_eur": l.get("unit_price_eur"),
                  "single_source": model.is_single_source(p)} for p, l in model.supplier_parts(target["id"], active_only=False)]
        return {"supplier": {**{k: rounded(v, 3) for k, v in table.items() if k not in ("lat", "lon")}, "certification": target["certification"]}, "parts": parts,
                "sources": [model.supplier_ref(target["id"], "pays, notation, qualité")] + [model.source_ref(p["xml_id"], "sourcing") for p, _ in model.supplier_parts(target["id"], active_only=False)]}
    concentration = scenarios.concentration(model)
    mapping = scenarios.part_supplier_mapping(model)
    single = [{"part": r["part"], "suppliers": r["suppliers"], "class": r["class"]} for r in mapping if r["single_source"]]
    return {
        **{k: rounded(concentration[k], 3) for k in ("suppliers_active", "suppliers_referenced", "countries", "top3_share", "non_eu_share", "single_source_parts", "single_source_spend", "total_spend")},
        "spend_by_country": [{"country": c, "annual_eur": round(v)} for c, v in concentration["by_country"]],
        "top_suppliers": [{k: rounded(r[k], 3) for k in ("supplier", "country", "active_parts", "spend_annual", "spend_share", "sole_source_parts", "rating")} for r in scenarios.supplier_table(model)[:6]],
        "single_source_list": single,
        "sources": [model.source_ref(r["part_id"], "sourcing") for r in mapping if r["single_source"]],
    }


def supplier_exit(model, supplier):
    result = scenarios.supplier_exit(model, resolve_supplier(model, supplier)["id"])
    keys = ("supplier", "country", "rating", "parts", "no_alternative", "spend_annual", "delta_annual", "one_off", "max_delay_weeks", "weeks_to_sop", "late_parts")
    return {
        **{k: rounded(result[k]) for k in keys},
        "rows": [{k: rounded(r[k]) for k in ("part", "share_lost_pct", "alternative", "status", "capacity_coverage", "delay_weeks", "before_sop", "delta_annual", "one_off", "no_alternative")} for r in result["rows"]],
        "sources": result["sources"],
    }


def supplier_switch(model, part, supplier, share_pct=100):
    node = resolve_node(model, part)
    result = scenarios.supplier_switch(model, node.part_id, resolve_supplier(model, supplier)["id"], int(share_pct))
    if "error" in result:
        raise ToolError(result["error"])
    keys = ("part", "share_pct", "from", "to", "price_before", "price_after", "purchase_delta_annual", "extra_lead_days", "extra_inventory", "carrying_cost_annual", "annual_delta",
            "switching_cost", "tests_cost", "one_off", "payback_months", "delay_weeks", "weeks_to_sop", "qualified_before", "qualified_after", "capacity_ok", "remarks", "resilience", "impacted_interfaces", "impacted_assemblies")
    return {**{k: rounded(result[k]) for k in keys}, "tests": [t["test"] for t in result["tests"]], "sources": result["sources"]}


def release_check(model, target="RELEASED"):
    target = target.upper()
    if target not in MATURITY_RANK:
        raise ToolError("Maturité cible attendue : FROZEN ou RELEASED.")
    result = scenarios.release_readiness(model, target)
    pending = [r for r in result["rows"] if not r["ready"]]
    return {
        **{k: rounded(result[k], 3) for k in ("target", "gate", "go", "ready", "total", "ready_pct", "ready_mass_pct", "ready_cost_pct", "earliest_date", "late_days", "statuses", "corrections", "excluded")},
        "not_ready": [{k: r[k] for k in ("part", "plm_id", "status", "maturity", "date", "owner", "issues")} for r in pending],
        "assemblies": [{k: a[k] for k in ("assembly", "maturity", "ready", "total", "ahead_of_children", "lowest_child")} for a in result["assemblies"]],
        "promotion_steps": result["promotion_steps"],
        "sources": result["sources"],
    }


def mass_optimization(model, target_saving_kg=None, perimeter=None, allow_low_feasibility=False):
    node = resolve_node(model, perimeter) if perimeter else model.tree
    if not node.is_assembly:
        node = node.parent
    plan = scenarios.mass_plan(model, node.id, float(target_saving_kg) if target_saving_kg else None, "LOW" if allow_low_feasibility else "MEDIUM")
    pareto = scenarios.mass_pareto(model, node.id)
    fields = ("part", "plm_id", "label", "kind", "material_after", "delta_mass", "delta_cost", "eur_per_kg", "delta_co2", "one_off", "weeks", "feasibility_label", "space", "risk")
    return {
        "perimeter": plan["perimeter"],
        "mass_kg": rounded(plan["perimeter_mass"], 3),
        "target_saving_kg": rounded(plan["target_saving_kg"]),
        "reached": plan["reached"],
        "heaviest_parts": [{k: rounded(r[k], 3) for k in ("part", "material", "mass_kg", "share", "cumulated_share")} for r in pareto["rows"][:8]],
        "plan": [{k: rounded(o[k]) for k in fields} for o in plan["chosen"]],
        "summary": {k: rounded(v) for k, v in plan["summary"].items()},
        "options_available": len(plan["options"]),
        "lightweight_value_eur_kg": model.program["lightweight_value_eur_kg"],
        "hypothesis": "Plan glouton : options triées par coût du kg gagné, une option par pièce, faisabilité au moins moyenne, délai compatible avec le démarrage série.",
        "sources": plan["sources"] + [model.source_ref(r["part_id"], "masse, matériau") for r in pareto["rows"][:8]],
    }


def indicators(model):
    kpis = scenarios.product_kpis(model)
    return {**{k: rounded(v, 3) for k, v in kpis.items()},
            "program": {k: model.program[k] for k in ("annual_volume", "sop_date", "release_gate_date", "mass_target_kg")},
            "sources": [model.source_ref(model.tree.product, "structure, masse")]}


def scenario_catalog(model):
    return {"scenarios": [{k: s.get(k) for k in ("id", "kind", "title", "narrative")} for s in model.scenarios.values()], "sources": []}
