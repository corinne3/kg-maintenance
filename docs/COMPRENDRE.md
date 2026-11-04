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
