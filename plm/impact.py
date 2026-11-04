"""Analyse d'impacts : applique des facteurs à une copie du produit et compare le résultat à la référence.

Cinq facteurs combinables : rupture d'un fournisseur, prix d'un matériau, changement de fournisseur, release
et allègement. Sans élément choisi, un facteur touche toutes les pièces qu'il concerne.
"""
from copy import deepcopy
from math import ceil

from plm import scenarios
from plm.model import FAMILIES, MATURITY_RANK, PlmModel, QUALIFIED

CLASS_WEIGHTS = {"A": 3, "B": 2, "C": 1}
PPM_CEILING = 150
OTD_FLOOR = 85
PPAP_VALUES = {"APPROVED": 1.0, "CONDITIONAL": 0.6, "IN_PROGRESS": 0.3, "NOT_STARTED": 0.0}
MATURITY_VALUES = {"RELEASED": 1.0, "FROZEN": 0.75, "IN_WORK": 0.4, "PRIVATE": 0.1, "OBSOLETE": 0.0}
FEASIBILITY_QUALITY_PENALTY = {"HIGH": 0, "MEDIUM": 5, "LOW": 15}
FEASIBILITY_RISK = {"HIGH": 0, "MEDIUM": 5, "LOW": 10}
CONCENTRATED_MATERIAL_RISK = 5  # magnésium : offre très concentrée en Chine

QUALITY_CRITERIA = [
    dict(key="ppm", label="Qualité fournisseur (PPM)", max=35, rule="100 % à 0 ppm, 0 % à 150 ppm ou plus, moyenne pondérée par la part de volume"),
    dict(key="otd", label="Livraison à l'heure", max=15, rule="0 % à 85 % de livraisons à l'heure ou moins, 100 % à 100 %"),
    dict(key="ppap", label="Statut PPAP", max=25, rule="Approuvé 100 %, à refaire 60 %, en cours 30 %, non qualifié 0 %"),
    dict(key="maturity", label="Maturité", max=15, rule="RELEASED 100 %, FROZEN 75 %, IN_WORK 40 %, PRIVATE 10 %, OBSOLETE 0 %"),
    dict(key="data", label="Complétude des données", max=10, rule="Part renseignée parmi description, matériau, fournisseur, prix et historique"),
]


def quality_of_part(model, part):
    """Score de qualité sur 100. Une option d'allègement non éprouvée retire des points."""
    links = model.active_links(part)
    total = sum(l["share_pct"] for l in links)

    def weighted(value):
        return sum(value(l) * l["share_pct"] for l in links) / total if total else 0.0

    ppm = weighted(lambda l: model.suppliers[l["supplier"]]["quality_ppm"])
    otd = weighted(lambda l: model.suppliers[l["supplier"]]["otd_pct"])
    checks = [bool(part["description"]), bool(part["material"]), bool(part["sourcing"]), any("unit_price_eur" in l for l in links), len(part["revisions"]) == part["revision_index"]]
    values = {
        "ppm": max(0.0, 1 - ppm / PPM_CEILING) if links else 0.0,
        "otd": min(1.0, max(0.0, (otd - OTD_FLOOR) / (100 - OTD_FLOOR))) if links else 0.0,
        "ppap": weighted(lambda l: PPAP_VALUES[l["qualification"]]),
        "maturity": MATURITY_VALUES[part["maturity"]],
        "data": sum(checks) / len(checks),
    }
    points = {c["key"]: c["max"] * values[c["key"]] for c in QUALITY_CRITERIA}
    penalty = part.get("quality_penalty", 0)
    return {"score": max(0.0, sum(points.values()) - penalty), "points": points, "penalty": penalty}


def weighted_average(model, values, part_ids=None):
    """Moyenne pondérée par la classe : une pièce A pèse 3, une B pèse 2, une C pèse 1."""
    ids = [p["xml_id"] for p in model.physical_parts] if part_ids is None else list(part_ids)
    weights = [CLASS_WEIGHTS[model.products[i].get("criticality", "C")] for i in ids]
    return sum(values[i] * w for i, w in zip(ids, weights)) / sum(weights) if ids else 0.0


def resolve_scope(model, elements):
    parts = set()
    for element in elements:
        node = model.nodes.get(element) or model.nodes_by_part[element][0]
        parts |= {leaf.part_id for leaf in node.leaves() if leaf.product.get("physical", True)}
    return parts


