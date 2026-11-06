# Comprendre le projet, brique par brique

## L'idée en une phrase
- Transformer 514 rapports d'incidents hydrauliques (texte libre + quelques champs) en un **graphe de connaissances**.
- Puis mesurer, chiffres à l'appui, les difficultés qui apparaissent : c'est le sujet du projet, pas la démo.

## Le chemin des données

```
CSV FAA ──► loader ──► mapping (domaine) ──► FAITS ──┬──► graphe NetworkX ──► analyses (hubs, chemins)
                                                    ├──► CSV + Cypher ──► Neo4j / FalkorDB
                                                    └──► Turtle (RDF) ──► SPARQL (rdflib)
```

| Brique | Fichier | Ce qu'elle fait | Générique ? |
| --- | --- | --- | --- |
| Config du domaine | `domains/maintenance_aviation/config.yaml` | Périmètre, ontologie, dictionnaire de variantes | Non (propre au domaine) |
| Mapping | `domains/maintenance_aviation/mapping.py` | Une ligne FAA → une liste de faits | Non |
| Faits | `kgcore/facts.py` | Format pivot : triplet + provenance | Oui |
| Entity resolution | `kgcore/resolver.py` | Variantes d'écriture → entité canonique | Oui |
| Graphe | `kgcore/graph.py` | Construction, hubs, parcours naïf vs typé | Oui |
| Exports | `kgcore/export.py` | CSV Neo4j, script Cypher, Turtle RDF | Oui |

**« Même stack, problèmes différents »** : pour un domaine RH, on écrirait seulement un nouveau `config.yaml` + `mapping.py`. Tout `kgcore/` reste identique.

## Les notions, simplement

- **Ontologie** : la liste des types de choses (Rapport, Avion, Pièce…) et des liens autorisés entre elles (un Rapport *CONCERNE* un Avion). C'est le « schéma » du graphe. Ici : section `ontology` du config.
- **Fait (triplet)** : sujet → relation → objet. Ex. `Rapport X —INVOLVES_PART→ Pompe moteur`. On y ajoute la **provenance** : de quelle source vient le fait (champ structuré, dictionnaire, LLM) et quel texte le justifie.
- **Entity resolution** : décider que `EDP`, `ENG 1 PUMP` et `ENGINE DRIVEN HYDRAULIC PUMP` sont la même chose. Sans ça, le graphe a trois nœuds au lieu d'un, et chaque comptage est faux.
- **Property graph** (Neo4j, FalkorDB) : des nœuds et des relations qui portent des propriétés. Langage : **Cypher**.
- **RDF** (standard du W3C) : uniquement des triplets, identifiés par des URI globales. Langage : **SPARQL**. Avantage : interopérable, se relie à des référentiels publics. Inconvénient : mettre une propriété sur un lien oblige à **réifier** (transformer le lien en nœud).
- **Hub** : nœud relié à énormément d'autres (ex. l'état « LEAKING »). Un GraphRAG qui suit tous les liens passe par les hubs et ramène tout le graphe.
- **GraphRAG** : au lieu de donner au LLM des extraits de texte proches de la question (RAG classique), on lui donne un morceau de graphe autour des entités de la question.

## Ce que montre l'étape 1 (chiffres dans `outputs/step1_report.md`)
1. Le champ structuré dit « PUMP » dans 117 rapports. **Selon ce champ seul, 0 rapport concerne une pompe moteur (EDP). En lisant le texte, 147.**
2. La même pompe est écrite de 15 façons différentes dans le texte (EDP, ENG PUMP, ENGINE-DRIVEN HYDRAULIC PUMP…), sans compter les numéros de moteur et les pluriels.
3. Un dictionnaire se trompe aussi : « EMP: U349218 » est un numéro d'employé, pas une pompe.
4. Un dictionnaire trouve les mots, pas le sens : 12 rapports citent plusieurs pompes ; laquelle est en panne ?
5. Un parcours naïf à 3 sauts ramène 61 % du graphe. Une requête qui suit le schéma ramène seulement ce qui répond.

## Lancer le projet sur ton PC (Windows)

```powershell
cd C:\dev\kg-maintenance
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# télécharger SDR-2025.csv depuis https://www.faa.gov/av-info/download_SDR dans data\
python run_step1.py
python run_sparql.py
```

Étape 2 (LLM local) :

```powershell
# installer Ollama depuis https://ollama.com, puis :
ollama pull llama3.2:3b
python run_step2_llm.py --limit 30
```

