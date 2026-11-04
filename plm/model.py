"""Modèle de données du dashboard : arbre d'affichage, coûts, sources, relations et positions."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from difflib import get_close_matches
from pathlib import Path

import numpy as np

from plm_parser import parse_plm

DATA_XML = Path(__file__).resolve().parent.parent / "data" / "XPDMXML_ECAR_PLM_ENRICHED.xml"

MATURITY_RANK = {"OBSOLETE": -1, "PRIVATE": 0, "IN_WORK": 1, "FROZEN": 2, "RELEASED": 3}
QUALIFIED = ("APPROVED", "CONDITIONAL")
QUALIFICATION_LABELS = {
    "APPROVED": "PPAP approuvé",
    "CONDITIONAL": "PPAP à refaire (rév. courante)",
    "IN_PROGRESS": "PPAP en cours",
    "NOT_STARTED": "Non qualifié",
}
CLAUSE_LABELS = {"INDEX_M": "Indexé au mois", "INDEX_Q": "Indexé au trimestre", "FIXED": "Prix fixe"}
FEASIBILITY_LABELS = {"HIGH": "Élevée", "MEDIUM": "Moyenne", "LOW": "Faible"}
FEASIBILITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# Ordre fixe (par masse décroissante) : une famille garde sa couleur quels que soient les filtres.
FAMILIES = ["Acier", "Aluminium", "Acier électrique", "Cuivre", "Fonte", "Polymère"]

# Termes métier pour retrouver une pièce depuis une question en langage naturel.
PART_ALIASES = {
    "ID_14": ["paquet de toles", "toles", "tole", "stator core", "noyau stator", "circuit magnetique"],
    "ID_16": ["bobinage", "bobines", "stator coils", "epingles", "hairpin"],
    "ID_5": ["arbre rapide", "high speed shaft", "arbre moteur", "hsh"],
    "ID_7": ["chemise", "refroidissement", "machine cooling"],
    "ID_3": ["roulement arriere", "hsh bea3", "roulement hybride", "roulement ceramique"],
    "ID_30": ["hsh bea1"],
    "ID_32": ["hsh bea2"],
    "ID_34": ["lsh bea1", "roulement de sortie"],
    "ID_36": ["lsh bea2"],
    "ID_38": ["ish bea1"],
    "ID_40": ["ish bea2"],
    "ID_42": ["pignon d'entree", "gear wheel a"],
    "ID_44": ["roue du 1er etage", "gear wheel c"],
    "ID_46": ["pignon du 2e etage", "gear wheel b"],
    "ID_48": ["couronne", "ring gear", "gear wheel d"],
    "ID_50": ["arbre intermediaire", "ish"],
    "ID_20": ["boitier de differentiel", "differential casing", "differential casting"],
    "ID_22": ["axe de satellites"],
    "ID_24": ["satellite", "bevel"],
    "ID_26": ["planetaire", "side shaft"],
    "ID_53": ["joint a levre", "joint spi", "spy joint", "joint"],
    "ID_55": ["demi-carter gauche", "carter gauche", "left housing"],
    "ID_57": ["demi-carter droit", "carter droit", "right housing"],
    "ID_59": ["logement de roulement", "bearing housing"],
    "ID_61": ["carter moteur", "motor housing"],
    "ID_63": ["flasque", "plate bearing"],
    "ID_65": ["support de transmission", "transmission support"],
    "ID_67": ["raccord", "tuyau", "pipe"],
    "ID_71": ["vis m8", "screw d8"],
    "ID_78": ["vis m10 x 155", "screw d10 l155"],
    "ID_69": ["vis m10 x 115", "screw d10 l115"],
}
ASSEMBLY_ALIASES = {
    "ID_0": ["e-drive", "edrive", "produit"],
    "ID_1": ["moteur", "emotor", "e-moteur"],
    "ID_8": ["stator"],
    "ID_17": ["reducteur", "reducer"],
    "ID_18": ["differentiel", "differential"],
    "ID_51": ["carters", "carter", "housing"],
}
FAMILY_ALIASES = {
    "Acier électrique": ["acier electrique", "electrical steel", "tole", "toles", "m235"],
    "Cuivre": ["cuivre", "copper"],
    "Aluminium": ["aluminium", "alu ", "aluminum", "alsi"],
    "Fonte": ["fonte", "cast iron"],
    "Polymère": ["polymere", "plastique", "polyamide", "fkm"],
    "Acier": ["acier", "steel"],
}


def normalize(text):
    text = unicodedata.normalize("NFD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower().replace("_", " ")).strip()


@dataclass(eq=False)
class Node:
    """Ligne de l'arbre d'affichage : une enveloppe EI et sa pièce 3D forment une seule ligne."""

    id: str
    product: dict
    wrapper: dict | None
    parent: "Node | None"
    label: str
    depth: int
    quantity: int
    abs_quantity: int
    children: list = field(default_factory=list)

    @property
    def is_assembly(self):
        return self.product["kind"] == "assembly"

    @property
    def part_id(self):
        return self.product["xml_id"]

    @property
    def unit_mass(self):
        return self.product["mass_kg"]

    @property
    def total_mass(self):
        return self.unit_mass * self.abs_quantity

    def path(self):
        steps = []
        node = self
        while node:
            steps.append(node)
            node = node.parent
        return steps[::-1]

    def leaves(self):
        return [self] if not self.is_assembly else [leaf for child in self.children for leaf in child.leaves()]

    def top_level(self):
        path = self.path()
        return path[1] if len(path) > 1 else self


class PlmModel:
    def __init__(self, data):
        self.data = data
        self.products = data["products"]
        self.instances = data["instances"]
        self.bom = {line["product"]: line for line in data["bom"]}
        enrichment = data["enrichment"]
        self.enrichment = enrichment
        self.program = enrichment["program"]
        self.suppliers = {s["id"]: s for s in enrichment["suppliers"]}
        self.materials = {m["plm_name"]: m for m in enrichment["materials"]}
        self.interface_types = {t["id"]: t for t in enrichment["interface_types"]}
        self.scenarios = {s["id"]: s for s in enrichment["scenarios"]}

        self.tree = self._build_node(data["root"], 1, None)
        self.nodes = {}
        self.nodes_by_part = {}
        self._index(self.tree)
        self.leaves = self.tree.leaves()
        self._shared_labels = {}
        for nodes in self.nodes_by_part.values():
            self._shared_labels[nodes[0].label] = self._shared_labels.get(nodes[0].label, 0) + 1
        self.parts = [self.products[part_id] for part_id in self.bom]
        self.physical_parts = [p for p in self.parts if p.get("physical", True)]

        self.interfaces_by_part = {}
        for interface in enrichment["interfaces"]:
            self.interfaces_by_part.setdefault(interface["first"], []).append({**interface, "other": interface["second"]})
            self.interfaces_by_part.setdefault(interface["second"], []).append({**interface, "other": interface["first"]})

        self.positions = self._absolute_positions()
        self.findings = []

    def _build_node(self, product_id, quantity, parent):
        source = self.products[product_id]
        wrapper = source if source["kind"] == "wrapper" else None
        product = self.products[wrapper["children"][0]["product"]] if wrapper else source
        node_quantity = quantity * wrapper["children"][0]["quantity"] if wrapper else quantity
        node = Node(
            id=source["xml_id"],
            product=product,
            wrapper=wrapper,
            parent=parent,
            label=source["display_name"],
            depth=parent.depth + 1 if parent else 0,
            quantity=node_quantity,
            abs_quantity=(parent.abs_quantity if parent else 1) * node_quantity,
        )
        if node.is_assembly:
            node.children = [self._build_node(c["product"], c["quantity"], node) for c in product["children"]]
        return node

    def _index(self, node):
        self.nodes[node.id] = node
        self.nodes_by_part.setdefault(node.part_id, []).append(node)
        for child in node.children:
            self._index(child)

    def _absolute_positions(self):
        """Positions absolues des instances en mm. Rotation3D est donnée par colonnes dans le XPDM :
        avec cette convention, le différentiel tombe bien sur l'axe de sortie du réducteur."""
        by_parent = {}
        for instance in self.instances:
            by_parent.setdefault(instance["parent"], []).append(instance)
        positions = {}

        def visit(product_id, rotation, translation):
            for instance in by_parent.get(product_id, []):
                position = translation + rotation @ np.array(instance["translation"])
                positions.setdefault(instance["child"], []).append((position * 1000).round(1).tolist())
                visit(instance["child"], rotation @ np.array(instance["rotation"]).reshape(3, 3).T, position)

        visit(self.data["root"], np.eye(3), np.zeros(3))
        return positions

    # Dates
    @property
    def reference_date(self):
        return date.fromisoformat(self.program["reference_date"])

    @property
    def weeks_to_sop(self):
        return (date.fromisoformat(self.program["sop_date"]) - self.reference_date).days / 7

    # Quantités et coûts
    def quantity(self, part_id):
        return self.bom[part_id]["quantity"]

    def material_of(self, part):
        return self.materials.get(part["material"])

    def material_cost(self, part):
        material = self.material_of(part)
        return part["usage_kg"] * material["price_eur_kg"] if material and part.get("usage_kg") else 0.0

    def should_cost(self, part):
        if not part.get("usage_kg"):
            return None
        return self.material_cost(part) + part.get("conversion_eur", 0.0)

    def unit_cost(self, part):
        """Renvoie (coût unitaire, nature). Sans prix fournisseur, on retient l'estimation matière + conversion."""
        priced = [(l["share_pct"], l["unit_price_eur"]) for l in part["sourcing"]
                  if l["share_pct"] > 0 and "unit_price_eur" in l]
        if priced:
            return sum(s * p for s, p in priced) / sum(s for s, _ in priced), "Prix fournisseur"
        estimate = self.should_cost(part)
        if estimate is not None:
            return estimate, "Estimation"
        return 0.0, "Sans objet"

    def line_cost(self, part):
        return self.unit_cost(part)[0] * self.quantity(part["xml_id"])

    def bom_cost(self):
        return sum(self.line_cost(p) for p in self.parts)

    def node_cost(self, node):
        return sum(self.unit_cost(leaf.product)[0] * leaf.abs_quantity for leaf in node.leaves())

    def margin_per_unit(self, bom_cost=None):
        cost = self.bom_cost() if bom_cost is None else bom_cost
        return self.program["selling_price_eur"] - cost - self.program["assembly_test_cost_eur"]

    def annual_spend(self, part):
        return self.line_cost(part) * self.program["annual_volume"]

    # Sources
    def active_links(self, part):
        return [l for l in part["sourcing"] if l["share_pct"] > 0]

    def qualified_links(self, part):
        return [l for l in part["sourcing"] if l["qualification"] in QUALIFIED]

    def primary_link(self, part):
        return max(self.active_links(part), key=lambda l: l["share_pct"], default=None)

    def is_single_source(self, part):
        return len(self.qualified_links(part)) <= 1

    def supplier_parts(self, supplier_id, active_only=True):
        rows = []
        for part in self.physical_parts:
            for link in part["sourcing"]:
                if link["supplier"] == supplier_id and (link["share_pct"] > 0 or not active_only):
                    rows.append((part, link))
        return rows

    # Relations
    def interfaces(self, part_id):
        return self.interfaces_by_part.get(part_id, [])

    def real_interfaces(self, part_id):
        return [i for i in self.interfaces(part_id) if i["type"] != "study"]

    def revalidation_tests(self, part_id):
        """Essais à refaire quand la pièce change : un essai par type d'interface concerné."""
        types = {i["type"] for i in self.real_interfaces(part_id)}
        return [self.interface_types[t] for t in sorted(types)]

    def node_label(self, part_id):
        """Nom sans ambiguïté d'une pièce : quatre pièces s'appellent GEAR WHEEL, une même pièce 3D peut avoir deux EI."""
        nodes = self.nodes_by_part[part_id]
        if len(nodes) > 1:
            return self.products[part_id]["display_name"]
        label = nodes[0].label
        return f"{label} rév. {nodes[0].product['revision']}" if self._shared_labels.get(label, 0) > 1 else label

    def part_label(self, part):
        return part["display_name"]

    def source_ref(self, part_or_id, fields=""):
        """Référence citable d'un produit : ID PLM, ID XML et champs utilisés."""
        part = self.products[part_or_id] if isinstance(part_or_id, str) else part_or_id
        return {"type": "Pièce", "id": part["xml_id"], "plm_id": part["plm_id"], "label": part["name"], "fields": fields}

    def supplier_ref(self, supplier_id, fields=""):
        supplier = self.suppliers[supplier_id]
        return {"type": "Fournisseur", "id": supplier_id, "plm_id": "", "label": supplier["name"], "fields": fields}

    # Recherche
    def find_part(self, text):
        """Retrouve une pièce ou un assemblage par ID, nom ou terme métier. Renvoie une liste de nœuds candidats."""
        raw = str(text).strip()
        if raw in self.nodes:
            return [self.nodes[raw]]
        if raw in self.nodes_by_part:
            return self.nodes_by_part[raw][:1]
        query = normalize(raw)
        for product in self.products.values():
            if normalize(product["plm_id"]) == query:
                found = self.nodes.get(product["xml_id"])
                return [found] if found else self.nodes_by_part[product["xml_id"]][:1]
        same_name = [n for n in self.nodes.values() if query in (normalize(n.product["name"]), normalize(n.wrapper["name"] if n.wrapper else ""))]
        if same_name:
            return same_name

        same_label = [n for n in self.nodes.values() if normalize(n.label) == query]
        if same_label:
            return same_label

        best = []
        best_length = 0
        for aliases, is_assembly in ((PART_ALIASES, False), (ASSEMBLY_ALIASES, True)):
            for product_id, terms in aliases.items():
                for term in terms:
                    if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", query) and len(term) > best_length:
                        best_length = len(term)
                        best = [self.nodes[product_id]] if is_assembly else self.nodes_by_part[product_id][:1]
        for node in self.nodes.values():
            label = normalize(node.label)
            if len(label) > max(best_length, 3) and label in query:
                best_length = len(label)
                best = [node]
        if best:
            return best

        labels = {normalize(n.label): n for n in self.nodes.values()}
        close = get_close_matches(query, list(labels), n=3, cutoff=0.6)
        return [labels[c] for c in close]

    def find_supplier(self, text):
        raw = str(text).strip()
        if raw in self.suppliers:
            return self.suppliers[raw]
        query = normalize(raw)
        for supplier in self.suppliers.values():
            name = normalize(supplier["name"])
            first_word = name.split()[0]
            if name == query or re.search(rf"(?<![a-z0-9]){re.escape(first_word)}(?![a-z0-9])", query):
                return supplier
        return None

    def find_family(self, text):
        query = f"{normalize(text)} "
        for family, terms in FAMILY_ALIASES.items():
            if any(term in query for term in terms):
                return family
        return None

    def materials_of_family(self, family):
        return [m for m in self.materials.values() if m["family"] == family and m["in_bom"]]

    # Espace
    def bounding_box(self):
        points = [p for positions in (self.positions.get(n.part_id, []) for n in self.leaves) for p in positions]
        low = [min(p[i] for p in points) for i in range(3)]
        high = [max(p[i] for p in points) for i in range(3)]
        return [round(h - l) for l, h in zip(low, high)]

    def volume_litres(self, part):
        material = self.material_of(part)
        if not material:
            return None
        return part["mass_kg"] / material["density_kg_dm3"]

    # Alertes
    def findings_for_product(self, product_id):
        return [f for f in self.findings if f["product_id"] == product_id]

    def findings_for_node(self, node):
        ids = {node.part_id, node.id}
        if node.wrapper:
            ids.add(node.wrapper["xml_id"])
        return [f for f in self.findings if f["product_id"] in ids]

    def subtree_findings(self, node):
        found = list(self.findings_for_node(node))
        for child in node.children:
            found.extend(self.subtree_findings(child))
        return found


def load_model(xml_path=DATA_XML):
    from plm.quality import run_checks

    model = PlmModel(parse_plm(xml_path))
    model.findings = run_checks(model)
    return model
