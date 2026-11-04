"""Moteurs de calcul : criticité et 5 scénarios. Fonctions pures, partagées par l'interface et le chatbot.

Chaque résultat porte une clé "sources" : les éléments PLM réellement utilisés pour le calcul.
"""
from datetime import date
from math import ceil

from plm.fmt import eur
from plm.model import CLAUSE_LABELS, FEASIBILITY_LABELS, FEASIBILITY_RANK, MATURITY_RANK, QUALIFICATION_LABELS, QUALIFIED

LEVELS = (("Critique", 70), ("Élevé", 45), ("Modéré", 25), ("Faible", 0))
UNKNOWN_SOURCING_WEEKS = 52  # délai d'un nouveau sourcing quand aucune alternative n'est référencée


def supplier_name(model, supplier_id):
    return model.suppliers[supplier_id]["name"]


def blocked_chain(model, part_id):
    chains = []
    for node in model.nodes_by_part[part_id]:
        chains.append(" › ".join(step.label for step in node.path()))
    return chains


# ---------------------------------------------------------------- Criticité


CRITERIA = [
    dict(key="sources", label="Sources qualifiées", max=35, scale="Aucune source qualifiée ou aucun fournisseur : 35. Une seule : 30 sans alternative référencée, 25 sinon. Deux : 8. Trois ou plus : 2."),
    dict(key="replacement", label="Remplacement", max=15, scale="Deux sources qualifiées ou plus : 2. Sinon, aucune alternative en cours : 15. Alternative prête en 26 semaines ou plus : 12, en 12 à 25 semaines : 8, en moins de 12 semaines : 4."),
    dict(key="lead_time", label="Délai de livraison", max=10, scale="60 jours ou plus : 10. De 30 à 59 jours : 6. Moins de 30 jours : 2. Fournisseur inconnu : 6."),
    dict(key="origin", label="Origine", max=10, scale="Risque géographique faible : 0. Moyen (Turquie, Serbie, Maroc, Inde, Taïwan) : 6. Élevé (Chine) : 10. Fournisseur inconnu : 6."),
    dict(key="finance", label="Santé financière", max=10, scale="Notation A : 0. B : 4. C : 10. Fournisseur inconnu : 4."),
    dict(key="class", label="Classe fonctionnelle", max=10, scale="A (vitale) : 10. B : 5. C (standard) : 1."),
    dict(key="interfaces", label="Interdépendances", max=5, scale="5 interfaces ou plus : 5. 3 ou 4 : 3. Moins : 1."),
    dict(key="cost", label="Poids dans le coût", max=5, scale="5 % ou plus de la nomenclature : 5. De 2 à 5 % : 3. Moins : 1."),
]
TECHNICAL_CRITERION = dict(key="technical", label="Changement technique", max=15, scale="Analyse d'impacts uniquement. Option d'allègement à faisabilité moyenne : 5, faible : 10. Magnésium : 5 de plus.")


def criticality(model):
    """Score de risque sur 100 : somme de 8 critères, détaillée dans "breakdown".
    Une pièce de classe A ou B avec au plus un fournisseur qualifié est toujours « Critique »."""
    total_cost = model.bom_cost()
    rows = []
    for part in model.physical_parts:
        part_id = part["xml_id"]
        links = part["sourcing"]
        qualified = model.qualified_links(part)
        klass = part.get("criticality", "C")
        commodity = 0.5 if klass == "C" else 1  # une pièce standard se requalifie vite ailleurs
        reasons = []
        points = {}
        details = {}

        def add(key, value, detail):
            points[key] = value
            details[key] = detail

        if not links:
            add("sources", 35, "Aucun fournisseur désigné")
            reasons.append("Aucun fournisseur désigné")
        elif not qualified:
            add("sources", 35, f"Aucune source qualifiée sur {len(links)} référencée(s)")
            reasons.append("Aucune source qualifiée")
        elif len(qualified) == 1:
            add("sources", (30 if len(links) == 1 else 25) * commodity, f"1 source qualifiée sur {len(links)} référencée(s)" + (", points divisés par 2 (classe C)" if commodity < 1 else ""))
            reasons.append("Un seul fournisseur qualifié" + ("" if len(links) > 1 else ", aucune alternative référencée"))
        elif len(qualified) == 2:
            add("sources", 8, "2 sources qualifiées")
        else:
            add("sources", 2, f"{len(qualified)} sources qualifiées")

        alternatives = [l["requal_weeks"] + l["ramp_up_weeks"] for l in links if l["qualification"] not in QUALIFIED]
        if qualified and len(qualified) > 1:
            add("replacement", 2, "Une autre source qualifiée prend le relais")
        elif not alternatives:
            add("replacement", 15 * commodity, "Aucune alternative en cours" + (", points divisés par 2 (classe C)" if commodity < 1 else ""))
        else:
            fastest = min(alternatives)
            add("replacement", 12 if fastest >= 26 else 8 if fastest >= 12 else 4, f"Alternative prête en {fastest} semaines au mieux")
            reasons.append(f"Alternative disponible en {fastest} semaines au mieux")

        primary = model.primary_link(part)
        if primary:
            supplier = model.suppliers[primary["supplier"]]
            lead = primary["lead_time_days"]
            add("lead_time", 10 if lead >= 60 else 6 if lead >= 30 else 2, f"{lead} jours chez {supplier['name']}")
            if lead >= 60:
                reasons.append(f"Délai long : {lead} jours")
            add("origin", {1: 0, 2: 6, 3: 10}[supplier["geo_risk"]], supplier["country_name"])
            if supplier["geo_risk"] >= 2:
                reasons.append(f"Origine exposée : {supplier['country_name']}")
            add("finance", {"A": 0, "B": 4, "C": 10}[supplier["financial_rating"]], f"Notation {supplier['financial_rating']}")
            if supplier["financial_rating"] == "C":
                reasons.append(f"Santé financière fragile : {supplier['name']} noté C")
        else:
            add("lead_time", 6, "Inconnu : aucun fournisseur actif")
            add("origin", 6, "Inconnue : aucun fournisseur actif")
            add("finance", 4, "Inconnue : aucun fournisseur actif")

        add("class", {"A": 10, "B": 5, "C": 1}[klass], f"Classe {klass}")
        if klass == "A":
            reasons.append("Fonction vitale (classe A)")

        interfaces = len(model.real_interfaces(part_id))
        add("interfaces", 5 if interfaces >= 5 else 3 if interfaces >= 3 else 1, f"{interfaces} interface(s)")
        if interfaces >= 5:
            reasons.append(f"{interfaces} interdépendances")

        cost_share = model.line_cost(part) / total_cost
        add("cost", 5 if cost_share >= 0.05 else 3 if cost_share >= 0.02 else 1, f"{cost_share:.1%} de la nomenclature".replace(".", ","))
        if cost_share >= 0.05:
            reasons.append(f"{cost_share:.0%} du coût de la nomenclature")

        technical = part.get("technical_risk", 0)
        if technical:
            add("technical", technical, "Option d'allègement non éprouvée")
            reasons.append("Changement technique en cours")

        score = min(round(sum(points.values())), 100)
        level = next(name for name, threshold in LEVELS if score >= threshold)
        single_source = model.is_single_source(part)
        level_reason = f"Score de {score}"
        if single_source and klass in ("A", "B"):
            if level != "Critique":
                level_reason = f"Score de {score}, relevé à Critique : classe {klass} avec au plus un fournisseur qualifié"
            level = "Critique"
        elif single_source and level in ("Faible", "Modéré"):
            level_reason = f"Score de {score}, relevé à Élevé : au plus un fournisseur qualifié"
            level = "Élevé"

        all_criteria = CRITERIA + ([TECHNICAL_CRITERION] if technical else [])
        breakdown = [{"key": c["key"], "label": c["label"], "max": c["max"], "points": points[c["key"]], "detail": details[c["key"]]} for c in all_criteria]
        countries = sorted({model.suppliers[l["supplier"]]["country_name"] for l in model.active_links(part)})
        rows.append({
            "part_id": part_id,
            "plm_id": part["plm_id"],
            "name": model.node_label(part_id),
            "plm_name": part["name"],
            "score": score,
            "level": level,
            "level_reason": level_reason,
            "reasons": reasons,
            "breakdown": breakdown,
            "sources_referenced": len(links),
            "sources_qualified": len(qualified),
            "single_source": single_source,
            "origin": ", ".join(countries) or "Non désignée",
            "interfaces": interfaces,
            "mass_kg": part["mass_kg"] * model.quantity(part_id),
            "volume_l": (model.volume_litres(part) or 0) * model.quantity(part_id),
            "envelope_mm": part.get("envelope_mm", ""),
            "quantity": model.quantity(part_id),
            "unit_cost": model.unit_cost(part)[0],
            "line_cost": model.line_cost(part),
            "cost_share": cost_share,
            "lead_time_days": primary["lead_time_days"] if primary else None,
            "class": klass,
            "subassembly": model.nodes_by_part[part_id][0].top_level().label,
        })
    return sorted(rows, key=lambda r: -r["score"])


