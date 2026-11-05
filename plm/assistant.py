"""Assistant intégré sans dépendance externe, avec modèle Ollama facultatif.

Les sources affichées viennent des outils de calcul PLM réellement exécutés.
"""
import re

from plm import tools, local_llm
from plm.fmt import compact_eur, eur, kg, number, pct, signed_compact_eur, signed_eur
from plm.model import normalize
from plm.tools import ToolError
from plm.chat_queries import SUGGESTIONS, answer_known

SYSTEM_PROMPT = """Tu es l'assistant PLM d'un équipementier qui fournit un e-drive avant de 410 kW à un constructeur automobile (OEM). L'équipementier n'a pas accès au PLM de l'OEM : il travaille à partir d'un export XML.

Règles :
- Toute valeur chiffrée, tout nom de pièce ou de fournisseur doit venir d'un outil. N'invente rien, et appelle les outils utiles avant de répondre.
- Pour une question de scénario (rupture, prix matière, changement de fournisseur, release, masse), utilise l'outil de calcul correspondant plutôt que de raisonner de tête.
- Cite les éléments utilisés avec leur ID PLM (prd-...) ou leur ID fournisseur (SUP-...).
- N'indique pas de toi-même la provenance des données. Si l'utilisateur la demande, réponds franchement : la structure, les masses, les matériaux, les révisions courantes et les positions viennent de l'export de l'OEM ; les coûts, fournisseurs, maturités, dates, historiques, interfaces, complexités et options d'allègement sont des hypothèses de travail, et les fournisseurs et événements sont fictifs.
- Si une donnée manque ou si plusieurs pièces portent le même nom (GEAR WHEEL), dis-le plutôt que de deviner.

Style : réponds en français, en commençant par la conclusion ou la décision à prendre, puis 2 à 5 puces courtes avec les chiffres clés. Pas plus de 150 mots, sauf si on te demande le détail. Montants en euros."""


def dedupe_sources(sources):
    merged = {}
    for source in sources:
        entry = merged.setdefault((source["type"], source["id"]), {**source, "fields": set()})
        entry["fields"].update(f.strip() for f in source.get("fields", "").split(",") if f.strip())
    return [{**entry, "fields": ", ".join(sorted(entry["fields"]))} for entry in merged.values()]


def bullets(lines):
    return "\n".join(f"- {line}" for line in lines)


def plural(count, singular, plural_form=None):
    return f"{number(count)} {singular if count <= 1 else plural_form or singular + 's'}"


def local_critical(model, _question):
    result = tools.critical_parts(model, top=6)
    levels = result["levels"]
    lines = [f"**{p['name']}** : score {p['score']}, {'; '.join(p['reasons'][:2]).lower()}" for p in result["parts"]]
    return f"**{levels['Critique']} composants sont critiques.** Les plus exposés :\n{bullets(lines)}", result["sources"]


def local_disruption(model, question):
    weeks = re.search(r"(\d+)\s*(?:sem|week)", normalize(question))
    weeks = int(weeks.group(1)) if weeks else 8
    supplier = model.find_supplier(question)
    nodes = [n for n in model.find_part(question) if not n.is_assembly]
    if not nodes and supplier:
        active = [p for p, _ in model.supplier_parts(supplier["id"])]
        if active:
            nodes = model.nodes_by_part[max(active, key=model.line_cost)["xml_id"]][:1]
    if not nodes:
        return ("Précisez la pièce touchée, par exemple : « Rupture du paquet de tôles pendant 16 semaines ».", [])
    result = tools.supply_disruption(model, nodes[0].part_id, supplier["id"] if supplier else None, weeks)
    strategies = result["strategies"]
    wait, best = strategies["wait"], strategies[result["best_strategy"]]
    cover = result["cover_days_before_line_stop"]
    lines = [
        f"Couverture avant arrêt de ligne : {number(cover, 0)} jours ouvrés" if cover is not None else "Pas d'arrêt de ligne attendu tant que les autres sources tiennent",
        f"Sans action : {plural(round(wait['lost_units']), 'e-drive perdu', 'e-drives perdus')}, {compact_eur(wait['total_cost'])}",
        f"Meilleure stratégie, {best['label'].lower()} : {plural(round(best['lost_units']), 'e-drive perdu', 'e-drives perdus')}, {compact_eur(best['total_cost'])}",
        *result["recommendations"][:2],
    ]
    return (f"**Arrêt de {result['supplier'].rstrip('.')} pendant {weeks} semaines sur {result['part']}.**\n{bullets(lines)}", result["sources"])


