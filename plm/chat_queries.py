"""Questions d'exploration partagées par les deux modes du chatbot."""
import re

from plm import tools
from plm.fmt import eur, kg
from plm.model import normalize
from plm.tool_inputs import key, FAMILIES, MATURITIES

SUGGESTIONS = [
    "Quels sont les indicateurs clés du produit ?",
    "Comment le produit est-il structuré ?",
    "Quels composants ont des alertes bloquantes ?",
    "Quelles données sont manquantes ?",
    "Quels sont les composants les plus critiques ?",
    "Quelles pièces sont mono-source ?",
    "De quels pays viennent les fournisseurs ?",
]


def plan_question(model, question):
    query = normalize(question)
    if re.search(r"alerte|bloquant|incoheren|manquant|anomalie|avertiss|warning|blocage", query):
        args = {}
        if 'bloquant' in query:
            args['severity'] = 'Bloquant'
        if re.search(r'attention|avertiss|warning', query):
            args['severity'] = (args['severity'] + ' ou ' if 'severity' in args else '') + 'Attention'
        if re.search(r"alertes? (info|informativ)|(?:ou|et) infos?\b|informatives", query):
            args['severity'] = (args['severity'] + ' ou ' if 'severity' in args else '') + 'Info'
        if re.search(r'manquant|vide', query):
            args['domain'] = 'Données manquantes ou vides'
        elif re.search(r'parent|maturite|incoheren', query):
            args['domain'] = 'Cohérence parent-enfant' if re.search(r'parent|maturite', query) else 'Incohérence'
        elif re.search(r'nommage|noms|naming', query):
            args['domain'] = 'Nommage'
        elif re.search(r'approvision|fournisseur|ppap', query):
            args['domain'] = 'Approvisionnement'
        explicit = re.search(r'\b(?:ID_\d+|prd-[\w-]+)\b', question, re.IGNORECASE)
        nodes = model.find_part(explicit.group(0) if explicit else question)
        ids = {n.part_id for n in nodes}
        if len(ids) == 1:
            args['part'] = nodes[0].id
        return {'tool': 'data_alerts', 'arguments': args}
    # Une liste filtrée doit passer par la recherche, pas par une fiche dont le
    # nom serait un matériau ou une maturité.
    if re.search(r'list|cherch|affich|trouv|quels|quelles', query) and re.search(r'piece|composant|roulement|carter|arbre|engrenage', query) and not re.search(r'hausse|baisse|variation|prix|rupture|changer', query):
        remaining = key(question)
        filters = {}
        for parameter, aliases in (('family', FAMILIES), ('maturity', MATURITIES)):
            values = []
            for alias in sorted(aliases, key=len, reverse=True):
                if re.search(r'\b'+re.escape(alias)+r'\b', remaining):
                    values.append(aliases[alias])
                    remaining = re.sub(r'\b'+re.escape(alias)+r'\b', ' ', remaining)
            if values:
                filters[parameter] = ' ou '.join(dict.fromkeys(values))
        if filters:
            stop = {'liste', 'listes', 'les', 'le', 'la', 'des', 'de', 'du', 'en', 'qui', 'sont', 'quels', 'quelles', 'quelles', 'pieces', 'piece', 'composants', 'composant', 'et', 'ou', 'affiche', 'moi', 'trouve', 'cherche', 'recherche', 'toutes', 'tous'}
            filters['query'] = ' '.join(word for word in remaining.split() if word not in stop)
            return {'tool': 'search_parts', 'arguments': filters}
    if re.search(r'liber|release|jalon|peut.*gel', query):
        return {'tool': 'release_check', 'arguments': {'target': 'FROZEN' if re.search(r'gel|frozen|fige', query) else 'RELEASED'}}
    percent = re.search(r'([+-]?\d+(?:[.,]\d+)?)\s*(?:%|pour cent)', query)
    if percent and re.search(r'hausse|baisse|variation|prix|augment|dimin', query):
        family = model.find_family(question)
        if family:
            value = float(percent.group(1).replace(',', '.'))
            if re.search(r'baisse|dimin|recul', query):
                value = -abs(value)
            return {'tool': 'material_price', 'arguments': {'material': family, 'pct': value}}
    if re.search(r'fiche|detail', query):
        explicit = re.search(r'\b(?:id[ _-]*\d+|prd-[\w-]+)\b', question, re.I)
        if explicit:
            return {'tool': 'part_details', 'arguments': {'part': explicit.group(0)}}
    if re.search(r'indicateur|vue d.ensemble|resume du produit|synthese du produit', query):
        return {'tool': 'indicators', 'arguments': {}}
    if re.search(r'structur|assemblages.*produit|composition du produit', query):
        return {'tool': 'product_structure', 'arguments': {}}
    if re.search(r'composants? .*critiques?|pieces? .*critiques?', query):
        count = re.search(r'\b(\d+)\b', query)
        spelled = next((n for word, n in (('deux', 2), ('trois', 3), ('quatre', 4), ('cinq', 5), ('six', 6), ('dix', 10)) if re.search(r'\b'+word+r'\b', query)), 6)
        return {'tool': 'critical_parts', 'arguments': {'top': min(25, max(1, int(count.group(1)))) if count else spelled}}
    if re.search(r'mono.source|monosource|pays.*fournisseur|origine.*fournisseur|fournisseur.*pays|fournisseur.*origine', query):
        return {'tool': 'supplier_mapping', 'arguments': {}}
    return None


