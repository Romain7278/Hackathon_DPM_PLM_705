"""Normalisation explicite des entrées des outils, sans filtre silencieusement perdu."""
import math
import re

from plm.model import normalize


class ToolError(Exception):
    """Paramètre inconnu, ambigu ou hors limites."""


def key(value):
    return re.sub(r'[^a-z0-9]+', ' ', normalize(value)).strip()


ALL = {'tous', 'toutes', 'tout', 'all', 'any', '*', ''}


def enum(value, aliases, label, allow_all=False):
    if value is None and allow_all:
        return None
    if not isinstance(value, str):
        raise ToolError(f"{label} : une valeur textuelle est attendue.")
    if allow_all and value.strip().lower() in ALL:
        return None
    canonical = aliases.get(key(value))
    if canonical is None:
        raise ToolError(f"{label} « {value} » inconnu. Valeurs possibles : {', '.join(sorted(set(aliases.values())))}.")
    return canonical


def alias_map(groups):
    return {key(alias): canonical for canonical, names in groups.items() for alias in [canonical, *names]}


SEVERITIES = alias_map({
    'Bloquant': ['bloquante', 'bloquants', 'bloquantes', 'blocage', 'blocking', 'blocker', 'alertes bloquantes', 'alerte bloquante'],
    'Attention': ['attentions', 'warning', 'warnings', 'avertissement', 'avertissements', 'points d attention', 'alerte attention'],
    'Info': ['infos', 'information', 'informations', 'informatif', 'informative', 'informatives', 'informational'],
})
DOMAINS = alias_map({
    'Données manquantes ou vides': ['données manquantes', 'donnée manquante', 'manquant', 'manquantes', 'missing data', 'complétude', 'champs vides', 'données vides'],
    'Cohérence parent-enfant': ['parent-enfant', 'parents enfants', 'maturité', 'cohérence des maturités', 'cohérence parent enfant', 'parent child', 'incohérences de maturité'],
    'Incohérence': ['incohérences', 'inconsistent', 'inconsistency', 'cycle de vie'],
    'Approvisionnement': ['approvisionnements', 'sourcing', 'supply', 'fournisseur', 'fournisseurs', 'qualification', 'ppap'],
    'Structure': ['structure produit', 'nomenclature', 'bom'],
    'Nommage': ['noms', 'nommage des pièces', 'naming', 'doublons de noms'],
})
MATURITIES = alias_map({
    'PRIVATE': ['privé', 'privés', 'privée', 'privées', 'brouillon', 'brouillons', 'draft'],
    'IN_WORK': ['en cours', 'en travail', 'en développement', 'en conception', 'in work', 'in progress'],
    'FROZEN': ['gelé', 'gelés', 'gelée', 'gelées', 'gel', 'figé', 'figés', 'figée', 'figées', 'frozen parts'],
    'RELEASED': ['libéré', 'libérés', 'libérée', 'libérées', 'validé', 'validés', 'validée', 'validées', 'released parts'],
    'OBSOLETE': ['obsolète', 'obsolètes', 'obsolete parts', 'retiré', 'retirés', 'retirée', 'retirées'],
})
FAMILIES = alias_map({
    'Acier': ['aciers', 'steel', 'steels'],
    'Acier électrique': ['aciers électriques', 'acier elec', 'electrical steel', 'electrical steels', 'tôles électriques'],
    'Aluminium': ['alu', 'aluminum', 'aluminiums'],
    'Cuivre': ['cuivres', 'copper'],
    'Fonte': ['fontes', 'cast iron'],
    'Polymère': ['polymères', 'polymers', 'polymer', 'plastique', 'plastiques'],
    'Magnésium': ['magnesium', 'magnésiums'],
})


