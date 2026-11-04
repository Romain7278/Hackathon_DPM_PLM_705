"""Contrôles de qualité des données : données manquantes, incohérences, risques d'approvisionnement."""
import re

from plm.model import MATURITY_RANK

BLOCKING = "Bloquant"
WARNING = "Attention"
INFO = "Info"

MISSING = "Données manquantes"
INCONSISTENT = "Incohérence"
SUPPLY = "Approvisionnement"
STRUCTURE = "Structure"
NAMING = "Nommage"

SEVERITY_RANK = {BLOCKING: 0, WARNING: 1, INFO: 2}
SEVERITY_ICONS = {BLOCKING: "🔴", WARNING: "🟠", INFO: "🔵"}

# Alertes déjà calculées par le parseur, à partir du XML d'origine.
PARSER_RULES = {
    "shared_name": (WARNING, NAMING),
    "near_duplicate_name": (INFO, NAMING),
    "irregular_name": (INFO, NAMING),
    "meshing_aid": (WARNING, STRUCTURE),
    "possible_double_count": (WARNING, STRUCTURE),
    "misleading_name": (WARNING, NAMING),
    "missing_wrapper": (INFO, STRUCTURE),
}


def finding(rule, severity, domain, product, message):
    return {"rule": rule, "severity": severity, "domain": domain, "product_id": product["xml_id"], "name": product["name"], "message": message}


def check_parser_warnings(model):
    found = []
    for product in model.products.values():
        # Une enveloppe EI et sa pièce 3D forment une seule ligne : pas de doublon d'alerte.
        part = model.products[product["children"][0]["product"]] if product["kind"] == "wrapper" else None
        part_codes = {w["code"] for w in part["warnings"]} if part else set()
        for warning in product["warnings"]:
            if warning["code"] in part_codes:
                continue
            severity, domain = PARSER_RULES[warning["code"]]
            found.append(finding(warning["code"], severity, domain, product, warning["message"]))
    return found


def check_maturity(model):
    found = []
    for node in model.nodes.values():
        if not node.is_assembly:
            continue
        rank = MATURITY_RANK[node.product["maturity"]]
        if rank < MATURITY_RANK["FROZEN"]:
            continue
        below = []
        for leaf in node.leaves():
            ranks = [leaf.product["maturity"]] + ([leaf.wrapper["maturity"]] if leaf.wrapper else [])
            lowest = min(ranks, key=MATURITY_RANK.get)
            if MATURITY_RANK[lowest] < rank:
                below.append(f"{leaf.label} ({lowest})")
        below = sorted(set(below))
        if below:
            shown = ", ".join(below[:6]) + (f" et {len(below) - 6} autres" if len(below) > 6 else "")
            found.append(finding(
                "maturity_parent_above_child", BLOCKING, INCONSISTENT, node.product,
                f"{node.label} est {node.product['maturity']} alors que {len(below)} sous-composants sont moins matures : {shown}.",
            ))

    for product in model.products.values():
        if product["kind"] == "wrapper":
            part = model.products[product["children"][0]["product"]]
            if MATURITY_RANK[product["maturity"]] > MATURITY_RANK[part["maturity"]]:
                found.append(finding(
                    "ei_above_3d", BLOCKING, INCONSISTENT, part,
                    f"L'Engineering Item est {product['maturity']} alors que sa pièce 3D est {part['maturity']}.",
                ))
    return found


def check_lifecycle(model):
    found = []
    for part in model.parts:
        maturity = part["maturity"]
        if maturity == "OBSOLETE":
            found.append(finding("obsolete_in_bom", BLOCKING, INCONSISTENT, part,
                                 f"Pièce OBSOLETE encore utilisée {model.quantity(part['xml_id'])} fois dans la nomenclature."))
        if maturity == "PRIVATE" and not part.get("physical", True):
            found.append(finding("study_geometry", WARNING, STRUCTURE, part,
                                 "Géométrie d'étude en PRIVATE : à exclure de la nomenclature de production."))
        modified = part["modified"][:10]
        if maturity in ("FROZEN", "RELEASED") and part.get("maturity_date") and modified > part["maturity_date"]:
            found.append(finding("modified_after_maturity", WARNING, INCONSISTENT, part,
                                 f"Modifiée le {modified}, après le passage en {maturity} du {part['maturity_date']}, sans nouvelle révision."))
    return found