def material_shares(model):
    cost = model.bom_cost()
    shares = {}
    for part in model.parts:
        info = model.material_of(part)
        if info and part.get("usage_kg"):
            shares[info["family"]] = shares.get(info["family"], 0.0) + model.material_cost(part) * model.quantity(part["xml_id"]) / cost
    return shares


def supplier_shares(model):
    return {row["supplier_id"]: row["spend_share"] for row in scenarios.supplier_table(model)}


def snapshot(model):
    risk_rows = scenarios.criticality(model)
    cost = model.bom_cost()
    return {
        "mass": model.tree.total_mass,
        "cost": cost,
        "margin_pct": model.margin_per_unit(cost) / model.program["selling_price_eur"],
        "annual_cost": cost * model.program["annual_volume"],
        "risk": {row["part_id"]: row["score"] for row in risk_rows},
        "quality": {p["xml_id"]: quality_of_part(model, p)["score"] for p in model.physical_parts},
        "critical": sum(row["level"] == "Critique" for row in risk_rows),
        "single_source": scenarios.concentration(model)["single_source_parts"],
        "suppliers": supplier_shares(model),
        "materials": material_shares(model),
    }


class ScenarioBuilder:
    """Modifie une copie des données : la référence n'est jamais touchée."""

    def __init__(self, model, scope):
        self.model = model
        self.data = deepcopy(model.data)
        self.products = self.data["products"]
        self.scope = scope
        self.touched = {}
        self.notes = []
        self.details = {}
        self.suppliers_tracked = []
        self.families_tracked = []

    def in_scope(self, part_id):
        return not self.scope or part_id in self.scope

    def touch(self, part_id, factor):
        factors = self.touched.setdefault(part_id, [])
        if factor not in factors:
            factors.append(factor)

    def track_supplier(self, supplier_id):
        if supplier_id not in self.suppliers_tracked:
            self.suppliers_tracked.append(supplier_id)

    def track_family(self, family):
        if family and family not in self.families_tracked:
            self.families_tracked.append(family)

    def physical_parts(self):
        return [self.products[p["xml_id"]] for p in self.model.physical_parts]

    def wrappers_of(self, part_id):
        return [p for p in self.products.values() if p["kind"] == "wrapper" and p["children"][0]["product"] == part_id]

    # ---------------------------------------------------------- Allègement
    def apply_mass(self, settings):
        options = scenarios.mass_options(self.model, self.model.tree.id)
        chosen_ids = settings.get("options") or []
        if chosen_ids:
            chosen = [o for o in options if o["option_id"] in chosen_ids and self.in_scope(o["part_id"])]
            automatic = False
        else:
            saving = max(0.0, self.model.tree.total_mass - settings["target_kg"])
            chosen = scenarios.mass_plan(self.model, self.model.tree.id, saving, "MEDIUM", allowed_parts=self.scope or None)["chosen"]
            automatic = True
        applied = []
        seen = set()
        for option in chosen:
            if option["part_id"] in seen:
                self.notes.append(f"Une seule option est retenue par pièce : {option['label']} ignorée sur {option['part']}.")
                continue
            seen.add(option["part_id"])
            self._apply_mass_option(option)
            applied.append(option)
        self.details["mass"] = {"chosen": applied, "automatic": automatic, "target_kg": settings["target_kg"], **scenarios.summarize_plan(self.model, applied, self.model.tree.total_mass)}

    def _apply_mass_option(self, option):
        part = self.products[option["part_id"]]
        spec = next(o for o in part["mass_options"] if o["id"] == option["option_id"])
        factor = spec["mass_factor"]
        delta = spec["cost_delta_eur"]
        old_material = self.model.material_of(self.model.products[part["xml_id"]])
        self.track_family(old_material["family"] if old_material else None)

        before_cost = self.model.should_cost(self.model.products[part["xml_id"]]) or 0.0
        part["mass_kg"] = round(part["mass_kg"] * factor, 4)
        if part.get("usage_kg"):
            part["usage_kg"] *= factor
        new_material = spec.get("new_material")
        if new_material:
            family = self.model.materials[new_material]["family"]
            part["material"] = new_material
            part["material_family"] = family
            part.pop("material_price_eur_kg", None)
            self.track_family(family)
            for wrapper in self.wrappers_of(part["xml_id"]):
                wrapper["material"] = new_material
                wrapper["material_family"] = family
        for link in part["sourcing"]:
            if "unit_price_eur" in link:
                link["unit_price_eur"] += delta
        if part.get("usage_kg"):
            info = self.model.materials[part["material"]]
            part["conversion_eur"] = max(0.0, before_cost + delta - part["usage_kg"] * info["price_eur_kg"])
        part["quality_penalty"] = FEASIBILITY_QUALITY_PENALTY[spec["feasibility"]]
        part["technical_risk"] = FEASIBILITY_RISK[spec["feasibility"]] + (CONCENTRATED_MATERIAL_RISK if new_material and "Magnesium" in new_material else 0)
        self.touch(part["xml_id"], "Allègement")

    # ---------------------------------------------------------- Prix d'un matériau
    def apply_price(self, settings):
        target = settings["material"]
        pct = settings["pct"]
        concerned = 0
        for part in self.physical_parts():
            info = self.model.materials.get(part["material"])
            if not info or not part.get("usage_kg") or not self.in_scope(part["xml_id"]):
                continue
            if target != info["family"] and target != info["plm_name"]:
                continue
            base = part.get("material_price_eur_kg", info["price_eur_kg"])
            delta_price = base * info["index_share"] * pct / 100
            part["material_price_eur_kg"] = base + delta_price
            delta_part = part["usage_kg"] * delta_price
            for link in part["sourcing"]:
                if "unit_price_eur" in link:
                    link["unit_price_eur"] += delta_part
            self.touch(part["xml_id"], "Prix matériau")
            concerned += 1
        self.track_family(target if target in FAMILIES else self.model.materials[target]["family"])
        self.details["price"] = {"material": target, "pct": pct, "parts": concerned}

    # ---------------------------------------------------------- Changement de fournisseur
    def apply_change(self, settings):
        from_id, to_id, share = settings.get("from"), settings.get("to"), settings["share"]
        if from_id:
            self.track_supplier(from_id)
        if to_id:
            self.track_supplier(to_id)
        if not from_id and not self.scope:
            self.notes.append("Changement de fournisseur : choisissez un fournisseur ou des éléments.")
        rows = []
        for part in self.physical_parts():
            part_id = part["xml_id"]
            if not self.in_scope(part_id) or (not from_id and not self.scope):
                continue
            actives = [l for l in part["sourcing"] if l["share_pct"] > 0]
            link = next((l for l in actives if l["supplier"] == from_id), None) if from_id else max(actives, key=lambda l: l["share_pct"], default=None)
            if link is None:
                continue
            self.track_supplier(link["supplier"])
            target = self._pick_target(part, link, to_id)
            label = self.model.node_label(part_id)
            current = self.model.suppliers[link["supplier"]]["name"]
            if target is None:
                rows.append({"part_id": part_id, "part": label, "from": current, "to": None, "moved": 0, "one_off": 0, "delay": None, "no_alternative": True})
                self.touch(part_id, "Changement de fournisseur (sans alternative)")
                continue
            newly_qualified = target["qualification"] not in QUALIFIED
            tests = self.model.revalidation_tests(part_id) if target["qualification"] == "NOT_STARTED" else []
            one_off = target["switching_cost_eur"] + sum(t["cost_eur"] for t in tests)
            lag = ceil(target["transit_days"] / 7)
            delay = target["requal_weeks"] + target["ramp_up_weeks"] + lag if newly_qualified or target["share_pct"] == 0 else target["ramp_up_weeks"]
            moved = link["share_pct"] * share / 100
            target["share_pct"] += moved
            link["share_pct"] -= moved
            if link["share_pct"] <= 0:
                part["sourcing"].remove(link)
            target["qualification"] = "APPROVED"  # état visé : une fois le nouveau fournisseur qualifié
            target["requal_weeks"] = 0
            self.track_supplier(target["supplier"])
            self.touch(part_id, "Changement de fournisseur")
            rows.append({"part_id": part_id, "part": label, "from": current, "to": self.model.suppliers[target["supplier"]]["name"], "moved": moved, "one_off": one_off, "delay": delay, "no_alternative": False})
        self.details["change"] = {
            "rows": rows,
            "parts": len(rows),
            "no_alternative": [r["part"] for r in rows if r["no_alternative"]],
            "one_off": sum(r["one_off"] for r in rows),
            "max_delay": max((r["delay"] for r in rows if r["delay"] is not None), default=0),
        }

    def _pick_target(self, part, link, to_id):
        others = [l for l in part["sourcing"] if l is not link]
        if to_id:
            return next((l for l in others if l["supplier"] == to_id), None)
        if not others:
            return None
        return min(others, key=lambda l: (l["qualification"] not in QUALIFIED, l["requal_weeks"] + l["ramp_up_weeks"], l.get("unit_price_eur", 0)))

    # ---------------------------------------------------------- Rupture
    def apply_disruption(self, settings):
        supplier_id, weeks = settings.get("supplier"), settings["weeks"]
        disrupted = []
        if not supplier_id and not self.scope:
            self.notes.append("Rupture : choisissez un fournisseur ou des éléments.")
        for part in self.physical_parts():
            part_id = part["xml_id"]
            if not self.in_scope(part_id) or (not supplier_id and not self.scope):
                continue
            actives = [l for l in part["sourcing"] if l["share_pct"] > 0]
            link = next((l for l in actives if l["supplier"] == supplier_id), None) if supplier_id else max(actives, key=lambda l: l["share_pct"], default=None)
            if link is None:
                continue
            reference = self.model.products[part_id]
            reference_link = next((l for l in reference["sourcing"] if l["supplier"] == link["supplier"]), None)
            if reference_link is not None and reference_link["share_pct"] > 0:
                disrupted.append((reference, reference_link))
            self.track_supplier(link["supplier"])
            # État pendant l'arrêt : le fournisseur sort, les autres sources actives se partagent le volume.
            part["sourcing"].remove(link)
            remaining = [l for l in part["sourcing"] if l["share_pct"] > 0]
            total = sum(l["share_pct"] for l in remaining)
            for other in remaining:
                other["share_pct"] = other["share_pct"] * 100 / total
            self.touch(part_id, "Rupture")
        self.details["disruption"] = combine_disruption(self.model, disrupted, weeks)

    # ---------------------------------------------------------- Release
    def apply_release(self, settings):
        target, gate = settings["target"], settings["gate"]
        for reference in self.model.physical_parts:
            part_id = reference["xml_id"]
            check = scenarios.part_release_status(self.model, reference, target, gate)
            if check["ready"]:
                continue
            # Sans élément choisi : projection au jalon, seules les pièces prévues à temps sont promues.
            on_time = check["date"] is not None and check["date"] <= gate
            if not (part_id in self.scope if self.scope else on_time):
                continue
            part = self.products[part_id]
            for item in [part, *self.wrappers_of(part_id)]:
                if MATURITY_RANK[item["maturity"]] < MATURITY_RANK[target]:
                    item["maturity"] = target
            if target == "RELEASED":
                for link in part["sourcing"]:
                    if link["share_pct"] > 0:
                        link["qualification"] = "APPROVED"
                        link["requal_weeks"] = 0
                        if "unit_price_eur" not in link and self.model.should_cost(reference) is not None:
                            link["unit_price_eur"] = round(self.model.should_cost(reference), 2)
            self.touch(part_id, "Release")
        assemblies = sorted((n for n in self.model.nodes.values() if n.is_assembly), key=lambda n: -n.depth)
        for node in assemblies:
            parts = [self.products[leaf.part_id] for leaf in node.leaves() if leaf.product.get("physical", True)]
            if all(MATURITY_RANK[p["maturity"]] >= MATURITY_RANK[target] for p in parts):
                self.products[node.part_id]["maturity"] = target

    def build(self):
        self._roll_up(self.data["root"])
        return PlmModel(self.data)

    def _roll_up(self, product_id):
        product = self.products[product_id]
        if not product["children"]:
            return product["mass_kg"]
        total = sum(self._roll_up(c["product"]) * c["quantity"] for c in product["children"])
        product["mass_kg"] = round(total, 3)
        return total


