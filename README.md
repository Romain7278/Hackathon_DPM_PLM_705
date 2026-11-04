# PLM Intelligence : dashboard e-drive 410 kW

Dashboard Streamlit à trois onglets : Product Explorer, Risques et interdépendances, Analyse d'impacts. Un bouton en bas à gauche ouvre un assistant qui cite ses sources PLM.

## Lancer

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Passez par `python -m` : la commande `streamlit` seule n'est pas reconnue quand le dossier des scripts Python n'est pas dans le PATH, ce qui est courant avec Anaconda sous Windows.

## Activer Claude dans le chatbot (facultatif)

Sans clé, le chatbot fonctionne en mode local : réponses guidées par mots-clés, sans IA, sur les mêmes calculs.
Pour le langage naturel complet, définissez la variable d'environnement `ANTHROPIC_API_KEY`, ou créez `.streamlit/secrets.toml` avec :

```toml
ANTHROPIC_API_KEY = "votre-clé"
```

Ne partagez jamais ce fichier. Le modèle utilisé est défini par `MODEL_ID` dans `plm/assistant.py`.

## Organisation

| Fichier | Rôle |
|---|---|
| `Hackathon dataset/XPDMXML_ECAR_PLM.xml` | Export d'origine des organisateurs, jamais modifié |
| `enrich_xml.py` | Génère le XML enrichi. Toutes les hypothèses sont dans ce fichier |
| `data/XPDMXML_ECAR_PLM_ENRICHED.xml` | XML enrichi lu par le dashboard |
| `plm_parser.py` | Lit le XML, d'origine ou enrichi |
| `plm/model.py` | Arbre, coûts, sources, relations, positions |
| `plm/quality.py` | Alertes : données manquantes ou vides, cohérence parent-enfant, autres constats par pièce |
| `plm/scenarios.py` | Score de risque détaillé et calculs par scénario |
| `plm/impact.py` | Analyse d'impacts : facteurs combinés appliqués à une copie du produit, score qualité, comparaison à la référence |
| `plm/tools.py`, `plm/assistant.py` | Outils et chatbot |
| `ui/`, `components/`, `app.py` | Interface |

Pour changer une hypothèse : modifiez `enrich_xml.py`, lancez `python enrich_xml.py`, puis redémarrez Streamlit.

## Origine des données

**Export d'origine :** structure, identifiants, noms, révisions courantes, masses, matériaux, positions 3D.

**Déduit du XML d'origine :** les couples d'engrenages et les roulements coaxiaux. Les entraxes calculés à partir des positions tombent exactement sur 100,0 mm et 154,0 mm. Attention, `Rotation3D` se lit par colonnes.

**Simulé dans l'extension `ext:Enrichment` :** coûts, fournisseurs, PPAP, contrats, maturités, dates, propriétaires, historiques de révision, interfaces non déduites des positions, options d'allègement, paramètres du programme.

Les fournisseurs et les événements sont **fictifs**. Toute ressemblance avec une société existante serait fortuite. L'application rappelle l'origine de chaque donnée.

## Bases des prix

- Cuivre : LME 14 415 $/t au 23/10/2026, soit 12,64 €/kg à 1,14 $/€, plus la conversion en fil émaillé (hypothèse).
- Aluminium : LME environ 3 100 $/t début octobre 2026, plus une prime Europe d'environ 300 $/t.
- Taux de change : 1,14 $/€, référence BCE de juillet 2026, faute de valeur plus récente.
- Magnésium : gain de 25 à 36 % annoncé sur des carters d'e-drive (publications de fabricants et presse spécialisée).
- Autres matières, conversions, capacités, délais et pénalités : hypothèses de travail, à faire valider par des experts.

## Limites connues

- L'export ne contient ni rotor ni aimants : le risque terres rares n'est pas couvert (signalé dans le dashboard).
- L'export ne contient pas la géométrie 3D : les positions sont réelles, mais chaque point est l'origine d'une pièce.
- Les scénarios de rupture et de prix sont calculés à cadence série, alors que le démarrage série n'a lieu qu'en septembre 2027.
- Le plan d'allègement est une heuristique : options triées par coût du kg gagné, une option par pièce.
- Les scores de risque et de qualité sont des indicateurs de travail, à calibrer avec des experts : leurs barèmes sont affichés dans l'application.
- L'analyse d'impacts montre un état : la rupture pendant l'arrêt, le changement de fournisseur une fois qualifié, le prix à plein régime.