def check_missing_data(model):
    found = []
    for part in model.physical_parts:
        part_id = part["xml_id"]
        if not part["sourcing"]:
            found.append(finding("missing_supplier", BLOCKING, MISSING, part, "Aucun fournisseur désigné."))
        elif not any("unit_price_eur" in l for l in model.active_links(part)):
            found.append(finding("missing_price", WARNING, MISSING, part, "Prix fournisseur non renseigné : le coût affiché est une estimation."))
        if not part["material"]:
            found.append(finding("missing_material", BLOCKING, MISSING, part, "Matériau non renseigné."))
        if not part["mass_kg"]:
            found.append(finding("missing_mass", BLOCKING, MISSING, part, "Masse non renseignée."))
        if not part["description"]:
            found.append(finding("missing_description", INFO, MISSING, part, "Description non renseignée."))
        if len(part["revisions"]) != part["revision_index"]:
            found.append(finding("missing_history", WARNING, MISSING, part,
                                 f"Historique incomplet : {len(part['revisions'])} révisions tracées pour la révision {part['revision']}."))
    for product in model.products.values():
        if product["kind"] == "assembly" and not product["description"]:
            found.append(finding("missing_description", INFO, MISSING, product, "Description non renseignée."))
    return found


def check_supply(model):
    found = []
    reference = model.program["reference_date"]
    for part in model.physical_parts:
        links = part["sourcing"]
        if not links:
            continue
        name = model.suppliers[links[0]["supplier"]]["name"]
        qualified = model.qualified_links(part)
        if not qualified:
            found.append(finding("no_qualified_source", BLOCKING, SUPPLY, part, "Aucune source qualifiée : tous les PPAP sont en cours."))
        elif len(qualified) == 1:
            sole = model.suppliers[qualified[0]["supplier"]]["name"]
            others = len(links) - 1
            detail = f"{others} autre(s) référencé(s) mais non qualifié(s)" if others else "aucune alternative référencée"
            found.append(finding("single_source", WARNING, SUPPLY, part, f"Mono-source : {sole} est le seul fournisseur qualifié ({detail})."))
        if part["maturity"] == "RELEASED" and not any(l["qualification"] == "APPROVED" for l in links):
            found.append(finding("released_without_ppap", BLOCKING, INCONSISTENT, part,
                                 f"Pièce RELEASED sans PPAP approuvé chez {name}."))
        for link in model.active_links(part):
            supplier = model.suppliers[link["supplier"]]["name"]
            if link.get("contract_end") and link["contract_end"] < reference:
                found.append(finding("contract_expired", WARNING, SUPPLY, part,
                                     f"Contrat échu le {link['contract_end']} chez {supplier}, encore actif à {link['share_pct']} %."))
            if link["qualification"] == "CONDITIONAL":
                found.append(finding("ppap_conditional", WARNING, SUPPLY, part,
                                     f"PPAP de {supplier} à refaire sur la révision {part['revision']} (prévu le {link.get('ppap_date', 'non planifié')})."))
    return found


def check_structure(model):
    found = []
    for node in model.nodes.values():
        if not node.is_assembly:
            continue
        computed = sum(child.total_mass for child in node.children)
        if abs(computed - node.unit_mass) > 0.01:
            found.append(finding("mass_rollup", BLOCKING, INCONSISTENT, node.product,
                                 f"Masse déclarée {node.unit_mass} kg, somme des enfants {computed:.3f} kg."))

    emotor = model.nodes["ID_1"]
    names = " ".join(n.label.lower() for n in emotor.leaves())
    if not re.search(r"rotor|magnet|aimant", names):
        found.append(finding("structure_gap", WARNING, STRUCTURE, emotor.product,
                             "Aucun rotor ni aimant dans la nomenclature du moteur : export partiel ou structure incomplète. Masse, coût et risques terres rares ne sont pas couverts."))
    organizations = {p["organization"] for p in model.products.values()}
    if organizations == {"Company Name"}:
        found.append(finding("placeholder_metadata", INFO, MISSING, model.tree.product,
                             "Organisation à la valeur générique « Company Name » sur tous les produits."))
    return found


def run_checks(model):
    found = (check_maturity(model) + check_lifecycle(model) + check_missing_data(model) + check_supply(model)
             + check_structure(model) + check_parser_warnings(model))
    return sorted(found, key=lambda f: (SEVERITY_RANK[f["severity"]], f["domain"], f["name"]))


def counts(findings):
    return {severity: sum(1 for f in findings if f["severity"] == severity) for severity in SEVERITY_RANK}