def combine_disruption(model, disrupted, weeks):
    """Toute la ligne s'arrête dès qu'une pièce manque : on retient, chaque semaine, la pièce la plus limitante."""
    if not disrupted:
        return {"parts": 0}
    program = model.program
    weekly = program["weekly_demand"]
    per_day = weekly / program["working_days_per_week"]
    margin = model.margin_per_unit()
    horizon = weeks + 26
    strategies = {}
    for name, settings in scenarios.STRATEGIES.items():
        runs = [scenarios.run_strategy(model, part, link, weeks, horizon, name) for part, link in disrupted]
        delivered = [min(run["series"][week]["delivered"] for run in runs) for week in range(horizon)]
        lost = sum(weekly - value for value in delivered)
        stop_days = lost / per_day
        extras = sum(run["extra_purchase"] + run["air_freight"] + run["one_off"] for run in runs)
        cost = lost * margin + stop_days * program["line_stop_penalty_eur_day"] + extras
        stopped = [week + 1 for week, value in enumerate(delivered) if value < weekly]
        strategies[name] = {"label": settings["label"], "delivered": delivered, "lost_units": lost, "stop_days": stop_days, "extras": extras, "total_cost": cost, "first_stop_week": stopped[0] if stopped else None, "last_stop_week": stopped[-1] if stopped else None}
    best = min(strategies, key=lambda name: strategies[name]["total_cost"])
    return {"parts": len(disrupted), "weeks": weeks, "strategies": strategies, "best": best}


