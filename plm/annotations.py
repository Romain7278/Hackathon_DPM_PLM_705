"""Textes factuels calculés à partir des données courantes, sans commentaire XML."""
from plm.fmt import kg
from plm.model import MATURITY_RANK, QUALIFIED


def supplier_note(model, part):
    if not part.get("physical", True):
        return "Géométrie d'étude : aucun approvisionnement attendu."
    links = part.get("sourcing", [])
    if not links:
        return "Aucun fournisseur désigné ; approvisionnement à définir."
    qualified = model.qualified_links(part)
    if not qualified:
        summary = "Aucune source qualifiée."
    elif len(qualified) == 1:
        summary = "Une seule source qualifiée : dépendance à un fournisseur unique."
    else:
        summary = f"{len(qualified)} sources qualifiées : approvisionnement diversifié."
    candidates = [link for link in links if link["qualification"] not in QUALIFIED]
    if candidates:
        delay = min(link["requal_weeks"] + link["ramp_up_weeks"] for link in candidates)
        summary += f" {len(candidates)} alternative(s) non qualifiée(s) ; qualification et montée en cadence en {delay} semaines au mieux."
    elif len(links) <= 1:
        summary += " Aucune alternative référencée."
    primary = model.primary_link(part)
    if primary and model.suppliers[primary["supplier"]]["financial_rating"] == "C":
        summary += " Le fournisseur principal présente une notation financière C (fragile)."
    return summary


def maturity_note(model, product):
    maturity = product["maturity"]
    children = [model.products[child["product"]] for child in product["children"]]
    facts = [f"Maturité actuelle : {maturity}."]
    if maturity == "OBSOLETE":
        facts.append("Référence obsolète : son utilisation en production doit être revue.")
    if children:
        obsolete = sum(child["maturity"] == "OBSOLETE" for child in children)
        behind = sum(MATURITY_RANK[child["maturity"]] < MATURITY_RANK[maturity] for child in children)
        if obsolete and maturity != "OBSOLETE":
            facts.append(f"{obsolete} composant(s) direct(s) obsolète(s) encore référencé(s).")
        if behind and maturity in ("FROZEN", "RELEASED"):
            facts.append(f"{behind} composant(s) direct(s) moins avancé(s) que le parent.")
        elif not obsolete:
            facts.append("Aucun écart de maturité bloquant détecté avec les composants directs.")
    if maturity in ("FROZEN", "RELEASED") and product.get("maturity_date") and product["modified"][:10] > product["maturity_date"]:
        facts.append("Une modification est datée après le passage à cette maturité ; la traçabilité est à vérifier.")
    return " ".join(facts)


def revision_history(part):
    """Compare les masses et matériaux des états historiques disponibles."""
    rows = []
    previous = None
    for revision in part.get("revisions", []):
        row = {key: value for key, value in revision.items() if key != "reason"}
        changes = []
        if previous is None:
            text = "Premier état disponible dans l'historique."
            if revision.get("mass_kg") is not None:
                text += f" Masse enregistrée : {kg(revision['mass_kg'])}."
            if revision.get("material"):
                text += f" Matériau enregistré : {revision['material']}."
        else:
            before, after = previous.get("mass_kg"), revision.get("mass_kg")
            if before is not None and after is not None and abs(after - before) > 0.000001:
                delta = round(after - before, 3)
                changes.append(f"Masse : {kg(before)} → {kg(after)} ({'+' if delta > 0 else ''}{kg(delta)})")
            before_material, after_material = previous.get("material"), revision.get("material")
            if before_material and after_material and before_material != after_material:
                changes.append(f"Matériau : {before_material} → {after_material}")
            text = f"Par rapport à la révision {previous['name']} : " + "; ".join(changes) + "." if changes else "Aucun écart mesurable dans les champs comparables."
        row["reason"] = text
        rows.append(row)
        previous = revision
    return rows
