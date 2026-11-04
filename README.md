# Graphe de connaissances de maintenance : là où ça coince

Cas d'étude sur des **données publiques réelles** : les *Service Difficulty Reports* de la FAA (2025), chapitre ATA 29 (hydraulique), 514 rapports d'incidents.

Le but n'est pas une démo qui marche. C'est de **rendre visibles et mesurables** les difficultés que rencontrent les équipes qui construisent des graphes de connaissances à partir de données industrielles.

## Ce que montrent les données (étape 1)

| Difficulté | Constat chiffré |
| --- | --- |
| Entity resolution | Le champ structuré dit « PUMP » dans 117 rapports. Selon ce champ seul, **0** rapport concerne une pompe moteur (EDP) ; en lisant le texte, **147**. La même pompe est écrite de **15** façons (hors numéros de moteur et pluriels). |
| Faux positifs | « EMP: U349218 » est un numéro d'employé, pas une *Electric Motor Pump*. |
| Mention ≠ panne | **12** rapports citent plusieurs pompes : un dictionnaire ne sait pas laquelle est en panne. |
| Hubs | Un parcours GraphRAG naïf à 3 sauts ramène **61 %** du graphe. Une requête guidée par l'ontologie ne ramène que ce qui répond. |
| Property graph vs RDF | Mêmes faits, deux modèles. La provenance est une propriété d'arête en Cypher ; en RDF, il faut réifier chaque triplet. |

Détails : [`outputs/etape1_rapport.md`](outputs/etape1_rapport.md) · Notions expliquées : [`docs/COMPRENDRE.md`](docs/COMPRENDRE.md) · Choix de conception : [`DECISIONS.md`](DECISIONS.md)

## Architecture : même stack, autre domaine

- `kgcore/` : générique (faits + provenance, entity resolution, graphe, exports Cypher et RDF).
- `domains/maintenance_aviation/` : tout ce qui est propre au domaine (périmètre, ontologie, dictionnaire, mapping).
- Un autre domaine = un autre dossier sous `domains/`.

## Stack
100 % open source, en local, sur un PC portable CPU 8 Go : Python, pandas, NetworkX, rdflib (SPARQL), export Neo4j/FalkorDB (Cypher), Ollama pour l'extraction par LLM (étape 2).

## Lancer
Voir [`docs/COMPRENDRE.md`](docs/COMPRENDRE.md#lancer-le-projet-sur-ton-pc-windows).

## Transparence
Données publiques FAA. Code écrit avec un assistant IA ; le cadrage, les choix de conception ([`DECISIONS.md`](DECISIONS.md)) et l'analyse sont les miens.
