"""Analyse d'impacts : applique des facteurs à une copie du produit et compare le résultat à la référence.

Six facteurs combinables : rupture, prix matière, changement de fournisseur,
release, allègement et versioning.
"""
from copy import deepcopy
from math import ceil
from datetime import timedelta

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


def next_revision(part):
    current = str(part["revision"])
    if current.isascii() and current.isalpha() and current.isupper():
        value = 0
        for letter in current:
            value = value * 26 + ord(letter) - ord('A') + 1
        value += 1
        label = ''
        while value:
            value, digit = divmod(value - 1, 26)
            label = chr(ord('A') + digit) + label
        return label
    return str(int(current) + 1) if current.isdigit() else current + '.1'

QUALITY_CRITERIA = [
    dict(key="ppm", label="Défauts fournisseurs", max=35, rule="PPM = pièces défectueuses par million. 35 points à 0 PPM, 0 à 150 PPM ou plus ; progression linéaire, pondérée par les volumes"),
    dict(key="otd", label="Livraison à l'heure", max=15, rule="0 % à 85 % de livraisons à l'heure ou moins, 100 % à 100 %"),
    dict(key="ppap", label="Qualification des fournisseurs", max=25, rule="Approuvé 100 %, à refaire 60 %, en cours 30 %, non qualifié 0 % ; moyenne pondérée par les volumes"),
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


def compare_models(reference, candidate, changed_ids=()):
    """Les mêmes indicateurs que les scénarios, calculés sur deux exports réels."""
    before, after = snapshot(reference), snapshot(candidate)
    changed_ids = set(changed_ids)

    def scores(key):
        ids_before = [p['xml_id'] for p in reference.physical_parts if p['plm_id'] in changed_ids]
        ids_after = [p['xml_id'] for p in candidate.physical_parts if p['plm_id'] in changed_ids]
        return {
            'product': (weighted_average(reference, before[key]), weighted_average(candidate, after[key])),
            'touched': (weighted_average(reference, before[key], ids_before), weighted_average(candidate, after[key], ids_after)) if ids_before and ids_after else None,
        }

    indicators = {key: (before[key], after[key]) for key in ('mass', 'cost', 'margin_pct', 'critical', 'single_source')}
    indicators.update(quality=scores('quality'), risk=scores('risk'))
    suppliers = before['suppliers'].keys() | after['suppliers'].keys()
    indicators['suppliers'] = [
        {'id': sid, 'label': (candidate.suppliers.get(sid) or reference.suppliers[sid])['name'],
         'before': before['suppliers'].get(sid, 0), 'after': after['suppliers'].get(sid, 0)}
        for sid in sorted(suppliers, key=lambda sid: -max(before['suppliers'].get(sid, 0), after['suppliers'].get(sid, 0)))
    ]
    indicators['materials'] = [
        {'label': family, 'before': before['materials'].get(family, 0), 'after': after['materials'].get(family, 0)}
        for family in sorted(before['materials'].keys() | after['materials'].keys())
    ]
    return {'indicators': indicators}


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

    # ---------------------------------------------------------- Versioning
    def apply_versioning(self, settings):
        part_id = settings["part"]
        if part_id not in {p["xml_id"] for p in self.model.physical_parts}:
            raise ValueError("Le versioning doit concerner une pièce physique.")
        if not self.in_scope(part_id):
            self.notes.append("Versioning : la pièce choisie est hors du périmètre des éléments sélectionnés.")
            return
        reference = self.model.products[part_id]
        part = self.products[part_id]
        kind = settings.get("kind", "geometry")
        if kind not in ("geometry", "material", "process"):
            raise ValueError("Nature de modification inconnue.")
        weeks = settings["weeks"]
        delta_pct = settings.get("mass_pct", 0)
        if not 1 <= weeks <= 52 or not -50 <= delta_pct <= 50:
            raise ValueError("Paramètres de versioning hors limites.")
        interfaces = self.model.real_interfaces(part_id)
        selected = settings.get("interfaces")
        if selected is not None:
            known = {i['other'] for i in interfaces}
            if not set(selected) <= known:
                raise ValueError("Interface étrangère à la pièce modifiée.")
            interfaces = [i for i in interfaces if i['other'] in selected]
        elif kind == 'process':
            interfaces = []
        types = sorted({i['type'] for i in interfaces})
        tests = [self.model.interface_types[t] for t in types]
        weeks = max(weeks, max((test['weeks'] for test in tests), default=0))
        revision = next_revision(reference)
        old_material_cost = self.model.material_cost(part)
        self.track_family(part.get('material_family'))
        new_material = settings.get('material') if kind == 'material' else None
        if new_material:
            if new_material not in self.model.materials:
                raise ValueError("Matériau inconnu.")
            part['material'] = new_material
            part['material_family'] = self.model.materials[new_material]['family']
        complexity_delta = settings.get('complexity_delta', 0)
        if not -2 <= complexity_delta <= 2:
            raise ValueError("Variation de complexité hors limites.")
        if kind == 'process':
            for key in ('process_rating', 'precision_rating'):
                part[key] = min(5, max(1, part[key] + complexity_delta))
        part["mass_kg"] = round(part["mass_kg"] * (1 + delta_pct / 100), 4)
        if part.get("usage_kg"):
            part["usage_kg"] *= 1 + delta_pct / 100
        new_material_cost = self.model.material_cost(part)
        delta_cost = new_material_cost - old_material_cost
        for link in part["sourcing"]:
            if "unit_price_eur" in link:
                link["unit_price_eur"] += delta_cost
            was_qualified = link["qualification"] in QUALIFIED
            if was_qualified:
                link["qualification"] = "IN_PROGRESS"
            link["requal_weeks"] = weeks if was_qualified else max(weeks, link['requal_weeks'])
            link["ppap_date"] = (self.model.reference_date + timedelta(weeks=link['requal_weeks'])).isoformat()
            if link["share_pct"] > 0:
                self.track_supplier(link["supplier"])
        planned = (self.model.reference_date + timedelta(weeks=weeks)).isoformat()
        for item in [part, *self.wrappers_of(part_id)]:
            item["revision"] = revision
            item["revision_index"] += 1
            item["maturity"] = "IN_WORK"
            item["modified"] = self.model.reference_date.isoformat() + "T09:00:00Z"
            item["maturity_date"] = self.model.reference_date.isoformat()
            item["planned_release"] = planned
            if item is not part:
                item["mass_kg"] = part["mass_kg"]
                item['material'] = part['material']
                item['material_family'] = part['material_family']
        part["revisions"].append({"name": revision, "date": self.model.reference_date.isoformat(), "eco": "SIMULATION", "mass_kg": part["mass_kg"], "material": part["material"]})
        self.track_family(part.get("material_family"))
        self.touch(part_id, "Versioning")
        self.details["versioning"] = {
            "part": self.model.node_label(part_id), "part_id": part_id,
            "before": reference["revision"], "after": revision,
            "weeks": weeks, "planned_release": planned,
            "interfaces": len(interfaces),
            "kind": kind,
            "neighbors": [{"part_id": i['other'], "part": self.model.node_label(i['other']), "type": self.model.interface_types[i['type']]['label'], "test": self.model.interface_types[i['type']]['test']} for i in interfaces],
            "assemblies": scenarios.blocked_chain(self.model, part_id),
            "tests": tests, "one_off": sum(test["cost_eur"] for test in tests),
            "mass_pct": delta_pct,
        }

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
            self.touch(part["xml_id"], "Coût matière")
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
        disrupted, rows = [], []
        if not supplier_id and not self.scope:
            self.notes.append("Rupture : choisissez un fournisseur ou des éléments.")
        for part in self.physical_parts():
            part_id = part["xml_id"]
            if not self.in_scope(part_id) or (not supplier_id and not self.scope):
                continue
            actives = [link for link in part["sourcing"] if link["share_pct"] > 0]
            link = next((link for link in actives if link["supplier"] == supplier_id), None) if supplier_id else max(actives, key=lambda link: link["share_pct"], default=None)
            if link is None:
                continue
            reference = self.model.products[part_id]
            reference_link = next((item for item in reference["sourcing"] if item["supplier"] == link["supplier"]), None)
            if reference_link is not None and reference_link["share_pct"] > 0:
                disrupted.append((reference, reference_link))
            self.track_supplier(link["supplier"])
            demand = self.model.program["weekly_demand"] * self.model.quantity(part_id)
            # Une substitution doit couvrir le volume déplacé en plus du volume déjà attribué.
            alternatives = []
            for other in part["sourcing"]:
                delay = other["ramp_up_weeks"] + ceil(other["transit_days"] / 7)
                required = demand * (other["share_pct"] + link["share_pct"]) / 100
                if (other is not link and other["qualification"] in QUALIFIED
                        and other["capacity_per_week"] >= required and delay < weeks):
                    alternatives.append((other, delay))
            before = self.model.unit_cost(part)[0]
            target, delay = min(alternatives, key=lambda pair: (pair[1], pair[0].get("unit_price_eur", before)), default=(None, 0))
            if target is not None:
                target["share_pct"] += link["share_pct"]
                self.track_supplier(target["supplier"])
            else:
                # Le simulateur tient compte des stocks, des autres sources et du redémarrage.
                run = scenarios.run_strategy(self.model, part, link, weeks, weeks + 26, "wait")
                delay = run["stop_days"] / self.model.program["working_days_per_week"]
            part["sourcing"].remove(link)
            self.touch(part_id, "Rupture avec substitution" if target else "Rupture sans alternative")
            rows.append({"part_id": part_id, "part": self.model.node_label(part_id),
                         "from": self.model.suppliers[link["supplier"]]["name"],
                         "to": self.model.suppliers[target["supplier"]]["name"] if target else None,
                         "before": before, "after": self.model.unit_cost(part)[0], "delay_weeks": delay})
        # Anciennes données conservées pour les consommateurs du moteur de simulation.
        self.details["disruption"] = {**combine_disruption(self.model, disrupted, weeks),
                                      "parts": len(rows), "weeks": weeks, "rows": rows}

    # ---------------------------------------------------------- Release
    def apply_release(self, settings):
        target, gate = settings["target"], settings["gate"]
        for reference in self.model.physical_parts:
            part_id = reference["xml_id"]
            check = scenarios.part_release_status(self.model, self.products[part_id], target, gate)
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
        return PlmModel(self.data, risk_priorities=self.model.risk_priorities)

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
        "qualified_before": len(reference.qualified_links(ref_part)),
        "qualified_after": len(scenario.qualified_links(new_part)),
        "material_before": ref_part["material"],
        "material_after": new_part["material"],
        "maturity_before": ref_part["maturity"],
        "maturity_after": new_part["maturity"],
        "revision_before": ref_part["revision"],
        "revision_after": new_part["revision"],
    }