def render_result(name, payload, question):
    """Les décomptes et listes sont restitués sans réécriture par le modèle."""
    if name == 'search_parts':
        lines = [f"**{r['name']}** (`{r['plm_id']}`) : {kg(r['mass_kg'])}, révision {r['revision']}, {r['maturity']}." for r in payload['results']]
        return f"**{payload['count']} élément(s) correspondent aux filtres.**\n\n" + '\n'.join('- '+line for line in lines) + (f"\n\n{len(lines)} résultats affichés." if len(lines) < payload['count'] else '')
    if name == 'data_alerts':
        total = payload['total']
        scope = f" ({payload['severity']})" if payload['severity'] else ''
        if not total:
            return f"Aucune alerte{scope} ne correspond aux filtres de cette question."
        head = f"**{total} alerte(s){scope}, sur {payload['affected_components']} élément(s) PLM.**"
        lines = [f"**{a['name']}** (`{a['plm_id']}`) · {a['severity']} : {a['message']}" for a in payload['alerts']]
        if total > len(lines):
            lines.append(f"{len(lines)} alertes affichées sur {total}. Le détail est disponible dans Product Explorer et les fiches des composants.")
        return head + '\n\n' + '\n'.join('- ' + line for line in lines)
    if name == 'indicators':
        return f"**Vue d’ensemble du produit**\n\n- {payload['pieces']} pièces, {payload['references']} références, {kg(payload['mass_kg'])}.\n- Coût nomenclature : {eur(payload['bom_cost'], 2)} par e-drive.\n- {payload['suppliers_active']} fournisseurs actifs dans {payload['countries']} pays.\n- {payload['critical_parts']} composants critiques ; {payload['alerts']['Bloquant']} alertes bloquantes au total, dont {payload['data_control_alerts']['Bloquant']} dans le contrôle des données."
    if name == 'product_structure':
        lines = [f"**{c['name']}** (`{c['plm_id']}`) · quantité {c['quantity']}, {kg(c['mass_kg'])}, {c['maturity']}." for c in payload['children']]
        return f"**{payload['assembly']}** : {payload['pieces']} pièces, {payload['references']} références.\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'critical_parts':
        lines = [f"**{p['name']}** (`{p['plm_id']}`) : **{p['score']}/100 · {p['level']}**. " + '; '.join(p['reasons'][-3:-1]) + '.' for p in payload['parts']]
        return f"**{payload['levels']['Critique']} composants critiques.** Voici les composants aux scores les plus élevés :\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'supplier_mapping' and 'supplier' not in payload:
        if re.search(r'mono.source|monosource', normalize(question)):
            lines = [f"**{p['part']}** (`{p['plm_id']}`) : {p['qualified']} fournisseur(s) qualifié(s) ; {p['suppliers'] or 'aucun fournisseur référencé'}." for p in payload['single_source_list'][:10]]
            return f"**{payload['single_source_parts']} pièces avec au plus un fournisseur qualifié.**\n\n" + '\n'.join('- '+line for line in lines) + ('\n\n10 premières pièces affichées.' if len(payload['single_source_list']) > 10 else '')
        lines = [f"**{row['country']}** : {row['suppliers']} fournisseur(s) actif(s)." for row in payload['suppliers_by_country']]
        return f"**{payload['suppliers_active']} fournisseurs actifs dans {payload['countries']} pays.**\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'supplier_mapping':
        supplier = payload['supplier']
        lines = [f"**{p['part']}** (`{p['plm_id']}`) : {p['share_pct']} % du volume, {p['status']}." for p in payload['parts']]
        return f"**{supplier['supplier']} · {supplier['country']} · notation {supplier['rating']}.**\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'supply_disruption':
        best = payload['strategies'][payload['best_strategy']]
        wait = payload['strategies']['wait']
        return f"**Rupture de {payload['duration_weeks']} semaines · {payload['part']} · {payload['supplier']}.**\n\n- Sans action : {wait['lost_units']:g} e-drives perdus, coût {eur(wait['total_cost'])}.\n- Meilleure stratégie : {best['label']}, coût {eur(best['total_cost'])}.\n- " + '\n- '.join(payload['recommendations'][:3])
    if name == 'supplier_exit':
        lines = [f"**{p['part']}** : {p['alternative']}, délai {p['delay_weeks']} semaines." for p in payload['rows']]
        return f"**{payload['parts']} pièces touchées par la disparition de {payload['supplier']}, {payload['no_alternative']} sans alternative.**\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'supplier_switch':
        return f"**{payload['part']} : changement de fournisseur sur {payload['share_pct']} % du volume.**\n\n- Prix moyen : {eur(payload['price_before'], 2)} → {eur(payload['price_after'], 2)}.\n- Délai : {payload['delay_weeks']} semaines ; coût unique : {eur(payload['one_off'])}.\n- Effet annuel : {eur(payload['annual_delta'])}.\n- " + '\n- '.join(payload['remarks'][:3])
    if name == 'release_check':
        lines = [f"**{p['part']}** (`{p['plm_id']}`) : {p['status']} ; {'; '.join(p['issues'])}." for p in payload['not_ready'][:10]]
        return f"**{'GO' if payload['go'] else 'NO-GO'} pour {payload['target']} : {payload['ready']} pièces prêtes sur {payload['total']}.**\n\n" + '\n'.join('- '+line for line in lines)
    if name == 'mass_optimization':
        summary = payload['summary']
        lines = [f"**{p['part']}** : {p['label']}, gain de {kg(-p['delta_mass'])}." for p in payload['plan']]
        return f"**Objectif : {kg(payload['target_saving_kg'])} ; gain calculé : {kg(summary['saved_kg'])}.**\n\n" + '\n'.join('- '+line for line in lines) + f"\n\nVariation de coût : {eur(summary['delta_cost_unit'], 2)} par e-drive ; coût unique : {eur(summary['one_off'])}."
    return None


def answer_known(model, question):
    plan = plan_question(model, question)
    if plan is None:
        return None
    payload = getattr(tools, plan['tool'])(model, **plan['arguments'])
    return {'text': render_result(plan['tool'], payload, question), 'sources': payload['sources'], 'tool': plan['tool']}