def local_price(model, question):
    query = normalize(question)
    match = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*(?:%|pour ?cent)", query)
    value = float(match.group(1).replace(",", ".")) if match else 10.0
    if re.search(r"baisse|chute|recul|diminu", query) and value > 0:
        value = -value
    family = model.find_family(question)
    if not family:
        return ("Précisez la matière, par exemple : « Impact d'une hausse de 20 % du cuivre ».", [])
    result = tools.material_price(model, family, value)
    lines = [
        f"{plural(result['parts'], 'pièce concernée', 'pièces concernées')}, {kg(result['mass_kg'])}",
        f"{signed_eur(result['delta_unit'], 2)} par e-drive",
        f"Marge : {pct(result['margin_pct_before'], 1)} puis {pct(result['margin_pct_after'], 1)}",
        f"{pct(result['share_within_3_months'])} de l'effet arrive sous 3 mois, selon les clauses de prix",
    ]
    return f"**Indice {family.lower()} {value:+.0f} %.**\n{bullets(lines)}", result["sources"]


def local_supplier_change(model, question):
    supplier = model.find_supplier(question)
    nodes = [n for n in model.find_part(question) if not n.is_assembly]
    if not supplier:
        return local_supplier_map(model, question)
    if not nodes:
        return local_supplier_exit(model, question)
    match = re.search(r"(\d+)\s*%", question)
    share = int(match.group(1)) if match else (30 if re.search(r"seconde source|double source", normalize(question)) else 100)
    result = tools.supplier_switch(model, nodes[0].part_id, supplier["id"], share)
    lines = [
        f"Prix moyen : {eur(result['price_before'], 2)} puis {eur(result['price_after'], 2)}",
        f"Effet annuel : {signed_compact_eur(result['annual_delta'])}, coût unique : {compact_eur(result['one_off'])}",
        f"Délai avant série : {result['delay_weeks']} semaines",
        *result["remarks"][:3],
    ]
    return f"**{result['part']} : {result['share_pct']} % vers {supplier['name'].rstrip('.')}.**\n{bullets(lines)}", result["sources"]


def local_supplier_exit(model, question):
    supplier = model.find_supplier(question)
    if not supplier:
        return ("Précisez le fournisseur, par exemple : « Que se passe-t-il si Garda disparaît ? ».", [])
    result = tools.supplier_exit(model, supplier["id"])
    lines = [f"**{r['part']}** : {r['alternative']}, {r['delay_weeks']} semaines" for r in result["rows"]]
    lines.append(f"Coût unique {compact_eur(result['one_off'])}, effet annuel {signed_compact_eur(result['delta_annual'])}")
    return (f"**Sans {result['supplier']} : {result['parts']} pièces touchées, {result['no_alternative']} sans alternative.**\n{bullets(lines)}", result["sources"])


def local_supplier_map(model, question):
    supplier = model.find_supplier(question)
    if supplier:
        result = tools.supplier_mapping(model, supplier["id"])
        info = result["supplier"]
        lines = [f"**{p['part']}** : {p['share_pct']} %, {p['status'].lower()}" for p in result["parts"]]
        return (f"**{info['supplier']} ({info['country']}, notation {info['rating']}) : {compact_eur(info['spend_annual'])} par an.**\n{bullets(lines)}", result["sources"])
    result = tools.supplier_mapping(model)
    single = ", ".join(s["part"] for s in result["single_source_list"][:8])
    lines = [
        f"{result['suppliers_active']} fournisseurs actifs dans {result['countries']} pays, {pct(result['non_eu_share'])} des achats hors UE",
        f"3 premiers fournisseurs : {pct(result['top3_share'])} des achats",
        f"Premiers pays : {', '.join(c['country'] for c in result['spend_by_country'][:3])}",
        f"Mono-source : {single}…",
    ]
    return f"**{result['single_source_parts']} pièces dépendent d'un seul fournisseur qualifié.**\n{bullets(lines)}", result["sources"]


