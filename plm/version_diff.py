"""Comparaison factuelle de deux exports, sans modifier les données étudiées."""
import json
from xml.etree import ElementTree as ET


class IncompatibleFormat(ValueError):
    """Le document n'utilise pas la structure du fichier de référence."""


def validate_format(reference_bytes, candidate_bytes):
    """Compare le format, indépendamment des valeurs, de l'ordre et des quantités."""
    def signature(payload):
        root = ET.fromstring(payload)
        paths = set()

        def visit(element, parent=()):
            path = (*parent, element.tag)
            paths.add((path, tuple(sorted(element.attrib))))
            for child in element:
                visit(child, path)

        visit(root)
        return root.tag, root.get("schemaVersion"), paths

    try:
        if signature(reference_bytes) != signature(candidate_bytes):
            raise IncompatibleFormat("Le format du fichier est incompatible.")
    except (ET.ParseError, RecursionError) as error:
        raise IncompatibleFormat("Le format du fichier est incompatible.") from error


LABELS = {
    "mass_kg": "Masse (kg)", "material": "Matériau", "maturity": "Maturité",
    "revision": "Révision", "revision_index": "Indice de révision", "name": "Nom",
    "description": "Description", "sourcing": "Approvisionnement", "revisions": "Historique",
    "children": "Composition", "parents": "Assemblages parents", "instances": "Positions et quantités",
    "supplier_data": "Données fournisseurs", "material_data": "Données matériau",
    "interfaces": "Interfaces", "unit_price_eur": "Coût unitaire (€)", "share_pct": "Part (%)",
    "qualification": "Qualification", "quantity": "Quantité", "criticality": "Classe",
    "modified": "Date de modification", "maturity_date": "Date de maturité", "ppap_date": "Date de qualification",
}
IGNORED = {"xml_id", "warnings", "display_name", "material_family", "kind"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def project(data):
    products = data["products"]
    identities = [p.get("plm_id") for p in products.values()]
    if not all(identities) or len(set(identities)) != len(identities):
        raise ValueError("Chaque produit doit avoir un identifiant PLM renseigné et unique pour être comparé.")
    refs = {key: p["plm_id"] for key, p in products.items()}

    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items() if key not in IGNORED}
        if isinstance(value, list):
            return sorted((normalize(item) for item in value), key=canonical)
        return refs.get(value, value) if isinstance(value, str) else value

    enrichment = data.get("enrichment") or {}
    suppliers = {s["id"]: s for s in enrichment.get("suppliers", [])}
    materials = {m["plm_name"]: m for m in enrichment.get("materials", [])}
    result = {}
    for xml_id, product in products.items():
        item = dict(product)
        item["instances"] = [i for i in data["instances"] if i["child"] == xml_id]
        item["supplier_data"] = {link["supplier"]: suppliers.get(link["supplier"], {}) for link in product["sourcing"]}
        item["material_data"] = materials.get(product.get("material"), {})
        item["interfaces"] = [i for i in enrichment.get("interfaces", []) if xml_id in i.values()]
        result[product["plm_id"]] = normalize(item)
    return result


def flatten(value, prefix=""):
    if isinstance(value, dict) and value:
        return {path: item for key, child in value.items() for path, item in flatten(child, f"{prefix} / {LABELS.get(key, key)}".strip(" / ")).items()}
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        # Identifie chaque source, révision ou position pour montrer ses champs séparément.
        for key in ("supplier", "plm_id", "option_id", "product", "name", "id"):
            if all(key in item for item in value) and len({canonical(item[key]) for item in value}) == len(value):
                return flatten({str(item[key]): item for item in value}, prefix)
    # Les autres listes sont comparées comme des ensembles ordonnés par canonicalisation.
    return {prefix: value}


def display(value, present=True):
    if not present:
        return "Absent"
    if value is None:
        return "Non renseigné"
    if isinstance(value, (dict, list)):
        return canonical(value)
    return str(value)


def compare(reference, candidate):
    before, after = project(reference), project(candidate)
    rows = []
    for identity in sorted(before.keys() | after.keys()):
        old, new = before.get(identity), after.get(identity)
        status = "Ajouté" if old is None else "Supprimé" if new is None else "Inchangé"
        a, b = flatten(old) if old is not None else {}, flatten(new) if new is not None else {}
        changes = []
        for field in sorted(a.keys() | b.keys()):
            if a.get(field) == b.get(field) and (field in a) == (field in b):
                continue
            left, right = a.get(field), b.get(field)
            delta = round(right - left, 6) if type(left) in (float, int) and type(right) in (float, int) else None
            changes.append({"Champ": field, "Référence": display(left, field in a), "Comparaison": display(right, field in b), "Écart numérique": delta})
        if status == "Inchangé" and changes:
            status = "Modifié"
        product = new if new is not None else old
        rows.append({"id": identity, "name": product.get("name", identity), "kind": next((p["kind"] for p in (candidate if new is not None else reference)["products"].values() if p["plm_id"] == identity), "part"), "status": status, "changes": changes})
    return rows


def compare_context(reference, candidate):
    """Les hypothèses programme et en-têtes ne sont pas rattachés à une pièce."""
    def context(data):
        ext = data.get("enrichment") or {}
        return {"En-tête": data.get("header", {}), "Programme": ext.get("program", {}),
                "Fournisseurs": sorted(ext.get("suppliers", []), key=canonical),
                "Matériaux": sorted(ext.get("materials", []), key=canonical),
                "Types d’interface": sorted(ext.get("interface_types", []), key=canonical)}
    a, b = flatten(context(reference)), flatten(context(candidate))
    return [{"Champ": key, "Référence": display(a.get(key), key in a), "Comparaison": display(b.get(key), key in b)}
            for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key) or (key in a) != (key in b)]