# ---------------------------------------------------------------- Scénario 1 : rupture d'approvisionnement

STRATEGIES = {
    "wait": dict(label="Attendre la reprise", flex=False, candidates=False, emergency=False,
                 description="Aucune action : les autres fournisseurs gardent leur part habituelle."),
    "reallocate": dict(label="Réallouer et activer les sources", flex=True, candidates=True, emergency=False,
                       description="Les sources actives montent à leur capacité, les candidates suivent leur PPAP au rythme normal."),
    "emergency": dict(label="Plan d'urgence", flex=True, candidates=True, emergency=True,
                      description="PPAP accéléré de 40 % (coût 1,5 fois plus élevé), fret aérien pour les origines lointaines."),
}


def run_strategy(model, part, disrupted, duration, horizon, strategy):
    program = model.program
    settings = STRATEGIES[strategy]
    emergency = settings["emergency"]
    quantity = model.quantity(part["xml_id"])
    weekly = program["weekly_demand"]
    working_days = program["working_days_per_week"]
    demand = weekly * quantity
    average_price = model.unit_cost(part)[0]
    links = part["sourcing"]

    target_stock = part.get("safety_stock_days", 0) / working_days * demand
    in_transit = demand * disrupted["share_pct"] / 100 * disrupted["transit_days"] / 7
    stock = target_stock + in_transit
    finished_goods = program["finished_goods_days"] * weekly / working_days

    def by_air(link):
        return emergency and link["transit_days"] > 14

    def lag(link):
        return 1 if by_air(link) else ceil(link["transit_days"] / 7)

    def flow(link, week):
        base = demand * link["share_pct"] / 100
        if link is disrupted:
            restart = duration + lag(link)
            if week <= restart:
                return 0
            nominal = base or link["capacity_per_week"]
            return nominal * 0.5 if week <= restart + 2 else nominal
        if link["share_pct"] > 0:
            if not settings["flex"]:
                return base
            ramp = max(1, link["ramp_up_weeks"] - 1) if emergency else link["ramp_up_weeks"]
            return max(base, link["capacity_per_week"]) if week > ramp + lag(link) else base
        if not settings["candidates"]:
            return 0
        requal = max(2, ceil(link["requal_weeks"] * 0.6)) if emergency else link["requal_weeks"]
        ramp = max(1, link["ramp_up_weeks"] - 1) if emergency else link["ramp_up_weeks"]
        return link["capacity_per_week"] if week > requal + ramp + lag(link) else 0

    # À besoin égal, le fournisseur habituel passe d'abord, puis les sources actives, puis les candidates.
    order = sorted(links, key=lambda l: (l is not disrupted, -l["share_pct"], l.get("unit_price_eur", 0)))
    series = []
    lost_total = extra_purchase = air_freight = 0.0
    used_candidates = set()
    for week in range(1, horizon + 1):
        need = demand + min(0.15 * demand, max(0.0, target_stock - stock))
        received = 0.0
        volumes = {}
        for link in order:
            volume = min(flow(link, week), need - received)
            if volume <= 0:
                continue
            received += volume
            volumes[link["supplier"]] = volume
            price = link.get("unit_price_eur", average_price)
            extra_purchase += volume * (price - average_price)
            if by_air(link):
                air_freight += volume * part["mass_kg"] * program["air_freight_eur_kg"]
            if link["share_pct"] == 0:
                used_candidates.add(link["supplier"])
        available = stock + received
        produced = int(min(available, demand) // quantity)
        stock = available - produced * quantity
        shortfall = weekly - produced
        buffered = min(finished_goods, shortfall)
        finished_goods -= buffered
        lost = shortfall - buffered
        lost_total += lost
        series.append({"week": week, "produced": produced, "delivered": weekly - lost, "lost": lost,
                       "stock_weeks": stock / demand, "received": received, "volumes": volumes})

    stopped = [row["week"] for row in series if row["lost"] > 0]
    stop_days = lost_total / (weekly / working_days)
    margin_lost = lost_total * model.margin_per_unit()
    penalty = stop_days * program["line_stop_penalty_eur_day"]
    one_off = sum(l["switching_cost_eur"] for l in links if l["supplier"] in used_candidates) * (1.5 if emergency else 1)
    extra_purchase = max(extra_purchase, 0.0)
    return {
        "strategy": strategy,
        "label": settings["label"],
        "description": settings["description"],
        "series": series,
        "lost_units": lost_total,
        "stop_days": stop_days,
        "first_stop_week": stopped[0] if stopped else None,
        "last_stop_week": stopped[-1] if stopped else None,
        "margin_lost": margin_lost,
        "penalty": penalty,
        "extra_purchase": extra_purchase,
        "air_freight": air_freight,
        "one_off": one_off,
        "total_cost": margin_lost + penalty + extra_purchase + air_freight + one_off,
        "candidates_used": [supplier_name(model, s) for s in used_candidates],
    }


def simulate_disruption(model, part_id, supplier_id=None, duration_weeks=8, horizon_weeks=36):
    part = model.products[part_id]
    links = part["sourcing"]
    if not links:
        return {"error": f"{part['name']} n'a aucun fournisseur désigné : la rupture ne peut pas être simulée.", "sources": [model.source_ref(part, "sourcing")]}
    if supplier_id:
        disrupted = next((l for l in links if l["supplier"] == supplier_id), None)
        if disrupted is None:
            return {"error": f"{supplier_name(model, supplier_id)} ne fournit pas {part['name']}.", "sources": [model.source_ref(part, "sourcing")]}
    else:
        disrupted = model.primary_link(part)

    results = {name: run_strategy(model, part, disrupted, duration_weeks, horizon_weeks, name) for name in STRATEGIES}
    best = min(results.values(), key=lambda r: r["total_cost"])

    program = model.program
    demand = program["weekly_demand"] * model.quantity(part_id)
    others = sum(demand * l["share_pct"] / 100 for l in links if l is not disrupted)
    deficit = demand - others
    in_transit = demand * disrupted["share_pct"] / 100 * disrupted["transit_days"] / 7
    plant_stock = part.get("safety_stock_days", 0) / program["working_days_per_week"] * demand
    finished_goods_parts = program["finished_goods_days"] / program["working_days_per_week"] * demand
    cover_days = None
    if deficit > 0:
        cover_days = (plant_stock + in_transit + finished_goods_parts) / deficit * program["working_days_per_week"]

    alternatives = []
    for link in links:
        if link is disrupted:
            continue
        supplier = model.suppliers[link["supplier"]]
        lag = ceil(link["transit_days"] / 7)
        normal = link["requal_weeks"] + link["ramp_up_weeks"] + lag
        fast = max(2, ceil(link["requal_weeks"] * 0.6)) + max(1, link["ramp_up_weeks"] - 1) + (1 if link["transit_days"] > 14 else lag)
        alternatives.append({
            "supplier": supplier["name"], "country": supplier["country_name"], "status": QUALIFICATION_LABELS[link["qualification"]],
            "share_pct": link["share_pct"], "capacity": link["capacity_per_week"], "coverage": link["capacity_per_week"] / demand,
            "price": link.get("unit_price_eur"), "delay_weeks": normal, "delay_emergency_weeks": fast,
            "switching_cost": link["switching_cost_eur"],
        })

    exposed = []
    for other, link in model.supplier_parts(disrupted["supplier"]):
        if other["xml_id"] == part_id:
            continue
        cover = other.get("safety_stock_days", 0) + link["transit_days"] * program["working_days_per_week"] / 7
        exposed.append({"part_id": other["xml_id"], "part": model.node_label(other["xml_id"]), "share_pct": link["share_pct"], "cover_days": cover,
                        "single_source": model.is_single_source(other)})

    recommendations = []
    wait = results["wait"]
    if best["strategy"] != "wait" and wait["total_cost"] - best["total_cost"] > 1:
        recommendations.append(f"Stratégie la moins coûteuse : {best['label'].lower()}, soit {eur(wait['total_cost'] - best['total_cost'])} de moins que l'attente.")
    elif wait["lost_units"] == 0:
        recommendations.append("Le stock et le transit absorbent l'arrêt : aucune unité perdue, surveiller la reprise.")
    else:
        recommendations.append("Aucune source alternative n'arrive à temps pour réduire la perte.")
    candidates = [l for l in links if l is not disrupted and l["share_pct"] == 0 and l["qualification"] not in QUALIFIED]
    if candidates and wait["total_cost"] > 0:
        cheapest = min(candidates, key=lambda l: l["switching_cost_eur"])
        ratio = wait["total_cost"] / max(cheapest["switching_cost_eur"], 1)
        recommendations.append(
            f"Finir la qualification de {supplier_name(model, cheapest['supplier'])} avant le démarrage série : "
            f"{eur(cheapest['switching_cost_eur'])}, soit {ratio:.0f} fois moins que l'exposition de ce scénario.")
    elif not [l for l in links if l is not disrupted]:
        recommendations.append("Aucune alternative référencée : lancer un sourcing maintenant, compter environ 12 mois.")
    if exposed:
        recommendations.append(f"{len(exposed)} autre(s) pièce(s) chez ce fournisseur seraient touchées si tout le site s'arrête.")

    sources = [model.source_ref(part, "structure, masse, stock, sourcing"), model.supplier_ref(disrupted["supplier"], "capacité, délai, transit")]
    sources += [model.supplier_ref(l["supplier"], "capacité, PPAP, prix") for l in links if l is not disrupted]
    return {
        "part_id": part_id,
        "part": model.node_label(part_id),
        "quantity": model.quantity(part_id),
        "supplier_id": disrupted["supplier"],
        "supplier": supplier_name(model, disrupted["supplier"]),
        "share_lost_pct": disrupted["share_pct"],
        "duration_weeks": duration_weeks,
        "weekly_demand_units": program["weekly_demand"],
        "plant_stock_days": part.get("safety_stock_days", 0),
        "transit_days": disrupted["transit_days"],
        "cover_days": cover_days,
        "blocked_chains": blocked_chain(model, part_id),
        "interfaces": len(model.real_interfaces(part_id)),
        "strategies": results,
        "best": best["strategy"],
        "alternatives": alternatives,
        "exposed_parts": exposed,
        "recommendations": recommendations,
        "margin_per_unit": model.margin_per_unit(),
        "sources": sources,
    }


# ---------------------------------------------------------------- Scénario 2 : prix des matières


def months_until(model, iso_date):
    end = date.fromisoformat(iso_date)
    start = model.reference_date
    return (end.year - start.year) * 12 + end.month - start.month


def effect_month(model, link):
    """Mois (à partir de la date de référence) où une variation d'indice atteint le prix de ce fournisseur."""
    clause = link["price_clause"]
    if clause == "INDEX_M":
        return 1
    if clause == "INDEX_Q":
        return 3
    if link.get("contract_end"):
        return max(1, months_until(model, link["contract_end"]) + 1)
    return 1


def material_price_impact(model, family=None, material=None, pct=10):
    """Effet d'une variation de l'indice matière. Seule la part indexée du prix matière bouge, pas la conversion."""
    rows = []
    monthly_delta = [0.0] * 12
    for part in model.physical_parts:
        info = model.material_of(part)
        if not info or not part.get("usage_kg"):
            continue
        if (family and info["family"] != family) or (material and info["plm_name"] != material):
            continue
        part_id = part["xml_id"]
        quantity = model.quantity(part_id)
        delta_part = part["usage_kg"] * info["price_eur_kg"] * info["index_share"] * pct / 100
        links = model.active_links(part)
        months = []
        total_share = sum(l["share_pct"] for l in links) or 1
        clauses = []
        if links:
            for link in links:
                month = effect_month(model, link)
                months.append(month)
                clauses.append(CLAUSE_LABELS[link["price_clause"]])
                for index in range(12):
                    if index + 1 >= month:
                        monthly_delta[index] += delta_part * quantity * link["share_pct"] / total_share
        else:
            months.append(1)
            clauses.append("Sans contrat")
            for index in range(12):
                monthly_delta[index] += delta_part * quantity
        unit_cost = model.unit_cost(part)[0]
        rows.append({
            "part_id": part_id,
            "plm_id": part["plm_id"],
            "part": model.node_label(part_id),
            "material": info["plm_name"],
            "quantity": quantity,
            "usage_kg": part["usage_kg"],
            "price_before": info["price_eur_kg"],
            "price_after": info["price_eur_kg"] * (1 + info["index_share"] * pct / 100),
            "unit_cost": unit_cost,
            "delta_part": delta_part,
            "delta_pct_part": delta_part / unit_cost if unit_cost else 0,
            "delta_unit": delta_part * quantity,
            "delta_annual": delta_part * quantity * model.program["annual_volume"],
            "first_month": min(months),
            "last_month": max(months),
            "clauses": ", ".join(sorted(set(clauses))),
        })
    rows.sort(key=lambda r: -abs(r["delta_unit"]))

    annual_volume = model.program["annual_volume"]
    delta_unit = sum(r["delta_unit"] for r in rows)
    bom_before = model.bom_cost()
    bom_after = bom_before + delta_unit
    price = model.program["selling_price_eur"]
    monthly_volume = annual_volume / 12
    timeline = []
    cumulated = 0.0
    for index, value in enumerate(monthly_delta):
        cumulated += value * monthly_volume
        timeline.append({"month": index + 1, "delta_unit": value, "cost": value * monthly_volume, "cumulated": cumulated})
    immediate = monthly_delta[2] / delta_unit if delta_unit else 0
    sources = [model.source_ref(p["part_id"], "masse, matériau, usage matière, clause de prix") for p in rows]
    return {
        "family": family,
        "material": material,
        "pct": pct,
        "rows": rows,
        "parts": len(rows),
        "mass_kg": sum(model.products[r["part_id"]]["mass_kg"] * r["quantity"] for r in rows),
        "delta_unit": delta_unit,
        "delta_annual": delta_unit * annual_volume,
        "bom_before": bom_before,
        "bom_after": bom_after,
        "margin_before": model.margin_per_unit(bom_before),
        "margin_after": model.margin_per_unit(bom_after),
        "margin_pct_before": model.margin_per_unit(bom_before) / price,
        "margin_pct_after": model.margin_per_unit(bom_after) / price,
        "timeline": timeline,
        "first_12_months": cumulated,
        "share_within_3_months": immediate,
        "sources": sources,
    }


def family_sensitivity(model, pct=10):
    rows = []
    for family in sorted({m["family"] for m in model.materials.values() if m["in_bom"]}):
        impact = material_price_impact(model, family=family, pct=pct)
        spend = sum(model.material_cost(model.products[r["part_id"]]) * r["quantity"] for r in impact["rows"])
        rows.append({"family": family, "delta_unit": impact["delta_unit"], "delta_annual": impact["delta_annual"], "mass_kg": impact["mass_kg"], "material_cost": spend, "parts": impact["parts"]})
    return sorted(rows, key=lambda r: -r["delta_annual"])


# ---------------------------------------------------------------- Scénario 3 : fournisseurs


def supplier_table(model):
    total = model.bom_cost()
    rows = []
    for supplier_id, supplier in model.suppliers.items():
        active = model.supplier_parts(supplier_id)
        candidates = [item for item in model.supplier_parts(supplier_id, active_only=False) if item[1]["share_pct"] == 0]
        spend_unit = sum(model.quantity(p["xml_id"]) * l.get("unit_price_eur", model.unit_cost(p)[0]) * l["share_pct"] / 100 for p, l in active)
        sole = [p for p, l in active if model.is_single_source(p)]
        rows.append({
            "supplier_id": supplier_id,
            "supplier": supplier["name"],
            "country": supplier["country_name"],
            "city": supplier["city"],
            "lat": supplier["lat"],
            "lon": supplier["lon"],
            "region": supplier["region"],
            "speciality": supplier["speciality"],
            "active_parts": len(active),
            "candidate_parts": len(candidates),
            "spend_unit": spend_unit,
            "spend_annual": spend_unit * model.program["annual_volume"],
            "spend_share": spend_unit / total,
            "sole_source_parts": len(sole),
            "sole_source_names": ", ".join(model.node_label(p["xml_id"]) for p in sole),
            "rating": supplier["financial_rating"],
            "ppm": supplier["quality_ppm"],
            "otd": supplier["otd_pct"],
            "geo_risk": supplier["geo_risk"],
        })
    return sorted(rows, key=lambda r: -r["spend_annual"])


def part_supplier_mapping(model):
    rows = []
    for part in model.physical_parts:
        part_id = part["xml_id"]
        links = sorted(part["sourcing"], key=lambda l: -l["share_pct"])
        parts_text = []
        for link in links:
            supplier = model.suppliers[link["supplier"]]
            status = f"{link['share_pct']} %" if link["share_pct"] else QUALIFICATION_LABELS[link["qualification"]].lower()
            parts_text.append(f"{supplier['name']} ({supplier['country']}, {status})")
        rows.append({
            "part_id": part_id,
            "part": model.node_label(part_id),
            "subassembly": model.nodes_by_part[part_id][0].top_level().label,
            "suppliers": " · ".join(parts_text) or "Aucun fournisseur désigné",
            "referenced": len(links),
            "qualified": len(model.qualified_links(part)),
            "single_source": model.is_single_source(part),
            "annual_spend": model.annual_spend(part),
            "class": part.get("criticality"),
        })
    return sorted(rows, key=lambda r: (r["qualified"], -r["annual_spend"]))


def concentration(model):
    table = supplier_table(model)
    active = [r for r in table if r["active_parts"]]
    hhi = sum((r["spend_share"] * 100) ** 2 for r in active)
    by_country = {}
    by_region = {}
    for row in active:
        by_country[row["country"]] = by_country.get(row["country"], 0) + row["spend_annual"]
        by_region[row["region"]] = by_region.get(row["region"], 0) + row["spend_annual"]
    total = sum(by_country.values())
    top3 = sum(r["spend_share"] for r in active[:3])
    single = [p for p in model.physical_parts if p["sourcing"] and model.is_single_source(p)]
    return {
        "suppliers_active": len(active),
        "suppliers_referenced": len(table),
        "countries": len(by_country),
        "hhi": hhi,
        "top3_share": top3,
        "by_country": sorted(by_country.items(), key=lambda item: -item[1]),
        "by_region": sorted(by_region.items(), key=lambda item: -item[1]),
        "non_eu_share": 1 - by_region.get("UE", 0) / total,
        "single_source_parts": len(single),
        "single_source_spend": sum(model.annual_spend(p) for p in single),
        "total_spend": total,
    }


def supplier_exit(model, supplier_id):
    """Que devient chaque pièce si ce fournisseur disparaît ?"""
    supplier = model.suppliers[supplier_id]
    weeks_left = model.weeks_to_sop
    rows = []
    for part, link in model.supplier_parts(supplier_id):
        part_id = part["xml_id"]
        quantity = model.quantity(part_id)
        demand = model.program["weekly_demand"] * quantity
        alternatives = [l for l in part["sourcing"] if l["supplier"] != supplier_id]
        active = [l for l in alternatives if l["share_pct"] > 0 and l["qualification"] in QUALIFIED]
        others = sorted([l for l in alternatives if l not in active], key=lambda l: l["requal_weeks"] + l["ramp_up_weeks"])
        chosen = active + others
        capacity = 0
        selected = []
        for alternative in chosen:
            selected.append(alternative)
            capacity += alternative["capacity_per_week"]
            if capacity >= demand:
                break
        lost_share = link["share_pct"] / 100
        if selected:
            best = selected[0]
            delay = max(l["requal_weeks"] + l["ramp_up_weeks"] + ceil(l["transit_days"] / 7) for l in selected)
            one_off = sum(l["switching_cost_eur"] for l in selected)
            weighted_price = sum(l.get("unit_price_eur", 0) * l["capacity_per_week"] for l in selected) / max(capacity, 1)
            delta_part = (weighted_price - link.get("unit_price_eur", weighted_price)) * lost_share
            names = ", ".join(supplier_name(model, l["supplier"]) for l in selected)
            status = QUALIFICATION_LABELS[best["qualification"]]
        else:
            delay = UNKNOWN_SOURCING_WEEKS
            one_off = 0
            delta_part = 0
            names = "Aucune alternative référencée"
            status = "Sourcing à lancer"
        rows.append({
            "part_id": part_id,
            "part": model.node_label(part_id),
            "share_lost_pct": link["share_pct"],
            "alternative": names,
            "status": status,
            "capacity_coverage": capacity / demand if demand else 0,
            "delay_weeks": delay,
            "before_sop": delay <= weeks_left,
            "delta_unit": delta_part * quantity,
            "delta_annual": delta_part * quantity * model.program["annual_volume"],
            "one_off": one_off,
            "no_alternative": not selected,
            "annual_spend": model.annual_spend(part),
        })
    rows.sort(key=lambda r: (not r["no_alternative"], -r["delay_weeks"]))
    sources = [model.supplier_ref(supplier_id, "notation, sourcing")] + [model.source_ref(r["part_id"], "sourcing, capacités, PPAP") for r in rows]
    return {
        "supplier_id": supplier_id,
        "supplier": supplier["name"],
        "country": supplier["country_name"],
        "rating": supplier["financial_rating"],
        "rows": rows,
        "parts": len(rows),
        "no_alternative": sum(r["no_alternative"] for r in rows),
        "spend_annual": sum(r["annual_spend"] * r["share_lost_pct"] / 100 for r in rows),
        "delta_annual": sum(r["delta_annual"] for r in rows),
        "one_off": sum(r["one_off"] for r in rows),
        "max_delay_weeks": max((r["delay_weeks"] for r in rows), default=0),
        "weeks_to_sop": weeks_left,
        "late_parts": sum(not r["before_sop"] for r in rows),
        "sources": sources,
    }


def double_source_resilience(model, part, primary, target, share_pct, duration_weeks=16, horizon_weeks=36):
    """Coût d'un arrêt du fournisseur principal avec et sans la seconde source, en réallouant les volumes."""
    before = run_strategy(model, part, primary, duration_weeks, horizon_weeks, "reallocate")
    new_primary = {**primary, "share_pct": 100 - share_pct}
    new_target = {**target, "share_pct": share_pct, "qualification": "APPROVED", "requal_weeks": 0}
    others = [l for l in part["sourcing"] if l is not primary and l is not target]
    changed = {**part, "sourcing": [new_primary, new_target, *others]}
    after = run_strategy(model, changed, new_primary, duration_weeks, horizon_weeks, "reallocate")
    return {"duration_weeks": duration_weeks, "cost_before": before["total_cost"], "cost_after": after["total_cost"],
            "lost_before": before["lost_units"], "lost_after": after["lost_units"]}


def supplier_switch(model, part_id, to_supplier, share_pct=100):
    """Changer de fournisseur (share_pct = 100) ou ajouter une seconde source (share_pct < 100)."""
    part = model.products[part_id]
    primary = model.primary_link(part)
    target = next((l for l in part["sourcing"] if l["supplier"] == to_supplier), None)
    if primary is None or target is None:
        return {"error": f"{supplier_name(model, to_supplier)} n'est pas référencé pour {part['name']}.", "sources": [model.source_ref(part, "sourcing")]}
    program = model.program
    quantity = model.quantity(part_id)
    annual_parts = quantity * program["annual_volume"]
    share = share_pct / 100
    price_before = model.unit_cost(part)[0]
    primary_price = primary.get("unit_price_eur", price_before)
    target_price = target.get("unit_price_eur", price_before)
    price_after = target_price * share + primary_price * (1 - share)
    purchase_delta = (price_after - price_before) * annual_parts

    extra_days = max(0, target["lead_time_days"] - primary["lead_time_days"]) * share
    daily_parts = annual_parts / (program["production_weeks"] * 7)
    extra_inventory = extra_days * daily_parts * target_price
    carrying_cost = extra_inventory * program["inventory_carrying_pct"] / 100

    tests = model.revalidation_tests(part_id)
    tests_cost = sum(t["cost_eur"] for t in tests) if target["qualification"] == "NOT_STARTED" else 0
    one_off = target["switching_cost_eur"] + tests_cost
    annual_delta = purchase_delta + carrying_cost
    payback = one_off / (-annual_delta / 12) if annual_delta < 0 else None
    delay = target["requal_weeks"] + target["ramp_up_weeks"] + ceil(target["transit_days"] / 7)
    from_supplier = model.suppliers[primary["supplier"]]
    to = model.suppliers[to_supplier]
    qualified_before = len(model.qualified_links(part))
    keeps_primary = share < 1
    qualified_after = qualified_before + (1 if target["qualification"] not in QUALIFIED else 0) - (0 if keeps_primary else 1)

    def side(link, supplier):
        return {"supplier": supplier["name"], "country": supplier["country_name"], "price": link.get("unit_price_eur"),
                "lead_time": link["lead_time_days"], "transit": link["transit_days"], "capacity": link["capacity_per_week"],
                "ppm": supplier["quality_ppm"], "otd": supplier["otd_pct"], "rating": supplier["financial_rating"],
                "geo_risk": supplier["geo_risk"], "status": QUALIFICATION_LABELS[link["qualification"]]}

    capacity_ok = target["capacity_per_week"] >= program["weekly_demand"] * quantity * share
    remarks = []
    if keeps_primary and qualified_after >= 2:
        remarks.append("La pièce n'est plus mono-source : un arrêt d'un fournisseur ne stoppe plus la ligne.")
    if not keeps_primary and qualified_after <= 1:
        remarks.append("La pièce reste mono-source après le changement : le risque est déplacé, pas réduit.")
    if not capacity_ok:
        remarks.append("Capacité insuffisante chez le nouveau fournisseur pour cette part de volume.")
    if delay > model.weeks_to_sop:
        remarks.append(f"Délai de {delay} semaines supérieur aux {model.weeks_to_sop:.0f} semaines restant avant le démarrage série.")
    if to["geo_risk"] > from_supplier["geo_risk"]:
        remarks.append(f"Risque géographique plus élevé : {to['country_name']}.")
    if to["quality_ppm"] > from_supplier["quality_ppm"] * 1.5:
        remarks.append(f"Qualité historique plus faible : {to['quality_ppm']} ppm contre {from_supplier['quality_ppm']} ppm.")
    if payback is not None:
        remarks.append(f"Retour sur investissement en {payback:.0f} mois.")
    elif annual_delta > 0:
        remarks.append(f"Surcoût annuel de {eur(annual_delta)} : c'est le prix de l'assurance.")

    resilience = double_source_resilience(model, part, primary, target, share_pct) if keeps_primary else None
    if resilience:
        remarks.append(f"Un arrêt de {resilience['duration_weeks']} semaines de {from_supplier['name']} coûterait {eur(resilience['cost_after'])} "
                       f"au lieu de {eur(resilience['cost_before'])}.")

    return {
        "part_id": part_id,
        "part": model.node_label(part_id),
        "share_pct": share_pct,
        "resilience": resilience,
        "from": side(primary, from_supplier),
        "to": side(target, to),
        "price_before": price_before,
        "price_after": price_after,
        "purchase_delta_annual": purchase_delta,
        "extra_lead_days": extra_days,
        "extra_inventory": extra_inventory,
        "carrying_cost_annual": carrying_cost,
        "annual_delta": annual_delta,
        "switching_cost": target["switching_cost_eur"],
        "tests": tests,
        "tests_cost": tests_cost,
        "one_off": one_off,
        "payback_months": payback,
        "delay_weeks": delay,
        "weeks_to_sop": model.weeks_to_sop,
        "qualified_before": qualified_before,
        "qualified_after": qualified_after,
        "capacity_ok": capacity_ok,
        "remarks": remarks,
        "impacted_interfaces": [{"part": model.node_label(i["other"]), "type": model.interface_types[i["type"]]["label"], "note": i["note"]} for i in model.real_interfaces(part_id)],
        "impacted_assemblies": blocked_chain(model, part_id),
        "sources": [model.source_ref(part, "prix, sourcing, interfaces"), model.supplier_ref(primary["supplier"], "prix, délai, qualité"), model.supplier_ref(to_supplier, "prix, délai, qualité, PPAP")],
    }


# ---------------------------------------------------------------- Scénario 4 : release


def part_release_status(model, part, target, gate):
    rank_target = MATURITY_RANK[target]
    nodes = model.nodes_by_part[part["xml_id"]]
    wrappers = [n.wrapper for n in nodes if n.wrapper]
    maturity = part["maturity"]
    maturity_ok = MATURITY_RANK[maturity] >= rank_target and all(MATURITY_RANK[w["maturity"]] >= rank_target for w in wrappers)
    links = model.active_links(part)
    ppap_ok = target != "RELEASED" or any(l["qualification"] == "APPROVED" for l in links)
    priced = any("unit_price_eur" in l for l in links)
    issues = []

    if not part.get("physical", True):
        return dict(status="À exclure", ready=False, in_scope=False, date=None, issues=["Géométrie d'étude : à retirer de la nomenclature de production."], maturity_ok=False, ppap_ok=False, data_ok=False)

    if maturity == "OBSOLETE":
        issues.append("Référence OBSOLETE à remplacer.")
    elif not maturity_ok:
        issues.append(f"Maturité {maturity}, {target} attendu.")
    if not links:
        issues.append("Aucun fournisseur désigné.")
    elif not ppap_ok:
        pending = [l for l in links if l.get("ppap_date")]
        when = max((l["ppap_date"] for l in pending), default="non planifié")
        issues.append(f"PPAP non approuvé (prévu le {when}).")
    if links and not priced:
        issues.append("Prix fournisseur manquant.")
    if part.get("blocking") and issues:
        issues.append(part["blocking"])

    planned = part.get("planned_release")
    ppap_dates = [l["ppap_date"] for l in links if l.get("ppap_date") and l["qualification"] != "APPROVED"] if target == "RELEASED" else []
    effective = max([d for d in [planned, *ppap_dates] if d], default=None)
    data_ok = bool(links) and priced

    if not issues:
        status = "Prêt"
    elif maturity == "OBSOLETE" or (not links and not planned):
        status = "Bloquant"
    elif effective and effective > gate:
        status = "En retard"
    else:
        status = "À promouvoir"
    return dict(status=status, ready=not issues, in_scope=True, date=effective, issues=issues, maturity_ok=maturity_ok, ppap_ok=ppap_ok, data_ok=data_ok)


def release_readiness(model, target="RELEASED", gate=None):
    gate = gate or model.program["release_gate_date"]
    rows = []
    for part in model.parts:
        part_id = part["xml_id"]
        check = part_release_status(model, part, target, gate)
        rows.append({
            "part_id": part_id,
            "plm_id": part["plm_id"],
            "part": model.node_label(part_id),
            "subassembly": model.nodes_by_part[part_id][0].top_level().label,
            "maturity": part["maturity"],
            "revision": part["revision"],
            "owner": part["owner"],
            "mass_kg": part["mass_kg"] * model.quantity(part_id),
            "cost": model.line_cost(part),
            **check,
        })
    order = {"Bloquant": 0, "En retard": 1, "À promouvoir": 2, "À exclure": 3, "Prêt": 4}
    rows.sort(key=lambda r: (order[r["status"]], r["date"] or "9999", -r["cost"]))
    scope = [r for r in rows if r["in_scope"]]
    ready = [r for r in scope if r["ready"]]

    assemblies = []
    for node in sorted((n for n in model.nodes.values() if n.is_assembly), key=lambda n: -n.depth):
        leaves = {leaf.part_id for leaf in node.leaves()}
        inside = [r for r in scope if r["part_id"] in leaves]
        done = [r for r in inside if r["ready"]]
        own_ok = MATURITY_RANK[node.product["maturity"]] >= MATURITY_RANK[target]
        lowest = min((model.products[r["part_id"]]["maturity"] for r in inside), key=MATURITY_RANK.get)
        assemblies.append({
            "part_id": node.part_id,
            "assembly": node.label,
            "depth": node.depth,
            "maturity": node.product["maturity"],
            "ready": len(done),
            "total": len(inside),
            "own_ok": own_ok,
            "ahead_of_children": MATURITY_RANK[node.product["maturity"]] > MATURITY_RANK[lowest] and node.product["maturity"] in ("FROZEN", "RELEASED"),
            "lowest_child": lowest,
        })

    dates = [r["date"] for r in scope if not r["ready"] and r["date"]]
    earliest = max(dates) if dates else gate
    blockers = [r for r in scope if r["status"] in ("Bloquant", "En retard")]
    late_days = (date.fromisoformat(earliest) - date.fromisoformat(gate)).days

    steps = []
    remaining = [r for r in scope if not r["ready"]]
    if remaining:
        steps.append({"step": "1. Pièces", "items": [r["part"] for r in sorted(remaining, key=lambda r: r["date"] or "9999")]})
    for depth, label in ((2, "2. Sous-ensembles"), (1, "3. Grands ensembles"), (0, "4. Produit")):
        items = [a["assembly"] for a in assemblies if a["depth"] == depth and not a["own_ok"]]
        if items:
            steps.append({"step": label, "items": items})
    corrections = [a["assembly"] for a in assemblies if a["ahead_of_children"]]

    counts = {}
    for row in rows:
        counts[row["maturity"]] = counts.get(row["maturity"], 0) + 1
    statuses = {}
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1

    total_mass = sum(r["mass_kg"] for r in scope)
    total_cost = sum(r["cost"] for r in scope)
    sources = [model.source_ref(r["part_id"], "maturité, PPAP, date prévue") for r in rows if not r["ready"]]
    return {
        "target": target,
        "gate": gate,
        "go": not remaining and not corrections,
        "ready": len(ready),
        "total": len(scope),
        "ready_pct": len(ready) / len(scope),
        "ready_mass_pct": sum(r["mass_kg"] for r in ready) / total_mass,
        "ready_cost_pct": sum(r["cost"] for r in ready) / total_cost,
        "rows": rows,
        "assemblies": assemblies,
        "statuses": statuses,
        "maturity_counts": counts,
        "blockers": blockers,
        "earliest_date": earliest,
        "late_days": late_days,
        "promotion_steps": steps,
        "corrections": corrections,
        "excluded": [r["part"] for r in rows if not r["in_scope"]],
        "sources": sources,
    }


# ---------------------------------------------------------------- Scénario 5 : masse


def perimeter_lines(model, perimeter_id):
    """Pièces du périmètre, regroupées : une pièce utilisée sous plusieurs lignes n'apparaît qu'une fois."""
    node = model.nodes[perimeter_id]
    lines = {}
    for leaf in node.leaves():
        line = lines.setdefault(leaf.part_id, {"part": leaf.product, "quantity": 0})
        line["quantity"] += leaf.abs_quantity
    return lines


def mass_pareto(model, perimeter_id="ID_0"):
    node = model.nodes[perimeter_id]
    lines = perimeter_lines(model, perimeter_id)
    total = sum(line["part"]["mass_kg"] * line["quantity"] for line in lines.values())
    rows = []
    for part_id, line in lines.items():
        part = line["part"]
        material = model.material_of(part)
        mass = part["mass_kg"] * line["quantity"]
        rows.append({
            "part_id": part_id,
            "part": model.node_label(part_id),
            "material": part["material"],
            "family": material["family"] if material else None,
            "density": material["density_kg_dm3"] if material else None,
            "quantity": line["quantity"],
            "mass_kg": mass,
            "share": mass / total,
            "volume_l": (model.volume_litres(part) or 0) * line["quantity"],
            "envelope_mm": part.get("envelope_mm", ""),
            "maturity": part["maturity"],
            "options": len(part["mass_options"]),
        })
    rows.sort(key=lambda r: -r["mass_kg"])
    cumulated = 0.0
    for row in rows:
        cumulated += row["mass_kg"]
        row["cumulated_share"] = cumulated / total
    return {"perimeter": node.label, "total_mass": total, "rows": rows}


def mass_options(model, perimeter_id="ID_0"):
    rows = []
    for part_id, line in perimeter_lines(model, perimeter_id).items():
        part = line["part"]
        quantity = line["quantity"]
        material = model.material_of(part)
        for option in part["mass_options"]:
            mass_before = part["mass_kg"] * quantity
            delta_mass = mass_before * (option["mass_factor"] - 1)
            delta_cost = option["cost_delta_eur"] * quantity
            usage = part.get("usage_kg", part["mass_kg"]) * quantity
            co2_before = usage * material["co2_kg_per_kg"] if material else 0
            new_material = model.materials.get(option.get("new_material"))
            co2_factor = new_material["co2_kg_per_kg"] if new_material else (material["co2_kg_per_kg"] if material else 0)
            co2_after = usage * option["mass_factor"] * co2_factor
            if option["kind"] == "DATA":
                co2_after = co2_before = 0
            rows.append({
                "option_id": option["id"],
                "part_id": part_id,
                "plm_id": part["plm_id"],
                "part": model.node_label(part_id),
                "label": option["label"],
                "kind": option["kind"],
                "material_before": part["material"],
                "material_after": option.get("new_material", part["material"]),
                "mass_before": mass_before,
                "delta_mass": delta_mass,
                "delta_cost": delta_cost,
                "eur_per_kg": delta_cost / -delta_mass if delta_mass else 0,
                "delta_co2": co2_after - co2_before,
                "one_off": option["one_off_eur"],
                "weeks": option["requal_weeks"],
                "feasibility": option["feasibility"],
                "feasibility_label": FEASIBILITY_LABELS[option["feasibility"]],
                "space": option["space_impact"],
                "risk": option["risk"],
                "tests": [t["test"] for t in model.revalidation_tests(part_id)],
                "interfaces": len(model.real_interfaces(part_id)),
            })
    return sorted(rows, key=lambda r: r["eur_per_kg"])


def summarize_plan(model, chosen, perimeter_mass):
    saved = -sum(o["delta_mass"] for o in chosen)
    delta_cost = sum(o["delta_cost"] for o in chosen)
    annual = delta_cost * model.program["annual_volume"]
    value = saved * model.program["lightweight_value_eur_kg"]
    return {
        "saved_kg": saved,
        "mass_after": perimeter_mass - saved,
        "delta_cost_unit": delta_cost,
        "delta_cost_annual": annual,
        "one_off": sum(o["one_off"] for o in chosen),
        "max_weeks": max((o["weeks"] for o in chosen), default=0),
        "delta_co2": sum(o["delta_co2"] for o in chosen),
        "avg_eur_per_kg": delta_cost / saved if saved else 0,
        "oem_value_unit": value,
        "net_unit": value - delta_cost,
        "fits_sop": max((o["weeks"] for o in chosen), default=0) <= model.weeks_to_sop,
    }


def mass_plan(model, perimeter_id="ID_0", target_saving_kg=None, min_feasibility="MEDIUM", max_weeks=None, allowed_parts=None):
    """Plan au meilleur coût : options triées par coût du kg gagné (heuristique gloutonne), une seule option par pièce."""
    max_weeks = model.weeks_to_sop if max_weeks is None else max_weeks
    perimeter_mass = model.nodes[perimeter_id].total_mass
    if target_saving_kg is None:
        target_saving_kg = max(0.0, perimeter_mass - model.program["mass_target_kg"]) if perimeter_id == "ID_0" else 0.05 * perimeter_mass
    options = mass_options(model, perimeter_id)
    eligible = [o for o in options if FEASIBILITY_RANK[o["feasibility"]] >= FEASIBILITY_RANK[min_feasibility] and o["weeks"] <= max_weeks and (not allowed_parts or o["part_id"] in allowed_parts)]
    chosen = []
    used = set()
    saved = 0.0
    for option in eligible:
        if saved >= target_saving_kg:
            break
        if option["part_id"] in used:
            continue
        chosen.append(option)
        used.add(option["part_id"])
        saved -= option["delta_mass"]
    summary = summarize_plan(model, chosen, perimeter_mass)
    sources = [model.source_ref(o["part_id"], "masse, matériau, option d'allègement, interfaces") for o in chosen]
    return {
        "perimeter": model.nodes[perimeter_id].label,
        "perimeter_mass": perimeter_mass,
        "target_saving_kg": target_saving_kg,
        "reached": saved >= target_saving_kg,
        "chosen": chosen,
        "options": options,
        "eligible": len(eligible),
        "summary": summary,
        "max_weeks_allowed": max_weeks,
        "min_feasibility": min_feasibility,
        "sources": sources,
    }


# ---------------------------------------------------------------- Indicateurs


def product_kpis(model):
    from plm.quality import control_findings, counts

    table = concentration(model)
    crit = criticality(model)
    release = release_readiness(model)
    return {
        "mass_kg": model.tree.total_mass,
        "pieces": sum(line["quantity"] for line in model.bom.values()),
        "references": len(model.bom),
        "bom_cost": model.bom_cost(),
        "selling_price": model.program["selling_price_eur"],
        "margin_unit": model.margin_per_unit(),
        "annual_spend": model.bom_cost() * model.program["annual_volume"],
        "suppliers_active": table["suppliers_active"],
        "suppliers_referenced": table["suppliers_referenced"],
        "countries": table["countries"],
        "non_eu_share": table["non_eu_share"],
        "single_source_parts": table["single_source_parts"],
        "critical_parts": sum(r["level"] == "Critique" for r in crit),
        "interfaces": len(model.enrichment["interfaces"]),
        "alerts": counts(control_findings(model.findings)),
        "release_ready": release["ready"],
        "release_total": release["total"],
        "bounding_box_mm": model.bounding_box(),
    }
