"""Contrôles de qualité des données.

La vue Contrôle des données présente deux familles : les champs manquants ou vides du XML, et la cohérence
de maturité entre parent et enfant. Les autres constats (approvisionnement, cycle de vie, nommage, structure)
restent affichés sur la fiche de chaque pièce.
"""
import re

from plm.model import MATURITY_RANK

BLOCKING = "Bloquant"
WARNING = "Attention"
INFO = "Info"

MISSING = "Données manquantes ou vides"
PARENT_CHILD = "Cohérence parent-enfant"
INCONSISTENT = "Incohérence"
SUPPLY = "Approvisionnement"
STRUCTURE = "Structure"
NAMING = "Nommage"

CONTROL_DOMAINS = (MISSING, PARENT_CHILD)
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


def finding(rule, severity, domain, product, message, element=None, field=None):
    return {"rule": rule, "severity": severity, "domain": domain, "product_id": product["xml_id"], "name": product["name"], "message": message, "element": element, "field": field, "generated": True}


def is_control(found):
    return found["domain"] in CONTROL_DOMAINS


def control_findings(findings):
    return [f for f in findings if is_control(f)]


def filled(value):
    return value not in (None, "", [])


def field_completeness(model):
    """Taux de remplissage de chaque champ, par type d'objet du XML."""
    products = list(model.products.values())
    reps = [p["rep_3d"] for p in model.parts if p.get("rep_3d")]

    def key(name):
        return lambda item: item.get(name)

    def priced(part):
        return any("unit_price_eur" in link for link in model.active_links(part)) or None

    def complete_history(part):
        return len(part["revisions"]) == part["revision_index"] or None

    groups = [
        ("Pièces 3D", model.parts, [("Nom", key("name")), ("ID PLM", key("plm_id")), ("Description", key("description")), ("Révision", key("revision")), ("Maturité", key("maturity")),
                                    ("Cycle de vie", key("lifecycle")), ("Masse", key("mass_kg")), ("Matériau", key("material")), ("Propriétaire", key("owner")),
                                    ("Date de création", key("created")), ("Date de modification", key("modified")), ("Représentation 3D", key("rep_3d"))]),
        ("Engineering Items", [p for p in products if p["kind"] == "wrapper"], [("Nom", key("name")), ("ID PLM", key("plm_id")), ("Description", key("description")), ("Révision", key("revision")),
                                                                                ("Maturité", key("maturity")), ("Masse", key("mass_kg")), ("Matériau", key("material"))]),
        ("Assemblages", [p for p in products if p["kind"] == "assembly"], [("Nom", key("name")), ("ID PLM", key("plm_id")), ("Description", key("description")), ("Révision", key("revision")),
                                                                           ("Maturité", key("maturity")), ("Masse", key("mass_kg"))]),
        ("Instances", model.instances, [("ID", key("plm_id")), ("Nom", key("name")), ("Description", key("description"))]),
        ("Représentations 3D", reps, [("Nom", key("name")), ("ID PLM", key("plm_id")), ("Description", key("description"))]),
        ("Pièces physiques, extension", model.physical_parts, [("Fournisseur", key("sourcing")), ("Prix fournisseur", priced), ("Historique de révision complet", complete_history), ("Matière consommée", key("usage_kg")), ("Procédé et complexité", key("process"))]),
    ]
    rows = []
    for group, items, fields in groups:
        for name, getter in fields:
            count = sum(1 for item in items if filled(getter(item)))
            rows.append({"object": group, "field": name, "filled": count, "total": len(items), "rate": count / len(items) if items else 1.0})
    return rows


def parent_child_links(model):
    """Compare la maturité de chaque parent à celle de ses enfants directs, tels que déclarés dans le XML."""
    checked = 0
    issues = []
    for parent in model.products.values():
        for reference in parent["children"]:
            child = model.products[reference["product"]]
            checked += 1
            parent_rank, child_rank = MATURITY_RANK[parent["maturity"]], MATURITY_RANK[child["maturity"]]
            names = parent["display_name"], child["display_name"]
            if child["maturity"] == "OBSOLETE" and parent["maturity"] != "OBSOLETE":
                rule, problem = "obsolete_in_bom", "Enfant obsolète encore utilisé"
                message = f"{names[0]} ({parent['maturity']}) utilise encore {names[1]}, OBSOLETE, {reference['quantity']} fois."
            elif parent_rank >= MATURITY_RANK["FROZEN"] and child_rank < parent_rank:
                if parent["kind"] == "wrapper":
                    rule, problem = "ei_above_3d", "Engineering Item plus avancé que sa pièce 3D"
                    message = f"L'Engineering Item {names[0]} est {parent['maturity']} alors que sa pièce 3D est {child['maturity']}."
                    names = f"{names[0]} (Engineering Item)", f"{names[1]} (pièce 3D)"
                else:
                    rule, problem = "maturity_parent_above_child", "Parent plus avancé que son enfant"
                    message = f"{names[0]} est {parent['maturity']} alors que son enfant {names[1]} est {child['maturity']}."
            else:
                continue
            issues.append({"parent_id": parent["xml_id"], "parent": names[0], "parent_maturity": parent["maturity"], "child_id": child["xml_id"], "child": names[1],
                           "child_maturity": child["maturity"], "gap": max(parent_rank - child_rank, 0), "rule": rule, "problem": problem, "message": message})
    return {"checked": checked, "issues": sorted(issues, key=lambda row: (-row["gap"], row["parent"]))}