Charger le graphe dans Neo4j (optionnel) :
- Neo4j Desktop → créer une base → copier `outputs/property_graph/nodes.csv` et `edges.csv` dans son dossier `import`.
- Exécuter `outputs/property_graph/import_neo4j.cypher`, puis les requêtes de `queries/README.md`.

## L'assistant (étape 3)

```powershell
pip install streamlit scikit-learn
streamlit run app.py
```
- Une page s'ouvre dans ton navigateur (http://localhost:8501).
- Choisis une question exemple ou tape la tienne, en anglais.
- Trois colonnes : **RAG classique** (textes ressemblants), **GraphRAG naïf** (tout à N sauts, déborde), **GraphRAG guidé** (le chemin de l'ontologie, avec des comptages).
- Case « Generate answers with the LLM » : le LLM répond à partir de chaque contexte (30 à 60 s par réponse).
- Case « model hierarchy » : décoche-la pour voir la question « A320 family » perdre la moitié de ses rapports (51 → 24).

## Le cas RH (2e domaine)

- **Données** : le vrai référentiel **ESCO** (métiers et compétences, en anglais et en français) + une **entreprise fictive** de 161 salariés générée par `domains/hr/generate.py`. Aucune personne réelle ; chaque fichier porte `synthetic=True`.
- **Pourquoi** : le graphe maintenance est en étoile autour des rapports. Un graphe de personnes a des chaînes longues, des données sensibles et du temps : il montre les pièges que la maintenance ne pouvait pas montrer.
- **Ce qu'il montre** (chiffres dans `outputs/hr_report.md`) :
  - le référentiel lui-même est ambigu : 1 539 libellés ESCO désignent plusieurs métiers ; « technicien **en** » et « technicien **de** » maintenance aéronautique sont deux métiers ;
  - Toulouse (français) et Bristol (anglais) ne sont reliés que par « Excel » et « communication » : des nœuds poubelles qui donnent une fausse impression de graphe connecté ;
  - la règle « collègue de collègue » propose 72 % de mobilités absurdes (aucune compétence commune) ; le chemin guidé par l'ontologie : 0 % ;
  - 13 équipes sur 30 ont moins de 5 personnes : une moyenne de salaire par équipe révélerait des individus ;
  - sans dates sur les liens, une réorganisation donne deux managers à 4 personnes, et 12 personnes gardent une habilitation expirée ;
  - une seule requête traverse les deux domaines : 51 incidents EDP sur famille A320, et 23 techniciens habilités.

```powershell
# ESCO v1.2.1, classification, CSV, en + fr : dézipper dans data\esco\en et data\esco\fr
python -m domains.hr.generate
python run_hr.py
python build_explorer.py
```

## L'agent (onglet 2 de l'assistant)

- **Ce qu'il fait** : pour chaque question, il choisit lui-même les outils (statistiques maintenance, recherche dans les textes, techniciens habilités, mobilité interne, agrégat RH sensible), vérifie les arguments, vérifie les droits, exécute, contrôle le résultat, et escalade vers une personne s'il ne peut pas répondre. Chaque décision est tracée.
- **Les garde-fous** (testés avec un LLM qui se trompe exprès) : outil inventé rejeté, JSON invalide → escalade, « leaks » réparé en LEAKING, outil sensible refusé pour un simple salarié même si le LLM le choisit, agrégat refusé sous 5 personnes.
- **Le routage, mesuré sur 16 questions** : règles seules (13/16, ratent les reformulations), LLM seul, ou hybride (règles d'abord, LLM seulement si aucune règle ne s'applique). C'est le même principe que la règle hybride de l'extraction.
- **Le vocabulaire à savoir dire** : tool use, router, garde-fous (validation de schéma, contrôle d'accès), human-in-the-loop (escalade), observabilité (trace des décisions), évaluation (jeu de questions de référence).

```powershell
python eval_agent.py          # environ 10 min : règles vs LLM vs hybride
streamlit run app.py          # onglet « Agent »
```


## Se promener dans tout le graphe (Streamlit, 2e onglet)

- `streamlit run app.py`, onglet **Explore the graph**.
- Chercher un nœud (ex. `PTU`, `LEAKING`, `A320`, `E161`, `Excel`), choisir 1 ou 2 sauts, filtrer les relations.
- Cliquer une ligne du tableau des relations = aller sur ce voisin ; bouton **← Back** pour revenir.
- Survoler un point du dessin = son nom, son type, son nombre de liens, et le nom des relations autour.
- Les arêtes sensibles (tranche de salaire, absence longue) ne sont pas affichées : elles restent derrière les règles d'accès de l'agent.
- Code : `assistant/explore.py` (calcul des positions avec NetworkX, dessin sans bibliothèque JavaScript).
