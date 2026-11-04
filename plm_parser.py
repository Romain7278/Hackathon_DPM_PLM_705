"""Convertit l'export PLM 3DEXPERIENCE (XPDMXML) en un JSON simple à exploiter.

Usage : python plm_parser.py [fichier.xml] [sortie.json]
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_XML = HERE / "Hackathon dataset" / "XPDMXML_ECAR_PLM.xml"
DEFAULT_OUT = HERE / "plm_data.json"

NS = "{http://www.3ds.com/xsd/XPDMXML}"
EXT = "{urn:esilv-hackathon:plm-enrichment:v1}"
MASS_TAG = "WCGEquivalentComputedExt.V_WCG_Mass"

# L'ordre compte : "steel" reste en dernier, car d'autres libellés contiennent ce mot
# (ex. "FKM fluoroelastomer (steel-reinforced)").
MATERIAL_FAMILIES = [
    ("aluminium", "Aluminium"),
    ("electrical steel", "Acier électrique"),
    ("polyamide", "Polymère"),
    ("fluoroelastomer", "Polymère"),
    ("cast iron", "Fonte"),
    ("copper", "Cuivre"),
    ("steel", "Acier"),
]


def text(element, tag):
    """Texte d'une balise enfant, ou None si elle est absente ou vide."""
    value = element.findtext(NS + tag)
    return value.strip() if value and value.strip() else None


def numbers(value):
    return [float(x) for x in value.split()]


def display_name(name):
    """Nom lisible : sans préfixe ECAR-EI_ / ECAR-3D_ / 01_ ni séparateurs parasites."""
    stem = re.sub(r"^ECAR-(EI|3D)[_ ]*(01_)?", "", name)
    return re.sub(r"[_\s]+", " ", stem).strip()


def material_family(material):
    if not material:
        return None
    lowered = material.lower()
    return next((family for key, family in MATERIAL_FAMILIES if key in lowered), "Autre")


def parse_product(element):
    name = text(element, "Name")
    material = text(element, "Material")
    return {
        "xml_id": element.get("id"),
        "plm_id": text(element, "ID"),
        "name": name,
        "display_name": display_name(name),
        "description": text(element, "Description"),
        "revision": text(element, "RevisionName"),
        "revision_index": int(text(element, "RevisionIndex")),
        "revision_family": text(element, "RevisionFamily"),
        "maturity": text(element, "Maturity"),
        "lifecycle": text(element, "Lifecycle"),
        "mass_kg": float(text(element, MASS_TAG)),
        "material": material,
        "material_family": material_family(material),
        "created": text(element, "TimeCreated"),
        "modified": text(element, "TimeModified"),
        "owner": text(element, "Owner"),
        "organization": text(element, "Organization"),
        "project": text(element, "Project"),
        "rep_3d": None,
        "children": [],
        "parents": [],
        "warnings": [],
        "sourcing": [],
        "revisions": [],
        "mass_options": [],
    }


def parse_instance(element):
    transform = element.find(NS + "RelativeTransformation3D")
    return {
        "xml_id": element.get("id"),
        "plm_id": text(element, "ID"),
        "parent": text(element, "Owned"),
        "child": text(element, "Instancing"),
        "name": text(element, "Name"),
        "description": text(element, "Description"),
        "order": float(text(element, "ChildOrder")),
        "translation": numbers(text(transform, "Translation3D")),
        "rotation": numbers(text(transform, "Rotation3D")),
    }


def parse_rep_3d(element):
    return {
        "owner": text(element, "Owned"),
        "xml_id": element.get("id"),
        "plm_id": text(element, "ID"),
        "name": text(element, "Name"),
        "description": text(element, "Description"),
        "revision": text(element, "RevisionName"),
    }


def link_structure(products, instances):
    """Regroupe les instances : une vis posée 13 fois devient un enfant de quantité 13."""
    counts = defaultdict(Counter)
    for instance in sorted(instances, key=lambda i: i["order"]):
        counts[instance["parent"]][instance["child"]] += 1

    for parent_id, children in counts.items():
        for child_id, quantity in children.items():
            products[parent_id]["children"].append({"product": child_id, "quantity": quantity})
            products[child_id]["parents"].append(parent_id)


def product_kind(product):
    """part = pièce 3D, wrapper = EI qui enveloppe une pièce, assembly = vrai sous-ensemble."""
    if not product["children"]:
        return "part"
    return "wrapper" if product["material"] else "assembly"


def add_warnings(products):
    """Alertes de qualité de données, à afficher sans jamais corriger la source."""
    same_name = defaultdict(list)
    spellings = defaultdict(set)
    for product in products.values():
        same_name[product["name"]].append(product)
        spellings[re.sub(r"\s", "", product["name"]).lower()].add(product["name"])
    lowered_names = {product["name"].lower() for product in products.values()}

    for product in products.values():
        name = product["name"]
        found = []
        if len(same_name[name]) > 1:
            found.append(("shared_name", f"Nom porté par {len(same_name[name])} produits distincts : "
                                         "ce sont des pièces différentes, pas des versions."))
        for other in sorted(spellings[re.sub(r"\s", "", name).lower()] - {name}):
            found.append(("near_duplicate_name", f"Nom quasi identique à « {other} » : seuls les espaces diffèrent."))
        if not re.match(r"ECAR-(EI|3D)_\S", name):
            found.append(("irregular_name", "Nom hors de la convention ECAR-EI_ / ECAR-3D_."))
        if "meshing" in (product["description"] or "").lower():
            found.append(("meshing_aid", "Géométrie d'aide au maillage selon sa description : probablement pas "
                                         "une pièce physique, mais sa masse est comptée dans le total."))
        if name.lower() + "s" in lowered_names:
            found.append(("possible_double_count", f"Semble être l'unité de « {product['display_name']}s » : "
                                                   "double comptage possible dans la masse, à vérifier."))
        if product["display_name"].lower() == "motor":
            found.append(("misleading_name", "Nom trompeur : pièce du carter en aluminium, probablement le carter "
                                             "moteur. Le moteur complet est EMOTOR FRONT."))
        if product["kind"] == "part" and any(products[p]["kind"] == "assembly" for p in product["parents"]):
            found.append(("missing_wrapper", "Pièce 3D rattachée directement à l'assemblage, sans Engineering Item."))
        product["warnings"] = [{"code": code, "message": message} for code, message in found]