def check_parent_child(model):
    """Une alerte par lien incohérent : elle s'affiche sur la fiche de l'enfant comme sur celle du parent."""
    found = []
    for link in parent_child_links(model)["issues"]:
        alert = finding(link["rule"], BLOCKING, PARENT_CHILD, model.products[link["child_id"]], link["message"])
        alert["related"] = link["parent_id"]
        found.append(alert)
    return found


def check_lifecycle(model):
    found = []
    for part in model.parts:
        maturity = part["maturity"]
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
    # Champs requis : les libellés et messages sont produits par les règles,
    # jamais par une éventuelle section d'alertes du XML.
    for product in model.products.values():
        for key, label in (("name", "Nom"), ("plm_id", "ID PLM"), ("revision", "Révision"),
                           ("maturity", "Maturité"), ("owner", "Propriétaire"), ("created", "Date de création"), ("modified", "Date de modification")):
            if not filled(product.get(key)):
                found.append(finding(f"missing_{key}", WARNING, MISSING, product, f"{label} non renseigné(e).", field=label))
    for part in model.physical_parts:
        if not part["sourcing"]:
            found.append(finding("missing_supplier", BLOCKING, MISSING, part, "Aucun fournisseur désigné.", field="Fournisseur"))
        elif not any("unit_price_eur" in l for l in model.active_links(part)):
            found.append(finding("missing_price", WARNING, MISSING, part, "Prix fournisseur non renseigné : le coût affiché est une estimation.", field="Prix fournisseur"))
        if not part["material"]:
            found.append(finding("missing_material", BLOCKING, MISSING, part, "Matériau non renseigné.", field="Matériau"))
        if not part["mass_kg"]:
            found.append(finding("missing_mass", BLOCKING, MISSING, part, "Masse non renseignée.", field="Masse"))
        if not part["description"]:
            found.append(finding("missing_description", INFO, MISSING, part, "Description vide.", field="Description"))
        if len(part["revisions"]) != part["revision_index"]:
            found.append(finding("missing_history", WARNING, MISSING, part,
                                 f"Historique incomplet : {len(part['revisions'])} révisions tracées pour la révision {part['revision']}.", field="Historique"))
    for product in model.products.values():
        if product["kind"] == "assembly" and not product["description"]:
            found.append(finding("missing_description", INFO, MISSING, product, "Description vide.", field="Description"))

    # Un champ vide sur tout un type d'objet donne une seule alerte, pas une par objet.
    for row in field_completeness(model):
        if row["object"] in ("Engineering Items", "Instances", "Représentations 3D") and row["filled"] < row["total"]:
            empty = row["total"] - row["filled"]
            found.append(finding("empty_field_group", INFO, MISSING, model.tree.product,
                                 f"Champ {row['field']} vide sur {empty} objets sur {row['total']}.", element=row["object"], field=row["field"]))

    organizations = {p["organization"] for p in model.products.values()}
    if organizations == {"Company Name"}:
        found.append(finding("placeholder_metadata", INFO, MISSING, model.tree.product,
                             "Valeur générique « Company Name » sur tous les produits.", element="Tous les produits", field="Organisation"))
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

    emotor = next((node for node in model.nodes.values() if node.is_assembly and "emotor" in node.label.lower()), None)
    if emotor is None:
        return found
    names = " ".join(n.label.lower() for n in emotor.leaves())
    if not re.search(r"rotor|magnet|aimant", names):
        found.append(finding("structure_gap", WARNING, STRUCTURE, emotor.product,
                             "Aucun rotor ni aimant dans la nomenclature du moteur : export partiel ou structure incomplète. Masse, coût et risques terres rares ne sont pas couverts."))
    return found


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


def run_checks(model):
    found = (check_parent_child(model) + check_missing_data(model) + check_lifecycle(model) + check_supply(model)
             + check_structure(model) + check_parser_warnings(model))
    return sorted(found, key=lambda f: (SEVERITY_RANK[f["severity"]], f["domain"], f["name"]))


def counts(findings):
    return {severity: sum(1 for f in findings if f["severity"] == severity) for severity in SEVERITY_RANK}
