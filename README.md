# PLM Intelligence - Team 705

Application Streamlit en mode sombre d’analyse d’un e-drive automobile : exploration du produit, risques fournisseurs et simulations d’impacts.

## Setup

Prérequis : Python 3.11+ et, pour les commandes ci-dessous, Windows / PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Ouvrir l’adresse locale affichée par Streamlit. Le bouton à droite du titre permet de choisir un XML enrichi présent dans `data/`.

### Ollama — facultatif

L’assistant intégré fonctionne sans installation supplémentaire. Pour utiliser le modèle local **Qwen3 1.7B** :

```powershell
# Premier lancement : téléchargement du moteur et du modèle (~3 Go)
./scripts/start-local-ai.ps1 -Install

# Lancements suivants
./scripts/start-local-ai.ps1
```

Activer ensuite **Utiliser Ollama** dans le chatbot. Le serveur écoute sur `127.0.0.1:11434` ; moteur, modèles et journaux restent dans `.local-ai/`, ignoré par Git. Si Ollama est indisponible, l’assistant intégré prend le relais.

## Fonctionnement

- **Product Explorer** : arborescence, fiches des composants, fournisseurs, historique et contrôle des données.
- **Risques et interdépendances** : scores détaillés, complexité, interfaces et origine des fournisseurs. Priorités réglables par critère : Élevé / Normal / Faible (poids 30 / 20 / 10, normalisés sur 100), appliquées dans toutes les analyses.
- **Analyse d’impacts** : comparaison à la référence après rupture, variation du coût matière, changement de fournisseur, maturité ou modification d’une pièce. Des aides contextuelles expliquent les indicateurs.
- **Suivi de versions** : charger un XML de même structure, consulter les écarts par pièce et comparer les indicateurs d’analyse d’impacts avec le bouton dédié.
- **Chatbot** : questions sur le produit et appels aux outils de calcul, avec sources PLM. Les filtres sont normalisés et les résultats chiffrés sont restitués par le code.

Le XML fournit les données d’entrée. L’application calcule les scores, alertes, constats, notes fournisseurs et résumés historiques. Les simulations modifient une copie du produit.

L’export original des organisateurs reste intact. Les fournisseurs et données économiques ajoutés sont des hypothèses de démonstration. Pour modifier ces hypothèses puis régénérer le XML enrichi :

```powershell
python enrich_xml.py
```

## Arborescence

```text
app.py                          # Point d’entrée Streamlit
requirements.txt                # Dépendances Python
plm_parser.py                   # Lecture du format XPDMXML
enrich_xml.py                   # Hypothèses et génération du XML enrichi
Hackathon dataset/              # Export original des organisateurs
data/                           # XML enrichis sélectionnables dans l’application
plm/                            # Modèle, scores, contrôles, simulations et chatbot
ui/                             # Vues Streamlit, thème et état de navigation
components/plm_tree/            # Composant HTML de l’arborescence
scripts/start-local-ai.ps1       # Installation et lancement d’Ollama
.streamlit/                     # Configuration Streamlit
```