def explode_bom(products, root_id):
    """Nomenclature à plat. Seules ces pièces s'additionnent : la masse et le matériau
    sont répétés sur les wrappers et les assemblages."""
    bom = {}

    def walk(product_id, quantity, path):
        product = products[product_id]
        path = path + [product_id]
        if product["children"]:
            for child in product["children"]:
                walk(child["product"], quantity * child["quantity"], path)
            return
        line = bom.setdefault(product_id, {
            "product": product_id,
            "plm_id": product["plm_id"],
            "name": product["name"],
            "display_name": product["display_name"],
            "material": product["material"],
            "material_family": product["material_family"],
            "revision": product["revision"],
            "maturity": product["maturity"],
            "unit_mass_kg": product["mass_kg"],
            "quantity": 0,
            "occurrences": [],
        })
        line["quantity"] += quantity
        line["occurrences"].append({"path": path, "quantity": quantity})

    walk(root_id, 1, [])
    for line in bom.values():
        line["total_mass_kg"] = round(line["unit_mass_kg"] * line["quantity"], 3)
    return list(bom.values())


def coerce(value):
    if value in ("true", "false"):
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def snake_case(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def ext_attrs(element):
    return {snake_case(key): coerce(value) for key, value in element.attrib.items()}


def parse_enrichment(root, products):
    """Lit la section ext:Enrichment du XML enrichi. Renvoie None pour un export d'origine."""
    enrichment = root.find(EXT + "Enrichment")
    if enrichment is None:
        return None

    for part in enrichment.find(EXT + "PartData"):
        attrs = ext_attrs(part)
        product = products[attrs.pop("ref")]
        attrs.pop("plm_id", None)
        attrs.pop("name", None)
        # Les constats affichés sont recalculés par l'application.
        for computed in ("reasons", "reason", "alerts", "warnings", "controls", "findings", "score", "risk_score", "sourcing_note", "blocking", "maturity_note"):
            attrs.pop(computed, None)
        product.update(attrs)
        product["sourcing"] = [ext_attrs(e) for e in part.findall(EXT + "Sourcing")]
        product["revisions"] = [{key: value for key, value in ext_attrs(e).items() if key != "reason"} for e in part.findall(EXT + "Revision")]
        product["mass_options"] = [ext_attrs(e) for e in part.findall(EXT + "MassOption")]

    def section(tag):
        element = enrichment.find(EXT + tag)
        return [ext_attrs(e) for e in element] if element is not None else []

    return {
        **ext_attrs(enrichment),
        "program": {snake_case(p["name"]): p["value"] for p in section("Program")},
        "materials": section("Materials"),
        "suppliers": section("Suppliers"),
        "interface_types": section("InterfaceTypes"),
        "interfaces": section("Interfaces"),
    }


def parse_plm(xml_path):
    root = ET.parse(xml_path).getroot()
    structure = root.find(NS + "ProductStructure")
    if structure is None or not structure.get("rootRefs"):
        raise ValueError("Structure produit XPDMXML absente ou référence racine manquante.")
    root_id = structure.get("rootRefs")

    products = {e.get("id"): parse_product(e) for e in structure.findall(NS + "Product")}
    instances = [parse_instance(e) for e in structure.findall(NS + "ProductInst")]

    for element in structure.findall(NS + "Rep3DAggr"):
        rep = parse_rep_3d(element)
        products[rep.pop("owner")]["rep_3d"] = rep

    link_structure(products, instances)
    for product in products.values():
        product["kind"] = product_kind(product)
    add_warnings(products)
    enrichment = parse_enrichment(root, products)

    return {
        "source_file": Path(xml_path).name,
        "header": {i.get("name"): i.get("value") for i in root.find(NS + "InfoHeader")},
        "root": root_id,
        "products": products,
        "instances": instances,
        "bom": explode_bom(products, root_id),
        "enrichment": enrichment,
    }


def main():
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XML
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

    data = parse_plm(xml_path)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    root = data["products"][data["root"]]
    pieces = sum(line["quantity"] for line in data["bom"])
    mass = sum(line["total_mass_kg"] for line in data["bom"])
    print(f"Racine : {root['name']} (revision {root['revision']})")
    print(f"{len(data['products'])} produits, {len(data['instances'])} instances")
    print(f"{pieces} pieces, {len(data['bom'])} references")
    print(f"Masse calculee : {mass:.3f} kg / declaree : {root['mass_kg']:.3f} kg")
    print(f"Ecrit : {out_path}")


if __name__ == "__main__":
    main()