def local_release(model, question):
    target = "FROZEN" if "frozen" in normalize(question) or "gel" in normalize(question) else "RELEASED"
    result = tools.release_check(model, target)
    blocking = [r for r in result["not_ready"] if r["status"] in ("Bloquant", "En retard")]
    lines = [f"**{r['part']}** ({r['maturity']}) : {r['issues'][0]}" for r in blocking[:5]]
    lines.append(f"Prêtes : {result['ready']} sur {result['total']} ({pct(result['ready_mass_pct'])} de la masse)")
    lines.append(f"Date au plus tôt : {result['earliest_date']}, jalon le {result['gate']}")
    if result["corrections"]:
        lines.append(f"Maturité trop haute à corriger : {', '.join(result['corrections'])}")
    verdict = "Oui" if result["go"] else "Non"
    return f"**{verdict}, le produit {'peut' if result['go'] else 'ne peut pas'} passer {target} au jalon.**\n{bullets(lines)}", result["sources"]


def local_mass(model, question):
    query = normalize(question)
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*kg", query)
    target = float(match.group(1).replace(",", ".")) if match else None
    perimeter = next((name for name, words in (("ID_1", ["moteur"]), ("ID_17", ["reducteur"]), ("ID_51", ["carter"])) if any(w in query for w in words)), None)
    result = tools.mass_optimization(model, target, perimeter)
    heavy = ", ".join(f"{r['part']} ({kg(r['mass_kg'])})" for r in result["heaviest_parts"][:4])
    summary = result["summary"]
    lines = [f"**{o['part']}** : {o['label'].lower()}, {kg(-o['delta_mass'])} gagnés" for o in result["plan"][:6]]
    lines.append(f"Total : {kg(round(summary['saved_kg'], 2))}, {signed_eur(summary['delta_cost_unit'], 2)} par e-drive, {compact_eur(summary['one_off'])} de coût unique")
    head = f"**{result['perimeter']} : {kg(result['mass_kg'])}. Plus lourdes : {heavy}.**"
    return f"{head}\n{bullets(lines)}", result["sources"]


def local_alerts(model, question):
    query = normalize(question)
    nodes = model.find_part(question)
    part = nodes[0].id if len(nodes) == 1 and re.search(r"(sur|de la|du) ", query) else None
    domain = "parent-enfant" if re.search(r"incoheren|maturite|parent", query) else "Données manquantes" if re.search(r"manquant|vide", query) else None
    result = tools.data_alerts(model, part=part, domain=domain)
    totals = result["totals"]
    lines = [f"{a['severity']} · **{a['name']}** : {a['message']}" for a in result["alerts"][:6]]
    head = ", ".join((plural(totals["Bloquant"], "alerte bloquante", "alertes bloquantes"), plural(totals["Attention"], "point d'attention", "points d'attention"), plural(totals["Info"], "information")))
    return f"**{head}.**\n{bullets(lines)}", result["sources"]