def analyze(model, params):
    """Applique les facteurs actifs et renvoie les indicateurs face à la référence."""
    scope = resolve_scope(model, params.get("elements", []))
    builder = ScenarioBuilder(model, scope)
    if params.get("versioning"):
        builder.apply_versioning(params["versioning"])
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

    suppliers = sorted({link['supplier'] for part_id in touched_ids
                        for current_model in (model, scenario)
                        for link in current_model.products[part_id]['sourcing'] if link['share_pct'] > 0},
                       key=lambda sid: model.suppliers[sid]['name'])
    families = builder.families_tracked or [max(before["materials"], key=before["materials"].get)]

    details = dict(builder.details)
    if details.get('versioning'):
        part_id = details['versioning']['part_id']
        risk_before = next(r for r in scenarios.criticality(model) if r['part_id'] == part_id)
        risk_after = next(r for r in scenarios.criticality(scenario) if r['part_id'] == part_id)
        details['versioning']['criteria'] = [
            {'criterion': b['label'], 'before': b['points'], 'after': a['points'], 'detail': a['detail']}
            for b, a in zip(risk_before['breakdown'], risk_after['breakdown'])
        ]
        details['versioning']['quality_criteria'] = [
            {'criterion': c['label'], 'before': quality_of_part(model, model.products[part_id])['points'][c['key']], 'after': quality_of_part(scenario, scenario.products[part_id])['points'][c['key']]}
            for c in QUALITY_CRITERIA
        ]
    if params.get("release"):
        target, gate = params["release"]["target"], params["release"]["gate"]
        details["release"] = {"before": scenarios.release_readiness(model, target, gate), "after": scenarios.release_readiness(scenario, target, gate), "target": target, "gate": gate}
        details["release"]["maturities"] = [
            {"Pièce": model.node_label(p["xml_id"]), "Maturité actuelle": p["maturity"],
             "Maturité visée": target, "Maturité simulée": scenario.products[p["xml_id"]]["maturity"]}
            for p in model.physical_parts if not scope or p["xml_id"] in scope
        ]

    rows = [part_row(model, scenario, part_id, builder.touched[part_id], before, after) for part_id in touched_ids]
    rows.sort(key=lambda r: -abs(r["cost_after"] - r["cost_before"]) - abs(r["mass_after"] - r["mass_before"]) - abs(r["risk_after"] - r["risk_before"]))
    sources = [model.source_ref(r["part_id"], "révision, masse, matériau, coût, sourcing, maturité, interfaces") for r in rows] + [model.supplier_ref(s, "part des achats, qualité") for s in suppliers if touched_ids]

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
            "suppliers": [{"id": s, "label": model.suppliers[s]["name"], "before": before["suppliers"].get(s, 0.0), "after": after["suppliers"].get(s, 0.0)} for s in suppliers],
            "materials": [{"label": f, "before": before["materials"].get(f, 0.0), "after": after["materials"].get(f, 0.0)} for f in families[:4]],
        },
        "details": details,
        "notes": builder.notes,
        "sources": sources,
    }