def enum_filter(value, aliases, label):
    """OU dans un filtre ; les différents types de filtres restent combinés par ET."""
    if value is None or isinstance(value, str) and value.strip().lower() in ALL:
        return None
    if isinstance(value, str) and key(value) in aliases:
        return [aliases[key(value)]]
    values = value if isinstance(value, list) else re.split(r'\s+(?:ou|or)\s+|[,;|]', value, flags=re.I) if isinstance(value, str) else [value]
    if not values:
        raise ToolError(f'{label} : filtre vide. Utilisez « tous » pour ne pas filtrer.')
    result = [enum(item.strip() if isinstance(item, str) else item, aliases, label) for item in values]
    return list(dict.fromkeys(result))


def numeric(value, label, low, high, integer=False, units=()):
    if isinstance(value, str):
        text = normalize(value).replace('\u202f', '').replace('\xa0', '').strip()
        words = {'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5, 'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9, 'dix': 10, 'douze': 12, 'quinze': 15, 'vingt': 20}
        unit_pattern = '|'.join(re.escape(unit) for unit in units)
        if unit_pattern:
            text = re.sub(rf'\s*(?:{unit_pattern})\s*$', '', text).strip()
        if text in words:
            value = words[text]
        elif re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', text):
            value = float(text.replace(',', '.'))
        else:
            raise ToolError(f"{label} « {value} » : nombre ou unité non reconnu.")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ToolError(f"{label} : un nombre fini est attendu.")
    if not low <= value <= high or integer and int(value) != value:
        raise ToolError(f"{label} : {'entier' if integer else 'nombre'} attendu entre {low} et {high}.")
    return int(value) if integer else float(value)


def boolean(value, label):
    if isinstance(value, bool):
        return value
    return enum(value, alias_map({'true': ['oui', 'yes', 'vrai', '1'], 'false': ['non', 'no', 'faux', '0']}), label) == 'true'


NUMBERS = {
    'weeks': (1, 104, True, ('semaines', 'semaine', 'weeks', 'week', 'sem')),
    'top': (1, 100, True, ()), 'limit': (1, 100, True, ()),
    'share_pct': (1, 100, True, ('%', 'pour cent', 'percent')),
    'pct': (-100, 500, False, ('%', 'pour cent', 'percent')),
    'target_saving_kg': (0, 100, False, ('kg', 'kilogrammes', 'kilogramme')),
}


def normalize_arguments(name, arguments):
    if not isinstance(arguments, dict):
        raise ToolError('Les paramètres doivent former un objet.')
    aliases = {'piece': 'part', 'composant': 'part', 'fournisseur': 'supplier', 'semaines': 'weeks', 'severite': 'severity', 'domaine': 'domain', 'famille': 'family', 'maturite': 'maturity', 'matiere': 'material', 'materiau': 'material', 'variation_pct': 'pct', 'part_pct': 'share_pct', 'gain_kg': 'target_saving_kg', 'perimetre': 'perimeter', 'nombre': 'top', 'requete': 'query', 'assemblage': 'assembly', 'cible': 'target', 'faisabilite_faible': 'allow_low_feasibility'}
    result = {}
    for raw, value in arguments.items():
        if not isinstance(raw, str):
            raise ToolError('Nom de paramètre non textuel.')
        identifier = key(raw).replace(' ', '_')
        parameter = aliases.get(identifier, identifier)
        if parameter in result:
            raise ToolError(f"Paramètre {parameter} fourni plusieurs fois.")
        optional_entities = {'data_alerts': ('part',), 'supplier_mapping': ('supplier',), 'product_structure': ('assembly',), 'mass_optimization': ('perimeter',)}
        if parameter in optional_entities.get(name, ()) and isinstance(value, str) and key(value) in ('tous', 'toutes', 'all', 'produit complet', 'tout le produit', ''):
            value = None
        if parameter in NUMBERS and value is not None:
            low, high, integer, units = NUMBERS[parameter]
            value = numeric(value, parameter, low, high, integer, units)
        elif parameter == 'target':
            value = enum(value, MATURITIES, 'Maturité cible')
        elif parameter == 'allow_low_feasibility':
            value = boolean(value, 'Faisabilité faible')
        result[parameter] = value
    return result