def local_part(model, question):
    nodes = model.find_part(question, fuzzy=False)
    if not nodes:
        return None
    if len({n.part_id for n in nodes}) > 1:
        options = ", ".join(f"{n.product['description'] or n.label} ({kg(n.unit_mass)}, rév. {n.product['revision']})" for n in nodes)
        return (f"Plusieurs pièces portent ce nom : {options}. Précisez, par exemple « couronne » ou « pignon d'entrée ».", [model.source_ref(n.part_id, "nom, masse") for n in nodes])
    result = tools.part_details(model, nodes[0].id)
    lines = [f"Chemin : {result['path']}", f"Révision {result['revision']}, {result['maturity']}, modifiée le {result['modified']}", f"Masse : {kg(result['mass_total_kg'])}, coût : {eur(result['cost_total_eur'], 2)}"]
    if result.get("material"):
        lines.append(f"Matériau : {result['material']}")
    if result.get("suppliers"):
        lines.append("Fournisseurs : " + ", ".join(f"{s['name']} ({s['share_pct']} %)" for s in result["suppliers"]))
    if result.get("children"):
        lines.append("Contenu : " + ", ".join(c["name"] for c in result["children"]))
    if result["alerts"]:
        lines.append(f"Alerte : {result['alerts'][0]['message']}")
    return f"**{result['name']}** (`{result['plm_id']}`)\n{bullets(lines)}", result["sources"]


def local_indicators(model, _question):
    result = tools.indicators(model)
    lines = [
        f"{result['pieces']} pièces, {result['references']} références, {kg(result['mass_kg'])}",
        f"Coût de la nomenclature : {eur(result['bom_cost'])} par e-drive",
        f"{result['suppliers_active']} fournisseurs actifs dans {result['countries']} pays",
        f"{result['critical_parts']} composants critiques, {result['alerts']['Bloquant']} alertes bloquantes",
    ]
    return f"**E-drive avant 410 kW.**\n{bullets(lines)}", result["sources"]


# Intentions testées dans l'ordre : la première qui correspond répond.
LOCAL_INTENTS = [
    (r"defaillan|faillite|disparait|retrait|perd |sans (garda|voltaron|schwaben)", local_supplier_exit),
    (r"rupture|penurie|arret|incendie|inondation|greve", local_disruption),
    (r"changer|remplacer|basculer|deloc|seconde source|double source|passer .*(a|vers|chez)", local_supplier_change),
    (r"prix|hausse|baisse|augment|flamb|chute", local_price),
    (r"release|liberer|jalon|promouv|maturite suffisante|peut-on sortir", local_release),
    (r"poids|masse|leger|allege|lourd|alleger|\d\s*kg", local_mass),
    (r"critique", local_critical),
    (r"fournisseur|mono-source|monosource|origine|pays|cartographie", local_supplier_map),
    (r"alerte|incoheren|manquant|warning|qualite des donnees|anomalie", local_alerts),
    (r"combien|nombre de pieces|indicateur|resume|synthese", local_indicators),
]


def ask_local(model, question):
    query = normalize(question)
    try:
        known = answer_known(model, question)
        if known:
            return {**known, 'sources': dedupe_sources(known['sources']), 'mode': 'local'}
        for pattern, handler in LOCAL_INTENTS:
            if re.search(pattern, query):
                text, sources = handler(model, question)
                return {"text": text, "sources": dedupe_sources(sources), "mode": "local"}
        answer = local_part(model, question)
    except ToolError as error:
        return {"text": str(error), "sources": [], "mode": "local"}
    if answer:
        return {"text": answer[0], "sources": dedupe_sources(answer[1]), "mode": "local"}
    return {
        "text": "Je n'ai pas identifié la demande. Essayez par exemple :\n" + bullets(SUGGESTIONS),
        "sources": [],
        "mode": "local",
    }


def ask(model, question, history, screen_context, on_tool=None, backend="integrated"):
    """L'assistant intégré fonctionne sans serveur ; Ollama est un choix explicite."""
    if backend != "ollama":
        return ask_local(model, question)
    try:
        answer = local_llm.ask(model, question, history, screen_context, SYSTEM_PROMPT, on_tool)
        answer["sources"] = dedupe_sources(answer["sources"])
        return answer
    except local_llm.LocalModelError as error:
        answer = ask_local(model, question)
        answer["text"] = f"*{error}. Réponse de l'assistant intégré en secours.*\n\n{answer['text']}"
        return answer