def part_row(reference, scenario, part_id, factors, before, after):
    ref_part, new_part = reference.products[part_id], scenario.products[part_id]
    quantity = reference.quantity(part_id)

    def sources(model, part):
        links = sorted(model.active_links(part), key=lambda l: -l["share_pct"])
        return " · ".join(f"{model.suppliers[l['supplier']]['name']} ({l['share_pct']:.0f} %)" for l in links) or "Aucun"

    return {
        "part_id": part_id,
        "plm_id": ref_part["plm_id"],
        "part": reference.node_label(part_id),
        "factors": ", ".join(factors),
        "mass_before": ref_part["mass_kg"] * quantity,
        "mass_after": new_part["mass_kg"] * quantity,
        "cost_before": reference.line_cost(ref_part),
        "cost_after": scenario.line_cost(new_part),
        "risk_before": before["risk"][part_id],
        "risk_after": after["risk"][part_id],
        "quality_before": before["quality"][part_id],
        "quality_after": after["quality"][part_id],
        "suppliers_before": sources(reference, ref_part),
        "suppliers_after": sources(scenario, new_part),
        "material_before": ref_part["material"],
        "material_after": new_part["material"],
        "maturity_before": ref_part["maturity"],
        "maturity_after": new_part["maturity"],
    }


def analyze(model, params):
    """Applique les facteurs actifs et renvoie les indicateurs face à la référence."""
    scope = resolve_scope(model, params.get("elements", []))
    builder = ScenarioBuilder(model, scope)
    if params.get("mass"):
        builder.apply_mass(params["mass"])
    if params.get("price"):
        builder.apply_price(params["price"])
    if params.get("change"):
        builder.apply_change(params["change"])
    if params.get("disruption"):
        builder.apply_disruption(params["disruption"])
    if params.get("release"):
        builder.apply_release(params["release"])
    scenario = builder.build()

    before, after = snapshot(model), snapshot(scenario)
    touched_ids = [part_id for part_id in builder.touched if part_id in before["quality"]]

    def score(values_key):
        product = (weighted_average(model, before[values_key]), weighted_average(model, after[values_key]))
        subset = (weighted_average(model, before[values_key], touched_ids), weighted_average(model, after[values_key], touched_ids)) if touched_ids else None
        return {"product": product, "touched": subset}

    suppliers = builder.suppliers_tracked or [max(before["suppliers"], key=before["suppliers"].get)]
    families = builder.families_tracked or [max(before["materials"], key=before["materials"].get)]

    details = dict(builder.details)
    if params.get("release"):
        target, gate = params["release"]["target"], params["release"]["gate"]
        details["release"] = {"before": scenarios.release_readiness(model, target, gate), "after": scenarios.release_readiness(scenario, target, gate), "target": target, "gate": gate}

    rows = [part_row(model, scenario, part_id, builder.touched[part_id], before, after) for part_id in touched_ids]
    rows.sort(key=lambda r: -abs(r["cost_after"] - r["cost_before"]) - abs(r["mass_after"] - r["mass_before"]) - abs(r["risk_after"] - r["risk_before"]))
    sources = [model.source_ref(r["part_id"], "masse, matériau, coût, sourcing, maturité") for r in rows] + [model.supplier_ref(s, "part des achats, qualité") for s in suppliers if touched_ids]

    return {
        "scope": scope,
        "touched": rows,
        "indicators": {
            "mass": (before["mass"], after["mass"]),
            "cost": (before["cost"], after["cost"]),
            "margin_pct": (before["margin_pct"], after["margin_pct"]),
            "annual_cost": (before["annual_cost"], after["annual_cost"]),
            "quality": score("quality"),
            "risk": score("risk"),
            "critical": (before["critical"], after["critical"]),
            "single_source": (before["single_source"], after["single_source"]),
            "suppliers": [{"id": s, "label": model.suppliers[s]["name"], "before": before["suppliers"].get(s, 0.0), "after": after["suppliers"].get(s, 0.0)} for s in suppliers[:4]],
            "materials": [{"label": f, "before": before["materials"].get(f, 0.0), "after": after["materials"].get(f, 0.0)} for f in families[:4]],
        },
        "details": details,
        "notes": builder.notes,
        "sources": sources,
    }
